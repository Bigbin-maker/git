import {
  ApartmentOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExportOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { Alert, App, Badge, Button, Descriptions, Input, Space, Table, Tabs, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useRef, useState } from 'react';
import { client } from '../api/client';
import { MarkdownMessage } from '../components/MarkdownMessage';
import type {
  MagicDrawExchangeElement,
  MagicDrawExchangeRelationship,
  MagicDrawDiagramLayout,
  MagicDrawLayoutEdge,
  MagicDrawBridgeOperationResult,
  MagicDrawPublishResult,
  MagicDrawStatus,
  ModelElement,
  ModelRelationship,
  SysMLDiagramView,
  SysMLIntentResult,
  SysMLProjectGenerateResult,
  ToolCall,
} from '../types';

const { TextArea } = Input;

type DialogueRole = 'system' | 'user' | 'assistant';
type FlowStatus = 'idle' | 'running' | 'done' | 'error';

interface DialogueMessage {
  id: string;
  role: DialogueRole;
  title: string;
  content: string;
  toolCalls?: ToolCall[];
  streaming?: boolean;
  context?: boolean;
}

interface FlowEvent {
  id: string;
  title: string;
  detail: string;
  status: FlowStatus;
  time: string;
}

const defaultPrompt =
  '请描述要建模的系统，例如：请你帮我设计一个飞机总体系统，并生成需求、边界、功能链路、接口、行为流程、约束和可推送到MagicDraw的SysML工程。';

export default function ModelGeneration1() {
  const { message } = App.useApp();
  const [projectName, setProjectName] = useState('AI_MBSE_Project');
  const [input, setInput] = useState('');
  const [dialogue, setDialogue] = useState<DialogueMessage[]>([
    {
      id: 'system-ready',
      role: 'system',
      title: 'AI建模助手',
      content:
        '请用自然语言描述任务目标、系统边界、关键功能、接口、约束和交付要求。我会基于对话上下文生成完整SysML工程，并把同一批模型推送到MagicDraw Bridge。',
    },
  ]);
  const [events, setEvents] = useState<FlowEvent[]>([
    {
      id: 'boot',
      title: 'AI工作台已就绪',
      detail: '等待对话输入。当前流程为：AI对话 -> 生成SysML工程 -> 推送MagicDraw -> 前端回显结果。',
      status: 'idle',
      time: nowTime(),
    },
  ]);
  const [projectResult, setProjectResult] = useState<SysMLProjectGenerateResult | null>(null);
  const [elements, setElements] = useState<ModelElement[]>([]);
  const [relationships, setRelationships] = useState<ModelRelationship[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [magicDrawStatus, setMagicDrawStatus] = useState<MagicDrawStatus | null>(null);
  const [magicDrawResult, setMagicDrawResult] = useState<MagicDrawPublishResult | null>(null);
  const [magicDrawSaveResult, setMagicDrawSaveResult] = useState<MagicDrawBridgeOperationResult | null>(null);
  const [magicDrawModelResult, setMagicDrawModelResult] = useState<MagicDrawBridgeOperationResult | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const dialogueStreamRef = useRef<HTMLDivElement | null>(null);

  const conversationPayload = useMemo(
    () =>
      dialogue
        .filter((item) => item.context !== false && (item.role === 'user' || item.role === 'assistant'))
        .map((item) => ({ role: item.role, content: item.content })),
    [dialogue],
  );
  const sysmlText = projectResult?.sysml_text || emptySysmlText(projectName);
  const bridgeOnline = !!magicDrawStatus?.bridge_available;

  useEffect(() => {
    refreshMagicDrawStatus();
    const timer = window.setInterval(refreshMagicDrawStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const stream = dialogueStreamRef.current;
    if (stream) {
      stream.scrollTop = stream.scrollHeight;
    }
  }, [dialogue]);

  const addEvent = (title: string, detail: string, status: FlowStatus = 'done') => {
    setEvents((current) => [
      { id: `${Date.now()}-${Math.random()}`, title, detail, status, time: nowTime() },
      ...current.slice(0, 9),
    ]);
  };

  const appendDialogue = (entry: Omit<DialogueMessage, 'id'> & { id?: string }) => {
    setDialogue((current) => [...current, { ...entry, id: entry.id || `${Date.now()}-${Math.random()}` }]);
  };

  const updateDialogue = (id: string, updater: (entry: DialogueMessage) => DialogueMessage) => {
    setDialogue((current) => current.map((item) => (item.id === id ? updater(item) : item)));
  };

  const resetModelPreview = () => {
    setProjectResult(null);
    setElements([]);
    setRelationships([]);
    setSelectedId(null);
    setMagicDrawResult(null);
    setMagicDrawSaveResult(null);
    setMagicDrawModelResult(null);
  };

  async function refreshMagicDrawStatus() {
    try {
      setMagicDrawStatus(await client.magicDrawStatus());
    } catch {
      setMagicDrawStatus(null);
    }
  }

  async function sendToAi() {
    const text = input.trim();
    if (!text) {
      message.warning('请先输入要让AI理解的设计内容');
      return;
    }

    appendDialogue({ role: 'user', title: '总体设计师输入', content: text });
    setInput('');
    setActiveAction('chat');

    addEvent('AI理解需求', '正在流式生成AI回复。', 'running');
    const assistantId = `${Date.now()}-${Math.random()}-assistant`;
    let streamedAnswer = '';
    appendDialogue({
      id: assistantId,
      role: 'assistant',
      title: 'AI回复',
      content: '',
      streaming: true,
    });

    try {
      await client.streamChat(text, 'chat', conversationPayload, {
        onDelta: (delta) => {
          streamedAnswer = mergeStreamContent(streamedAnswer, delta);
          updateDialogue(assistantId, (entry) => ({
            ...entry,
            content: cleanAiOutput(streamedAnswer),
          }));
        },
        onDone: (result) => {
          streamedAnswer = streamedAnswer || result.answer || '';
          updateDialogue(assistantId, (entry) => ({
            ...entry,
            content: cleanAiOutput(streamedAnswer),
            toolCalls: result.tool_calls,
            streaming: false,
          }));
        },
        onError: (detail) => {
          updateDialogue(assistantId, (entry) => ({
            ...entry,
            content: detail,
            streaming: false,
          }));
        },
      });
      addEvent('AI回复完成', '对话上下文已更新，可继续补充约束，也可直接生成SysML工程。');
      const nextConversation = [
        ...conversationPayload,
        { role: 'user', content: text },
        { role: 'assistant', content: cleanAiOutput(streamedAnswer) },
      ].filter((item) => item.content.trim());
      const intent = await classifySysmlIntent(text, nextConversation);
      if (intent.should_generate) {
        resetModelPreview();
        addEvent('识别为建模任务', intent.reason || '将根据当前对话同步右侧SysML工程。');
        await runGenerateProject({
          prompt: text,
          conversation: nextConversation,
          projectName: '',
          auto: true,
        });
      } else {
        addEvent('普通对话', intent.reason || '未触发SysML工程生成。');
      }
    } catch {
      updateDialogue(assistantId, (entry) => ({
        ...entry,
        content: 'AI 对话流式输出失败，请检查后端服务或大语言模型配置。',
        streaming: false,
      }));
      addEvent('AI对话失败', '请检查后端服务或大语言模型配置。', 'error');
      message.error('AI对话失败，请检查后端服务');
    } finally {
      setActiveAction(null);
    }
  }

    /*
    addEvent('AI理解需求', '已把当前设计描述发送给大语言模型，正在生成AI回复。', 'running');

    try {
      const result = await client.chat(text, 'chat');
      appendDialogue({
        role: 'assistant',
        title: 'AI回复',
        content: cleanAiOutput(result.answer),
        toolCalls: result.tool_calls,
      });
      addEvent('AI回复完成', '对话上下文已更新，可继续补充约束，也可直接生成SysML工程。');
    } catch {
      addEvent('AI对话失败', '请检查后端服务或大语言模型配置。', 'error');
      message.error('AI对话失败，请检查后端服务');
    } finally {
      setActiveAction(null);
    }
  }

    */
  async function generateProject() {
    await runGenerateProject();
  }

  async function runGenerateProject(options: {
    prompt?: string;
    conversation?: Array<{ role: string; content: string }>;
    projectName?: string;
    auto?: boolean;
  } = {}) {
    setActiveAction('generate');
    addEvent(options.auto ? '同步右侧模型' : '生成SysML工程', '后端正在基于当前对话上下文生成完整SysML工程包。', 'running');
    try {
      const sourceConversation = options.conversation || conversationPayload;
      const prompt = options.prompt ?? (input.trim() || sourceConversation.map((item) => item.content).join('\n'));
      const requestedProjectName = options.projectName !== undefined ? options.projectName : projectName;
      const result = await client.generateSysmlProject(requestedProjectName, prompt, sourceConversation);
      setProjectResult(result);
      setProjectName(result.project_name);
      setElements(result.elements);
      setRelationships(result.relationships);
      setSelectedId(result.elements[0]?.id ?? null);
      setMagicDrawResult(null);
      if (!options.auto) {
        appendDialogue({
          role: 'assistant',
          title: 'SysML工程已生成',
          content: `${result.summary}\n\n已生成SysML textual view，右侧MagicDraw画布块和工程包预览已同步刷新。`,
          context: false,
        });
        message.success('完整SysML工程已生成');
      }
      addEvent(options.auto ? '右侧模型已同步' : 'SysML工程完成', `${result.elements.length}个元素、${result.relationships.length}条关系已生成并回显。`);
      return result;
    } catch {
      addEvent('SysML工程生成失败', '请检查后端服务或输入内容。', 'error');
      message.error('SysML工程生成失败');
      return null;
    } finally {
      setActiveAction(null);
    }
  }

  async function publishMagicDraw() {
    if (!elements.length) {
      message.warning('请先生成SysML工程');
      return;
    }
    await runPublishMagicDraw(elements, relationships, projectName, projectResult?.diagram_views || []);
  }

  async function generateAndPublish() {
    const result = await runGenerateProject();
    if (result) {
      await runPublishMagicDraw(result.elements, result.relationships, result.project_name, result.diagram_views || []);
    }
  }

  async function runPublishMagicDraw(
    sourceElements: ModelElement[],
    sourceRelationships: ModelRelationship[],
    packageName: string,
    diagramViews: SysMLDiagramView[] = [],
  ) {
    setActiveAction('magicdraw');
    addEvent('推送MagicDraw', '正在打包SysML工程，并调用MagicDraw Bridge导入接口。', 'running');
    try {
      const result = await client.publishMagicDraw(sourceElements, sourceRelationships, packageName, diagramViews);
      setMagicDrawResult(result);
      await refreshMagicDrawStatus();
      if (result.mode === 'bridge') {
        try {
          setMagicDrawModelResult(await client.readMagicDrawCurrentModel());
        } catch {
          // Import success is still useful even if the follow-up model read fails.
        }
      }
      appendDialogue({
        role: 'assistant',
        title: 'MagicDraw返回结果',
        content:
          result.mode === 'bridge'
            ? `MagicDraw Bridge已接收工程：${bridgeSummary(result.bridge_response)}`
            : `Bridge未连接，已生成本地MagicDraw交换包：${result.files?.directory || '见返回文件列表'}`,
        context: false,
      });
      addEvent(
        result.mode === 'bridge' ? 'MagicDraw已创建模型' : '已生成MagicDraw交换包',
        result.mode === 'bridge' ? bridgeSummary(result.bridge_response) : result.files?.directory || result.message,
      );
      message.success(result.mode === 'bridge' ? '已推送到MagicDraw Bridge' : '已生成MagicDraw交换包');
    } catch {
      addEvent('MagicDraw推送失败', '请检查后端、Bridge插件、MagicDraw是否启动并进入主界面。', 'error');
      message.error('MagicDraw推送失败');
    } finally {
      setActiveAction(null);
    }
  }

  async function saveMagicDrawProject() {
    setActiveAction('save-magicdraw');
    addEvent('保存MagicDraw工程', '正在通过Bridge请求MagicDraw保存当前工程。', 'running');
    try {
      const result = await client.saveMagicDrawProject();
      setMagicDrawSaveResult(result);
      const ok = !!result.available && result.bridge_response?.status !== 'error';
      addEvent(ok ? 'MagicDraw工程已保存' : 'MagicDraw保存失败', bridgeSummary(result.bridge_response) || result.message, ok ? 'done' : 'error');
      ok ? message.success('MagicDraw工程已保存') : message.error(result.message);
    } catch {
      addEvent('MagicDraw保存失败', '请检查Bridge连接和MagicDraw工程状态。', 'error');
      message.error('MagicDraw保存失败');
    } finally {
      setActiveAction(null);
    }
  }

  async function readMagicDrawCurrentModel() {
    setActiveAction('read-magicdraw');
    addEvent('读取MagicDraw模型', '正在从Bridge拉取MagicDraw当前工程的真实模型状态。', 'running');
    try {
      const result = await client.readMagicDrawCurrentModel();
      setMagicDrawModelResult(result);
      const response = result.bridge_response || {};
      const countText = `元素${numberValue(response.element_count)}个，关系${numberValue(response.relationship_count)}条。`;
      addEvent('MagicDraw模型已读取', countText);
      message.success('已读取MagicDraw当前模型');
    } catch {
      addEvent('MagicDraw模型读取失败', '请检查Bridge连接和MagicDraw工程状态。', 'error');
      message.error('MagicDraw模型读取失败');
    } finally {
      setActiveAction(null);
    }
  }

  return (
    <div className="page-stack model1-page">
      <div className="page-heading">
        <div>
          <h1>AI工作台</h1>
          <p>全新流程：只根据AI对话生成完整SysML工程，随后推送MagicDraw，并把MagicDraw返回的工程包、Bridge响应、元素和关系全部回显到本页面。</p>
        </div>
        <Space size={10} wrap>
          <Badge status={bridgeOnline ? 'success' : 'warning'} text={bridgeOnline ? 'MagicDraw Bridge已连接' : 'MagicDraw Bridge未连接'} />
          <Button icon={<ReloadOutlined />} onClick={refreshMagicDrawStatus}>
            刷新Bridge
          </Button>
          <Button icon={<SaveOutlined />} disabled={!bridgeOnline} loading={activeAction === 'save-magicdraw'} onClick={saveMagicDrawProject}>
            保存MagicDraw
          </Button>
          <Button icon={<DatabaseOutlined />} disabled={!bridgeOnline} loading={activeAction === 'read-magicdraw'} onClick={readMagicDrawCurrentModel}>
            读取模型
          </Button>
        </Space>
      </div>

      <div className="model1-workbench">
        <section className="content-band model1-left-panel">
          <div className="status-line">
            <Typography.Title level={5}>
              <RobotOutlined /> AI对话建模流
            </Typography.Title>
            <Tag color={activeAction === 'chat' ? 'processing' : 'blue'}>{activeAction === 'chat' ? '对话中' : '可对话'}</Tag>
          </div>

          <label className="form-field">
            工程包名称
            <Input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </label>

          <div className="dialogue-stream model1-dialogue" ref={dialogueStreamRef} aria-label="AI dialogue for SysML project generation">
            {dialogue.map((item) => (
              <div className={`dialogue-message ${item.role}`} key={item.id}>
                <div className="dialogue-message-top">
                  <span>{item.title}</span>
                  <Tag color={item.role === 'user' ? 'blue' : item.role === 'assistant' ? 'green' : 'default'}>
                    {item.role === 'user' ? '人工' : item.role === 'assistant' ? 'AI' : '系统'}
                  </Tag>
                </div>
                <div className="dialogue-message-body">
                  <MarkdownMessage content={cleanAiOutput(item.content)} streaming={item.streaming} />
                </div>
                {!!item.toolCalls?.length && (
                  <div className="dialogue-tool-list">
                    {item.toolCalls.map((tool) => (
                      <Tag color={tool.status === 'success' ? 'green' : 'gold'} key={`${item.id}-${tool.tool}`}>
                        {tool.tool}: {tool.summary}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="prompt-console">
            <TextArea value={input} rows={6} placeholder={defaultPrompt} onChange={(event) => setInput(event.target.value)} />
            <div className="toolbar">
              <Button type="primary" icon={<SendOutlined />} loading={activeAction === 'chat'} onClick={sendToAi}>
                发送给AI
              </Button>
              <Button icon={<CodeOutlined />} loading={activeAction === 'generate'} onClick={generateProject}>
                生成完整SysML工程
              </Button>
              <Button icon={<ExportOutlined />} loading={activeAction === 'magicdraw'} disabled={!elements.length} onClick={publishMagicDraw}>
                推送MagicDraw
              </Button>
              <Button icon={<CloudUploadOutlined />} loading={activeAction === 'generate' || activeAction === 'magicdraw'} onClick={generateAndPublish}>
                生成并推送
              </Button>
            </div>
          </div>

          <div className="pipeline-feed model1-events">
            <div className="selector-title">处理流水</div>
            {events.map((item) => (
              <div className={`pipeline-event ${item.status}`} key={item.id}>
                <span className="event-dot" />
                <div>
                  <div className="event-title">
                    {item.title}
                    <span>{item.time}</span>
                  </div>
                  <div className="event-detail">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="model1-right-panel">
          <div className="content-band page-stack">
            <div className="magicdraw-board-heading">
              <div>
                <Typography.Title level={5}>
                  <ApartmentOutlined /> AI到MagicDraw工程回显
                </Typography.Title>
                <Typography.Text type="secondary">左侧对话驱动建模，右侧同步展示SysML文本、MagicDraw画布块、工程包和Bridge返回。</Typography.Text>
              </div>
              <Tag color={magicDrawResult?.mode === 'bridge' ? 'green' : magicDrawResult ? 'gold' : 'default'}>
                {magicDrawResult ? `MagicDraw: ${magicDrawResult.mode}` : '等待推送'}
              </Tag>
            </div>

            <div className="pipeline-strip">
              <PipelineStep title="AI对话" done={dialogue.some((item) => item.role === 'user')} active={activeAction === 'chat'} />
              <PipelineStep title="生成SysML" done={elements.length > 0} active={activeAction === 'generate'} />
              <PipelineStep title="推送MagicDraw" done={!!magicDrawResult} active={activeAction === 'magicdraw'} />
              <PipelineStep title="结果回显" done={!!magicDrawResult} />
            </div>

            {projectResult && (
              <Alert
                type="success"
                showIcon
                message={projectResult.summary}
                description={projectResult.assumptions.join('；')}
              />
            )}
          </div>

          <SysmlLivePanel
            sysmlText={sysmlText}
            selectedId={selectedId}
          />

          <MagicDrawCanvasPanel
            result={magicDrawResult}
            elements={elements}
            relationships={relationships}
            packageName={projectName}
            bridgeOnline={bridgeOnline}
          />

          <MagicDrawReturnPanel result={magicDrawResult} elements={elements} relationships={relationships} packageName={projectName} />

          <MagicDrawLiveModelPanel modelResult={magicDrawModelResult} saveResult={magicDrawSaveResult} />
        </section>
      </div>
    </div>
  );
}

function PipelineStep({ title, done, active }: { title: string; done?: boolean; active?: boolean }) {
  return (
    <div className={`pipeline-step ${done ? 'done' : active ? 'running' : ''}`}>
      {done ? <CheckCircleOutlined /> : active ? <ClockCircleOutlined /> : <PlayCircleOutlined />}
      <span>{title}</span>
    </div>
  );
}

function SysmlLivePanel({
  sysmlText,
  selectedId,
}: {
  sysmlText: string;
  selectedId: string | null;
}) {
  const lines = sysmlText.split('\n');
  return (
    <div className="content-band sysml-correspondence">
      <div className="magicdraw-board-heading">
        <div>
          <Typography.Title level={5}>
            <BranchesOutlined /> AI创建的SysML文本
          </Typography.Title>
          <Typography.Text type="secondary">这里仅展示AI生成的SysML textual view。</Typography.Text>
        </div>
        <Tag color={selectedId ? 'blue' : 'default'}>{selectedId || '未选中'}</Tag>
      </div>

      <div className="sysml-text-pane">
        <div className="pane-title">SysML textual view</div>
        <div className="sysml-code-lines model1-code-lines" aria-label="Generated SysML text">
          {lines.map((line, index) => {
            const selected = !!selectedId && line.includes(selectedId);
            return (
              <div className={`sysml-code-line ${selected ? 'selected' : ''}`} key={`${index}-${line}`}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <code>{line || ' '}</code>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MagicDrawCanvasPanel({
  result,
  elements,
  relationships,
  packageName,
  bridgeOnline,
}: {
  result: MagicDrawPublishResult | null;
  elements: ModelElement[];
  relationships: ModelRelationship[];
  packageName: string;
  bridgeOnline: boolean;
}) {
  const payload = result?.exchange_payload;
  const bridgeResponse = result?.bridge_response || null;
  const layout = payload?.diagram_layout;
  const drawing = layout ? buildCanvasDrawing(layout) : null;
  const hasDrawing = !!drawing?.nodes.length;
  const bridgeElements = bridgeTotal(bridgeResponse, 'elements');
  const bridgeRelationships = bridgeTotal(bridgeResponse, 'relationships');
  const elementCount = bridgeElements || payload?.elements?.length || elements.length;
  const relationshipCount = bridgeRelationships || payload?.relationships?.length || relationships.length;
  const diagramName = String(bridgeResponse?.diagram || bridgeResponse?.diagram_name || layout?.diagram_name || payload?.diagram_name || 'AI_MBSE_Trace_View');
  const projectLabel = String(bridgeResponse?.project || payload?.root_package || packageName);
  const statusLabel = result ? (hasDrawing ? '统一画布回显' : '缺少画布数据') : elements.length ? '等待推送MagicDraw' : '等待建模';
  const note = result
    ? hasDrawing
      ? '下图严格按照后端生成的统一 diagram_layout 渲染；MagicDraw Bridge 也应使用同一份布局摆放图元。'
      : '本次返回结果中没有 diagram_layout，因此前端不自行生成图。请重新生成并推送。'
    : elements.length
      ? '已生成SysML工程，点击“推送MagicDraw”后才会返回统一画布数据并绘图。'
      : '先通过AI对话生成完整SysML工程。';

  return (
    <div className="content-band page-stack">
      <div className="status-line">
        <Typography.Title level={5}>
          <ApartmentOutlined /> MagicDraw画布块
        </Typography.Title>
        <Tag color={result?.mode === 'bridge' ? 'green' : result ? 'gold' : bridgeOnline ? 'blue' : 'default'}>{statusLabel}</Tag>
      </div>

      <div className="model1-magicdraw-canvas" aria-label="MagicDraw canvas status block">
        <div className="magicdraw-canvas-topbar">
          <span>package / {projectLabel}</span>
          <Tag color={bridgeOnline ? 'green' : 'orange'}>{bridgeOnline ? 'Bridge在线' : 'Bridge未连接'}</Tag>
        </div>
        <div className={`magicdraw-canvas-frame ${hasDrawing ? 'has-drawing' : ''}`}>
          {hasDrawing ? (
            <svg
              className="magicdraw-drawing-svg"
              width={drawing!.width}
              height={drawing!.height}
              viewBox={`0 0 ${drawing!.width} ${drawing!.height}`}
              role="img"
              aria-label="Frontend MagicDraw model drawing"
            >
              <defs>
                <marker id="model1-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
                  <path d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              <g className="magicdraw-drawing-links">
                {drawing!.edges.map((edge) => (
                  <g className="magicdraw-drawing-link" key={edge.id}>
                    <path d={edge.path} markerEnd="url(#model1-arrow)" />
                    <text x={edge.labelX} y={edge.labelY}>
                      {edge.label}
                    </text>
                  </g>
                ))}
              </g>
              <g className="magicdraw-drawing-nodes">
                {drawing!.nodes.map((node) => (
                  <g className={`magicdraw-drawing-node ${node.cssType}`} key={node.id}>
                    {node.shape === 'ellipse' ? (
                      <ellipse cx={node.x + node.width / 2} cy={node.y + node.height / 2} rx={node.width / 2} ry={node.height / 2} />
                    ) : (
                      <rect x={node.x} y={node.y} width={node.width} height={node.height} rx={node.shape === 'soft' ? 14 : 3} />
                    )}
                    <text className="node-stereo" x={node.x + node.width / 2} y={node.y + 17}>
                      {node.stereotype}
                    </text>
                    {node.lines.map((line, index) => (
                      <text className="node-name" x={node.x + node.width / 2} y={node.y + 38 + index * 15} key={`${node.id}-${line}`}>
                        {line}
                      </text>
                    ))}
                  </g>
                ))}
              </g>
            </svg>
          ) : (
            <div className="magicdraw-canvas-state">
              <ApartmentOutlined />
              <strong>MagicDraw画布等待建模</strong>
              <span>{note}</span>
            </div>
          )}
        </div>
        <div className="magicdraw-canvas-footer">
          <span>{note}</span>
        </div>
        <div className="magicdraw-canvas-metrics">
          <div>
            <span>工程</span>
            <strong>{projectLabel}</strong>
          </div>
          <div>
            <span>视图</span>
            <strong>{diagramName}</strong>
          </div>
          <div>
            <span>元素</span>
            <strong>{elementCount}</strong>
          </div>
          <div>
            <span>关系</span>
            <strong>{relationshipCount}</strong>
          </div>
        </div>
      </div>
    </div>
  );
}

function MagicDrawReturnPanel({
  result,
  elements,
  relationships,
  packageName,
}: {
  result: MagicDrawPublishResult | null;
  elements: ModelElement[];
  relationships: ModelRelationship[];
  packageName: string;
}) {
  const payload = result?.exchange_payload;
  const exchangeElements = payload?.elements || [];
  const exchangeRelationships = payload?.relationships || [];
  const fileRows = Object.entries(result?.files || {}).map(([key, value]) => ({ key, value }));

  if (!result) {
    return (
      <div className="content-band page-stack">
        <div className="status-line">
          <Typography.Title level={5}>
            <ExportOutlined /> MagicDraw返回结果
          </Typography.Title>
          <Tag color={elements.length ? 'blue' : 'default'}>{elements.length ? '等待推送' : '等待工程'}</Tag>
        </div>
        <Alert
          type="info"
          showIcon
          message="暂无MagicDraw返回"
          description={elements.length ? '点击“推送MagicDraw”后，这里会展示Bridge响应、交换包文件、元素表和关系表。' : '先通过AI对话生成SysML工程。'}
        />
      </div>
    );
  }

  const elementColumns: ColumnsType<MagicDrawExchangeElement> = [
    { title: 'Local ID', dataIndex: 'local_id', width: 120 },
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'type', width: 130, render: (value) => <Tag color={typeColor(String(value))}>{String(value)}</Tag> },
    { title: '分包', dataIndex: 'package', width: 150 },
    { title: 'Metaclass', dataIndex: 'metaclass', width: 130 },
    { title: 'Stereotype', dataIndex: 'stereotype', ellipsis: true },
    { title: '来源需求', dataIndex: 'source_requirement', width: 130 },
  ];

  const relationshipColumns: ColumnsType<MagicDrawExchangeRelationship> = [
    { title: '关系ID', dataIndex: 'local_id', width: 120 },
    { title: 'Source', dataIndex: 'source_name' },
    { title: '关系', dataIndex: 'stereotype', render: (value, item) => value || item.type },
    { title: '分包', dataIndex: 'package', width: 150 },
    { title: 'Target', dataIndex: 'target_name' },
    { title: 'Metaclass', dataIndex: 'metaclass', width: 130 },
  ];

  return (
    <div className="content-band page-stack">
      <div className="status-line">
        <Typography.Title level={5}>
          <ExportOutlined /> MagicDraw返回结果
        </Typography.Title>
        <Tag color={result.mode === 'bridge' ? 'green' : 'gold'}>{result.mode === 'bridge' ? 'Bridge已导入' : '本地交换包'}</Tag>
      </div>

      <Alert
        type={result.mode === 'bridge' ? 'success' : 'warning'}
        showIcon
        message={result.message}
        description={result.mode === 'bridge' ? bridgeSummary(result.bridge_response) : 'Bridge未连接时仍会生成真实交换包，可用于检查将要发给MagicDraw的数据。'}
      />

      <Tabs
        items={[
          {
            key: 'summary',
            label: 'Bridge回显',
            children: (
              <div className="page-stack">
                <Descriptions bordered column={{ xs: 1, md: 2 }}>
                  <Descriptions.Item label="Root Package">{payload?.root_package || packageName}</Descriptions.Item>
                  <Descriptions.Item label="模式">{result.mode}</Descriptions.Item>
                  <Descriptions.Item label="元素数">{exchangeElements.length || elements.length}</Descriptions.Item>
                  <Descriptions.Item label="关系数">{exchangeRelationships.length || relationships.length}</Descriptions.Item>
                  <Descriptions.Item label="Bridge响应" span={2}>
                    {bridgeSummary(result.bridge_response)}
                  </Descriptions.Item>
                </Descriptions>
                <pre className="mono-json">{JSON.stringify(result.bridge_response || {}, null, 2)}</pre>
              </div>
            ),
          },
          {
            key: 'files',
            label: '工程包文件',
            children: (
              <Table
                size="small"
                rowKey="key"
                dataSource={fileRows}
                pagination={false}
                columns={[
                  { title: '文件', dataIndex: 'key', width: 160 },
                  { title: '路径', dataIndex: 'value', render: (value) => <Typography.Text copyable>{String(value)}</Typography.Text> },
                ]}
              />
            ),
          },
          {
            key: 'elements',
            label: '元素',
            children: (
              <Table<MagicDrawExchangeElement>
                size="small"
                rowKey={(item) => item.local_id || item.name || 'element'}
                dataSource={exchangeElements}
                columns={elementColumns}
                scroll={{ x: 980 }}
                pagination={{ pageSize: 8 }}
              />
            ),
          },
          {
            key: 'relationships',
            label: '关系',
            children: (
              <Table<MagicDrawExchangeRelationship>
                size="small"
                rowKey={(item) => item.local_id || item.name || `${item.source}-${item.target}-${item.type}`}
                dataSource={exchangeRelationships}
                columns={relationshipColumns}
                scroll={{ x: 900 }}
                pagination={{ pageSize: 8 }}
              />
            ),
          },
          {
            key: 'payload',
            label: '原始Payload',
            children: <pre className="mono-json model1-payload-json">{JSON.stringify(payload || {}, null, 2)}</pre>,
          },
        ]}
      />
    </div>
  );
}

function MagicDrawLiveModelPanel({
  modelResult,
  saveResult,
}: {
  modelResult: MagicDrawBridgeOperationResult | null;
  saveResult: MagicDrawBridgeOperationResult | null;
}) {
  const model = modelResult?.bridge_response || {};
  const elements = recordArray(model.elements);
  const relationships = recordArray(model.relationships);
  const diagrams = recordArray(model.diagrams);
  const elementColumns: ColumnsType<Record<string, unknown>> = [
    { title: 'Local ID', dataIndex: 'local_id', width: 120 },
    { title: 'MagicDraw ID', dataIndex: 'magicdraw_id', width: 190, ellipsis: true },
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'type', width: 130, render: (value) => <Tag color={typeColor(String(value))}>{String(value || '-')}</Tag> },
    { title: 'Qualified Name', dataIndex: 'qualified_name', ellipsis: true },
  ];
  const relationshipColumns: ColumnsType<Record<string, unknown>> = [
    { title: 'Local ID', dataIndex: 'local_id', width: 120 },
    { title: 'MagicDraw ID', dataIndex: 'magicdraw_id', width: 190, ellipsis: true },
    { title: 'Source', dataIndex: 'source_name' },
    { title: 'Target', dataIndex: 'target_name' },
    { title: 'Qualified Name', dataIndex: 'qualified_name', ellipsis: true },
  ];

  return (
    <div className="content-band page-stack">
      <div className="status-line">
        <Typography.Title level={5}>
          <DatabaseOutlined /> MagicDraw真实模型状态
        </Typography.Title>
        <Tag color={modelResult?.available ? 'green' : saveResult ? 'blue' : 'default'}>
          {modelResult ? '已读取' : saveResult ? '已保存' : '等待读取'}
        </Tag>
      </div>

      {!modelResult && !saveResult ? (
        <Alert
          type="info"
          showIcon
          message="尚未读取MagicDraw当前模型"
          description="点击页面右上角“读取模型”后，这里会展示MagicDraw工程中的真实元素ID、Qualified Name、关系和图。"
        />
      ) : (
        <Tabs
          items={[
            {
              key: 'summary',
              label: '状态摘要',
              children: (
                <div className="page-stack">
                  <Descriptions bordered column={{ xs: 1, md: 2 }}>
                    <Descriptions.Item label="工程">{String(model.project || '-')}</Descriptions.Item>
                    <Descriptions.Item label="工程ID">{String(model.project_id || '-')}</Descriptions.Item>
                    <Descriptions.Item label="元素数">{String(model.element_count ?? elements.length)}</Descriptions.Item>
                    <Descriptions.Item label="关系数">{String(model.relationship_count ?? relationships.length)}</Descriptions.Item>
                    <Descriptions.Item label="保存回执" span={2}>
                      {saveResult ? JSON.stringify(saveResult.bridge_response || saveResult) : '-'}
                    </Descriptions.Item>
                  </Descriptions>
                </div>
              ),
            },
            {
              key: 'elements',
              label: 'MagicDraw元素',
              children: (
                <Table<Record<string, unknown>>
                  size="small"
                  rowKey={(item) => recordKey(item)}
                  dataSource={elements}
                  columns={elementColumns}
                  scroll={{ x: 1100 }}
                  pagination={{ pageSize: 8 }}
                />
              ),
            },
            {
              key: 'relationships',
              label: 'MagicDraw关系',
              children: (
                <Table<Record<string, unknown>>
                  size="small"
                  rowKey={(item) => recordKey(item)}
                  dataSource={relationships}
                  columns={relationshipColumns}
                  scroll={{ x: 1100 }}
                  pagination={{ pageSize: 8 }}
                />
              ),
            },
            {
              key: 'diagrams',
              label: 'MagicDraw图',
              children: (
                <Table<Record<string, unknown>>
                  size="small"
                  rowKey={(item) => recordKey(item)}
                  dataSource={diagrams}
                  pagination={false}
                  columns={[
                    { title: 'Diagram ID', dataIndex: 'id', width: 220, ellipsis: true },
                    { title: '名称', dataIndex: 'name' },
                  ]}
                />
              ),
            },
          ]}
        />
      )}
    </div>
  );
}

interface CanvasDrawingNode {
  id: string;
  type: string;
  cssType: string;
  stereotype: string;
  shape: 'rect' | 'soft' | 'ellipse';
  lines: string[];
  column: number;
  row: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface CanvasDrawingEdge {
  id: string;
  label: string;
  path: string;
  labelX: number;
  labelY: number;
}

function buildCanvasDrawing(layout: MagicDrawDiagramLayout) {
  const nodes = (layout.nodes || []).map<CanvasDrawingNode>((node) => ({
    id: String(node.id || node.element_id || node.label || ''),
    type: String(node.type || 'Block'),
    cssType: String(node.type || 'Block').toLowerCase(),
    stereotype: node.stereotype_label || canvasStereotype(String(node.type || 'Block')),
    shape: canvasShape(String(node.shape || node.type || 'rect')),
    lines: splitCanvasLabel(node.label || node.name || node.id || 'UnnamedElement', 18, 2),
    column: Number(node.column || 0),
    row: Number(node.row || 0),
    x: Number(node.x || 0),
    y: Number(node.y || 0),
    width: Number(node.width || 220),
    height: Number(node.height || 72),
  }));
  const edges = (layout.edges || []).map<CanvasDrawingEdge>((edge) => ({
    id: String(edge.id || edge.relationship_id || `${edge.source}-${edge.target}`),
    label: truncateCanvasText(String(edge.label || edge.type || 'trace'), 18),
    path: canvasPathFromPoints(edge.points || []),
    labelX: Number(edge.label_x || edge.points?.[0]?.x || 0),
    labelY: Number(edge.label_y || edge.points?.[0]?.y || 0),
  }));

  return {
    nodes,
    edges,
    width: Number(layout.width || 980),
    height: Number(layout.height || 520),
  };
}

function canvasPathFromPoints(points: MagicDrawLayoutEdge['points']) {
  if (!points?.length) return '';
  if (points.length >= 4) {
    const [start, control1, control2, end] = points;
    return `M ${start.x} ${start.y} C ${control1.x} ${control1.y}, ${control2.x} ${control2.y}, ${end.x} ${end.y}`;
  }
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
}

function canvasStereotype(type: string) {
  if (type === 'Activity') return '«activity»';
  if (type === 'Block') return '«block»';
  if (type === 'Requirement') return '«requirement»';
  if (type === 'UseCase') return '«use case»';
  if (type === 'Interface') return '«interface»';
  if (type === 'ConstraintBlock') return '«constraint»';
  return '«element»';
}

function canvasShape(value: string): CanvasDrawingNode['shape'] {
  if (value === 'ellipse' || value === 'UseCase') return 'ellipse';
  if (value === 'soft' || value === 'Interface') return 'soft';
  return 'rect';
}

function splitCanvasLabel(value: string, size: number, maxLines: number) {
  const text = String(value || '').trim();
  const lines: string[] = [];
  for (let index = 0; index < text.length && lines.length < maxLines; index += size) {
    lines.push(text.slice(index, index + size));
  }
  if (text.length > size * maxLines && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, Math.max(1, size - 1))}…`;
  }
  return lines.length ? lines : ['Unnamed'];
}

function truncateCanvasText(value: string, size: number) {
  const text = String(value || '').trim();
  return text.length > size ? `${text.slice(0, size - 1)}…` : text;
}

function emptySysmlText(projectName: string) {
  return [`package ${sysmlIdentifier(projectName)} {`, '  // 等待AI对话生成完整SysML工程', '}'].join('\n');
}

function sysmlIdentifier(value: string) {
  const normalized = String(value || 'AI_MBSE_Project')
    .trim()
    .replace(/[^A-Za-z0-9_\u4e00-\u9fa5]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return normalized || 'AI_MBSE_Project';
}

function typeColor(type: string) {
  if (type === 'Requirement') return 'purple';
  if (type === 'Block') return 'blue';
  if (type === 'UseCase') return 'green';
  if (type === 'Interface') return 'cyan';
  if (type === 'Activity') return 'orange';
  if (type === 'ConstraintBlock') return 'magenta';
  return 'default';
}

function bridgeSummary(response?: Record<string, unknown> | null) {
  if (!response) return '-';
  const status = String(response.status || response.mode || 'ok');
  const project = response.project ? `项目：${response.project}` : '';
  const elementsCreated = numberValue(response.elements_created);
  const elementsReused = numberValue(response.elements_reused);
  const relationshipsCreated = numberValue(response.relationships_created);
  const relationshipsReused = numberValue(response.relationships_reused);
  const elementTotal = elementsCreated + elementsReused;
  const relationshipTotal = relationshipsCreated + relationshipsReused;
  const elementText =
    response.elements_created !== undefined || response.elements_reused !== undefined
      ? `元素：总计${elementTotal}（新建${elementsCreated}，复用${elementsReused}）`
      : '';
  const relationshipText =
    response.relationships_created !== undefined || response.relationships_reused !== undefined
      ? `关系：总计${relationshipTotal}（新建${relationshipsCreated}，复用${relationshipsReused}）`
      : '';
  return [status, project, elementText, relationshipText].filter(Boolean).join('；') || 'MagicDraw已返回处理结果';
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object') : [];
}

function recordKey(item: Record<string, unknown>) {
  return String(item.magicdraw_id || item.qualified_name || item.local_id || item.id || item.name || JSON.stringify(item));
}

function bridgeTotal(response: Record<string, unknown> | null, scope: 'elements' | 'relationships') {
  if (!response) return 0;
  const created = numberValue(response[`${scope}_created`]);
  const reused = numberValue(response[`${scope}_reused`]);
  const explicitTotal = numberValue(response[`${scope}_total`]);
  return created + reused || explicitTotal;
}

function mergeStreamContent(current: string, incoming: string) {
  const chunk = String(incoming || '');
  if (!chunk) return current;
  if (!current) return chunk;
  if (chunk === current) return current;
  if (chunk.length > 12 && current.endsWith(chunk)) return current;
  if (chunk.startsWith(current)) return chunk;
  return `${current}${chunk}`;
}

async function classifySysmlIntent(messageText: string, conversation: Array<{ role: string; content: string }>): Promise<SysMLIntentResult> {
  try {
    return await client.classifySysmlIntent(messageText, conversation);
  } catch {
    return localSysmlIntent(messageText);
  }
}

function localSysmlIntent(messageText: string): SysMLIntentResult {
  const text = messageText.trim();
  const compact = text.replace(/\s+/g, '').toLowerCase();
  const trivialInputs = new Set(['在吗', '你好', '您好', 'hi', 'hello', 'hey', '谢谢', '多谢', '收到', 'ok', '好的', '你在吗']);
  if (trivialInputs.has(compact) || (compact.length <= 4 && !/(画|建|生成|模型|sysml|mbse)/i.test(compact))) {
    return {
      should_generate: false,
      intent: 'chat',
      confidence: 0.98,
      reason: '最新输入是寒暄或普通短句，不触发SysML工程生成。',
    };
  }

  const modelTerms = [
    'sysml',
    'mbse',
    'magicdraw',
    '模型',
    '系统',
    '总体',
    '工程',
    '建模',
    '需求',
    '模块',
    '用例',
    '接口',
    '活动',
    '约束',
    '关系',
    '追溯',
    '画布',
    '右侧',
    '方案',
    '飞机',
    '航空器',
    '飞行器',
    '无人机',
    '卫星',
    '星座',
    '雷达',
  ];
  const actionTerms = ['生成', '创建', '构建', '建立', '设计', '重建', '更新', '修改', '补充', '完善', '同步', '推送', '导入', '校验', '验证', '重新生成'];
  const lowerText = text.toLowerCase();
  const hasModelTerm = modelTerms.some((term) => lowerText.includes(term.toLowerCase()));
  const hasActionTerm = actionTerms.some((term) => text.includes(term));
  const asksHow = /(怎么|如何|为什么|是什么|能不能|是否|介绍|解释|说明|该如何)/.test(text);

  return {
    should_generate: hasModelTerm && hasActionTerm && !asksHow,
    intent: hasModelTerm && hasActionTerm && !asksHow ? 'sysml_generation' : 'chat',
    confidence: hasModelTerm && hasActionTerm ? 0.8 : 0.55,
    reason: hasModelTerm && hasActionTerm && !asksHow ? '识别到建模对象和生成/修改类动作。' : '未识别到明确的SysML工程生成或修改意图。',
  };
}

function cleanAiOutput(value: string) {
  return String(value || '')
    .split('\n')
    .filter((line) => {
      const text = line.trim();
      return !(
        text.startsWith('建模引导：我会围绕任务目标') ||
        text.includes('信息足够时，可以点击“生成完整SysML工程”') ||
        text.includes('信息足够时，可以点击"生成完整SysML工程"')
      );
    })
    .join('\n')
    .trim();
}

function nowTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
