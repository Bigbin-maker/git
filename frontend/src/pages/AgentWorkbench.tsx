import {
  ApartmentOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CloseOutlined,
  CompressOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EllipsisOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  FullscreenOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { App, Button, Input, Modal, Progress, Segmented, Select, Space, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { CSSProperties, ChangeEvent, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { client } from '../api/client';
import { MarkdownMessage } from '../components/MarkdownMessage';
import type {
  ChatMessage,
  ChangeImpactMatrixRow,
  ChangeImpactSandboxRequest,
  ChangeImpactSandboxResponse,
  DraftValidationIssue,
  DraftValidationReport,
  DiagramViewLayoutNode,
  KnowledgeBaseSummary,
  MagicDrawBridgeOperationResult,
  MagicDrawDiagramLayout,
  MagicDrawLayoutEdge,
  MagicDrawPublishResult,
  MagicDrawStatus,
  MergeConflictRecord,
  MergeRequestRecord,
  ModelElement,
  ModelRelationship,
  SysMLDiagramView,
  SysMLProjectGenerateResult,
  ToolCall,
} from '../types';

type ChatRole = 'assistant' | 'user' | 'system';
type WorkStatus =
  | 'idle'
  | 'chatting'
  | 'generating'
  | 'syncing'
  | 'reading'
  | 'simulating'
  | 'uploading'
  | 'accepting'
  | 'editing'
  | 'validating'
  | 'analyzing'
  | 'submitting'
  | 'merging';
type ResponseMode = 'fast' | 'deep' | 'review';
type KnowledgeMode = 'auto' | 'direct_chat' | 'knowledge_qa';
type PaneResizeTarget = keyof AgentPaneSizes;
type MagicDrawPushStage = 'preview' | 'release' | null;

interface AgentPaneSizes {
  project: number;
  chat: number;
  explorer: number;
  summary: number;
}

interface ChatAttachment {
  name: string;
  size: number;
  type: string;
  status?: string;
}

interface AttachedFile extends ChatAttachment {
  id: string;
  content: string;
  backendId?: number;
}

interface ProjectItem {
  id: string;
  name: string;
  workspace: string;
  prompt: string;
  protected?: boolean;
}

interface ChatBubble {
  id: string;
  role: ChatRole;
  content: string;
  time: string;
  state?: 'ok' | 'working';
  streaming?: boolean;
  attachments?: ChatAttachment[];
}

interface SyncRow {
  id: string;
  category: string;
  name: string;
  action: string;
  status: string;
  detail: string;
}

interface PreviewValidation {
  status: 'idle' | 'pass' | 'warn';
  issues: string[];
  elementCount: number;
  relationshipCount: number;
  layoutNodeCount: number;
  layoutEdgeCount: number;
}

interface ProjectWorkspace {
  prompt: string;
  chat: ChatBubble[];
  projectResult: SysMLProjectGenerateResult | null;
  publishResult: MagicDrawPublishResult | null;
  liveModel: MagicDrawBridgeOperationResult | null;
  selectedId: string | null;
  selectedRelationshipId: string | null;
  activeTab: string;
  lastSyncTime: string;
  simulationSummary: string;
  generationDuration: string;
  generatedAt: string;
  preReviewReport: DraftValidationReport | null;
  impactReport: ChangeImpactSandboxResponse | null;
}

interface AgentPersistedState {
  version: number;
  projects: ProjectItem[];
  activeProjectId: string;
  workspaces: Record<string, ProjectWorkspace>;
  mode: ResponseMode;
  knowledgeMode: KnowledgeMode;
  selectedMergeRequestId: number | null;
}

const defaultPaneSizes: AgentPaneSizes = {
  project: 230,
  chat: 360,
  explorer: 290,
  summary: 260,
};

const paneResizeConfig: Record<PaneResizeTarget, { min: number; max: number; reverse?: boolean }> = {
  project: { min: 190, max: 390 },
  chat: { min: 280, max: 560 },
  explorer: { min: 220, max: 520 },
  summary: { min: 220, max: 460, reverse: true },
};

const initialProjects: ProjectItem[] = [
  {
    id: 'leo-analysis',
    name: '卫星任务分析系统',
    workspace: '卫星任务分析系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'orbit-jump',
    name: '智能跨域系统',
    workspace: '智能跨域系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'uav-flight',
    name: '无人机飞控系统',
    workspace: '无人机飞控系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'radar-processing',
    name: '雷达信号处理系统',
    workspace: '雷达信号处理系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'aircraft-surveillance',
    name: '航空器监控系统',
    workspace: '航空器监控系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'ground-station',
    name: '地面站系统',
    workspace: '地面站系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'rocket-control',
    name: '火箭姿控控制系统',
    workspace: '火箭姿控控制系统',
    prompt: '',
    protected: true,
  },
  {
    id: 'environment-control',
    name: '空间环境监测系统',
    workspace: '空间环境监测系统',
    prompt: '',
    protected: true,
  },
];

interface AgentWorkbenchProps {
  sessionRole?: 'admin' | 'designer';
  workspace?: string;
}

export default function AgentWorkbench({ sessionRole = 'admin', workspace }: AgentWorkbenchProps) {
  const { message, modal } = App.useApp();
  const persistedState = useMemo(() => loadWorkbenchState(sessionRole, workspace), [sessionRole, workspace]);
  const initialProjectState = useMemo(() => normalizePersistedProjects(persistedState?.projects), [persistedState]);
  const [projects, setProjects] = useState<ProjectItem[]>(() => initialProjectState);
  const [activeProjectId, setActiveProjectId] = useState(() =>
    resolvePersistedActiveProjectId(persistedState?.activeProjectId, initialProjectState),
  );
  const [query, setQuery] = useState('');
  const [workspaces, setWorkspaces] = useState<Record<string, ProjectWorkspace>>(() =>
    hydratePersistedWorkspaces(initialProjectState, persistedState?.workspaces),
  );
  const [mode, setMode] = useState<ResponseMode>(persistedState?.mode || 'deep');
  const [knowledgeMode, setKnowledgeMode] = useState<KnowledgeMode>(persistedState?.knowledgeMode || 'auto');
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeBaseSummary | null>(null);
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [status, setStatus] = useState<WorkStatus>('idle');
  const [pushStage, setPushStage] = useState<MagicDrawPushStage>(null);
  const [magicDrawStatus, setMagicDrawStatus] = useState<MagicDrawStatus | null>(null);
  const [paneSizes, setPaneSizes] = useState<AgentPaneSizes>(loadPaneSizes);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectName, setEditingProjectName] = useState('');
  const [preReviewOpen, setPreReviewOpen] = useState(false);
  const [internalDiagramOpen, setInternalDiagramOpen] = useState(false);
  const [internalDiagramFocusId, setInternalDiagramFocusId] = useState<string | null>(null);
  const [internalDiagramViews, setInternalDiagramViews] = useState<Record<string, SysMLDiagramView>>({});
  const [internalDiagramLoading, setInternalDiagramLoading] = useState(false);
  const [internalDiagramError, setInternalDiagramError] = useState('');
  const [mergeRequests, setMergeRequests] = useState<MergeRequestRecord[]>([]);
  const [selectedMergeRequestId, setSelectedMergeRequestId] = useState<number | null>(persistedState?.selectedMergeRequestId || null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const knowledgeFileInputRef = useRef<HTMLInputElement | null>(null);
  const chatStreamRef = useRef<HTMLDivElement | null>(null);
  const streamingContentRef = useRef<HTMLDivElement | null>(null);

  const isWorkspaceScoped = sessionRole === 'designer' && !!workspace;
  const authorizedProjects = isWorkspaceScoped ? projects.filter((item) => item.workspace === workspace) : projects;
  const activeProject = authorizedProjects.find((item) => item.id === activeProjectId) || authorizedProjects[0] || projects[0];
  const activeProjectAllowed = authorizedProjects.some((item) => item.id === activeProjectId);
  const firstAuthorizedProjectId = authorizedProjects[0]?.id;
  const activeWorkspaceId = activeProject.id;
  const activeWorkspace = workspaces[activeWorkspaceId] || createWorkspace(activeProject);
  const prompt = activeWorkspace.prompt;
  const chat = activeWorkspace.chat;
  const projectResult = activeWorkspace.projectResult;
  const publishResult = activeWorkspace.publishResult;
  const liveModel = activeWorkspace.liveModel;
  const selectedId = activeWorkspace.selectedId;
  const selectedRelationshipId = activeWorkspace.selectedRelationshipId;
  const activeTab = activeWorkspace.activeTab;
  const lastSyncTime = activeWorkspace.lastSyncTime;
  const simulationSummary = activeWorkspace.simulationSummary;
  const generationDuration = activeWorkspace.generationDuration;
  const generatedAt = activeWorkspace.generatedAt;
  const preReviewReport = activeWorkspace.preReviewReport;
  const impactReport = activeWorkspace.impactReport;
  const elements = projectResult?.elements || [];
  const relationships = projectResult?.relationships || [];
  const internalDiagramFocus = useMemo(
    () => (projectResult ? resolveFocusedBlock(elements, relationships, selectedId) : null),
    [elements, projectResult, relationships, selectedId],
  );
  const dialogInternalDiagramFocus = internalDiagramFocusId ? elements.find((item) => item.id === internalDiagramFocusId) || internalDiagramFocus : internalDiagramFocus;
  const activeInternalDiagramView = dialogInternalDiagramFocus ? internalDiagramViews[dialogInternalDiagramFocus.id] || null : null;
  const selectedRelationship = relationships.find((item) => item.id === selectedRelationshipId) || null;
  const editableRelationship = selectedRelationship || relationships[0] || null;
  const editableElement = elements.find((item) => item.id === selectedId) || elements[0] || null;
  const bridgeOnline = !!magicDrawStatus?.bridge_available;
  const bridgeProjectOpen = magicDrawStatus?.project_open ?? null;
  const bridgeProjectName = magicDrawStatus?.project_name || '';
  const bridgeProjectPathConfigured = !!magicDrawStatus?.project_path_configured;
  const visibleProjects = authorizedProjects.filter((item) => item.name.toLowerCase().includes(query.trim().toLowerCase()));
  const syncRows = useMemo(() => buildSyncRows(elements, relationships, publishResult), [elements, relationships, publishResult]);
  const groupedElements = useMemo(() => groupElements(elements), [elements]);
  const summary = useMemo(() => buildSummary(elements, relationships, publishResult, liveModel), [elements, relationships, publishResult, liveModel]);
  const previewValidation = useMemo(() => buildPreviewValidation(projectResult, null), [projectResult]);
  const workflow = useMemo(() => buildWorkflow(projectResult, publishResult, previewValidation, status), [projectResult, publishResult, previewValidation, status]);
  const canGenerateModel =
    status !== 'generating' &&
    status !== 'chatting' &&
    status !== 'editing' &&
    status !== 'accepting' &&
    status !== 'validating' &&
    status !== 'analyzing' &&
    status !== 'submitting' &&
    status !== 'merging' &&
    status !== 'syncing';
  const selectedMergeRequest =
    mergeRequests.find((item) => item.id === selectedMergeRequestId) || mergeRequests[0] || null;
  const canPreviewPushModel = !!projectResult && projectResult.draft_status !== 'rejected';
  const canPushModel = !!projectResult && isDraftAccepted(projectResult);
  const conversationPayload = useMemo<ChatMessage[]>(
    () =>
      chat
        .filter((item) => (item.role === 'user' || item.role === 'assistant') && item.content.trim())
        .slice(-10)
        .map((item) => ({ role: item.role, content: item.content })),
    [chat],
  );
  const stationStyle = {
    '--agent-project-width': `${paneSizes.project}px`,
    '--agent-chat-width': `${paneSizes.chat}px`,
    '--agent-explorer-width': `${paneSizes.explorer}px`,
    '--agent-summary-width': `${paneSizes.summary}px`,
  } as CSSProperties;

  const resizeHandle = (target: PaneResizeTarget, label: string) => (
    <div
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemax={paneResizeConfig[target].max}
      aria-valuemin={paneResizeConfig[target].min}
      aria-valuenow={paneSizes[target]}
      className="agent-resizer"
      onDoubleClick={() => resetPaneSize(target)}
      onPointerDown={(event) => startPaneResize(event, target)}
      role="separator"
      tabIndex={0}
      title={`${label}，双击恢复默认`}
    />
  );

  function updateActiveWorkspace(updater: (current: ProjectWorkspace) => ProjectWorkspace) {
    setWorkspaces((current) => {
      const existing = current[activeWorkspaceId] || createWorkspace(activeProject);
      return { ...current, [activeWorkspaceId]: updater(existing) };
    });
  }

  function setPrompt(next: string | ((current: string) => string)) {
    updateActiveWorkspace((current) => ({ ...current, prompt: resolveNext(next, current.prompt) }));
  }

  function setChat(next: ChatBubble[] | ((current: ChatBubble[]) => ChatBubble[])) {
    updateActiveWorkspace((current) => ({ ...current, chat: resolveNext(next, current.chat) }));
  }

  function setProjectResult(next: SysMLProjectGenerateResult | null) {
    updateActiveWorkspace((current) => ({ ...current, projectResult: next, impactReport: null }));
  }

  function setPublishResult(next: MagicDrawPublishResult | null) {
    updateActiveWorkspace((current) => ({ ...current, publishResult: next }));
  }

  function setLiveModel(next: MagicDrawBridgeOperationResult | null) {
    updateActiveWorkspace((current) => ({ ...current, liveModel: next }));
  }

  function setSelectedId(next: string | null) {
    updateActiveWorkspace((current) => ({ ...current, selectedId: next, selectedRelationshipId: null }));
  }

  function setSelectedRelationshipId(next: string | null) {
    updateActiveWorkspace((current) => ({ ...current, selectedRelationshipId: next }));
  }

  function setActiveTab(next: string) {
    updateActiveWorkspace((current) => ({ ...current, activeTab: next }));
  }

  function setLastSyncTime(next: string) {
    updateActiveWorkspace((current) => ({ ...current, lastSyncTime: next }));
  }

  function setSimulationSummary(next: string) {
    updateActiveWorkspace((current) => ({ ...current, simulationSummary: next }));
  }

  function setGenerationDuration(next: string) {
    updateActiveWorkspace((current) => ({ ...current, generationDuration: next }));
  }

  function setGeneratedAt(next: string) {
    updateActiveWorkspace((current) => ({ ...current, generatedAt: next }));
  }

  function setPreReviewReport(next: DraftValidationReport | null) {
    updateActiveWorkspace((current) => ({ ...current, preReviewReport: next }));
  }

  function setImpactReport(next: ChangeImpactSandboxResponse | null) {
    updateActiveWorkspace((current) => ({ ...current, impactReport: next }));
  }

  useEffect(() => {
    saveWorkbenchState(sessionRole, workspace, {
      version: workbenchStorageVersion,
      projects,
      activeProjectId,
      workspaces,
      mode,
      knowledgeMode,
      selectedMergeRequestId,
    });
  }, [sessionRole, workspace, projects, activeProjectId, workspaces, mode, knowledgeMode, selectedMergeRequestId]);

  useEffect(() => {
    if (firstAuthorizedProjectId && !activeProjectAllowed) {
      setActiveProjectId(firstAuthorizedProjectId);
      setEditingProjectId(null);
      setEditingProjectName('');
      setQuery('');
    }
  }, [activeProjectAllowed, firstAuthorizedProjectId]);

  useEffect(() => {
    const load = async () => {
      try {
        setMagicDrawStatus(await client.magicDrawStatus());
      } catch {
        setMagicDrawStatus(null);
      }
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    refreshKnowledgeSummary();
  }, []);

  useEffect(() => {
    refreshMergeRequests();
  }, [sessionRole]);

  useEffect(() => {
    setAttachments([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (knowledgeFileInputRef.current) knowledgeFileInputRef.current.value = '';
    setEditingProjectId(null);
    setEditingProjectName('');
    setWorkspaces((current) => (current[activeWorkspaceId] ? current : { ...current, [activeWorkspaceId]: createWorkspace(activeProject) }));
  }, [activeWorkspaceId, activeProject]);

  useEffect(() => {
    savePaneSizes(paneSizes);
  }, [paneSizes]);

  useEffect(() => {
    setInternalDiagramViews(diagramViewsToInternalCache(projectResult?.diagram_views));
    setInternalDiagramFocusId(null);
    setInternalDiagramError('');
  }, [activeWorkspaceId, projectResult?.draft_id, projectResult?.project_name]);

  useEffect(() => {
    const hasStreamingMessage = chat.some((item) => item.streaming);
    if (!hasStreamingMessage) return;

    const scrollStreamingMessageToBottom = () => {
      if (chatStreamRef.current) {
        chatStreamRef.current.scrollTop = chatStreamRef.current.scrollHeight;
      }
      if (streamingContentRef.current) {
        streamingContentRef.current.scrollTop = streamingContentRef.current.scrollHeight;
      }
    };

    scrollStreamingMessageToBottom();
    const frame = window.requestAnimationFrame(scrollStreamingMessageToBottom);
    const resizeObserver = streamingContentRef.current ? new ResizeObserver(scrollStreamingMessageToBottom) : null;
    if (streamingContentRef.current) {
      resizeObserver?.observe(streamingContentRef.current);
    }

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
    };
  }, [chat]);

  async function refreshKnowledgeSummary() {
    try {
      setKnowledgeSummary(await client.knowledgeSummary());
    } catch {
      setKnowledgeSummary(null);
    }
  }

  async function refreshMergeRequests() {
    try {
      const operator = sessionRole === 'admin' ? 'admin' : 'designer';
      const items = await client.listMergeRequests(sessionRole, operator);
      setMergeRequests(items);
      setSelectedMergeRequestId((current) => (current && items.some((item) => item.id === current) ? current : items[0]?.id || null));
      await restoreDraftFromMergeRequests(items);
      const mergedCurrentDraft = projectResult?.draft_id && items.some((item) => item.draft_id === projectResult.draft_id && item.status === 'merged');
      if (mergedCurrentDraft && projectResult.draft_status !== 'accepted') {
        setProjectResult({ ...projectResult, draft_status: 'accepted' });
      }
    } catch {
      setMergeRequests([]);
      setSelectedMergeRequestId(null);
    }
  }

  async function restoreDraftFromMergeRequests(items: MergeRequestRecord[]) {
    if (sessionRole !== 'designer' || projectResult?.draft_id || !items.length) return;
    const candidate =
      items.find((item) => item.status === 'pending' || item.status === 'conflict' || item.status === 'merged') || items[0];
    if (!candidate?.draft_id) return;

    try {
      const draft = await client.getModelDraft(candidate.draft_id);
      setProjectResult(draft);
      setInternalDiagramViews(diagramViewsToInternalCache(draft.diagram_views));
      setPublishResult(null);
      setLiveModel(null);
      setSelectedId(draft.elements[0]?.id || null);
      setSelectedRelationshipId(null);
      setPreReviewReport(null);
      setImpactReport(null);
      setGenerationDuration('--');
      setGeneratedAt(formatAuditTime(candidate.created_at));
      setLastSyncTime('--');
      setActiveTab('sysml');
      setChat((current) => {
        const restoreMessageId = `restore-draft-${draft.draft_id}`;
        if (current.some((item) => item.id === restoreMessageId)) return current;
        return [
          ...current,
          {
            id: restoreMessageId,
            role: 'assistant',
            content: `已从合并请求 MR-${String(candidate.id).padStart(4, '0')} 恢复草稿 #${draft.draft_id}：${draft.elements.length} 个元素，${draft.relationships.length} 条关系。`,
            time: nowTime(),
            state: 'ok',
          },
        ];
      });
    } catch {
      // Merge management still works even if the draft snapshot cannot be restored.
    }
  }

  function resetKnowledgeBase() {
    modal.confirm({
      title: '清空知识库',
      content: '确定清空已上传的知识库文档和检索索引吗？临时附件和当前对话不会被删除。',
      okText: '清空',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const result = await client.resetKnowledgeBase();
        setKnowledgeSummary({ document_count: 0, chunk_count: 0, latest_documents: [] });
        message.success(`已清空知识库：删除 ${result.deleted_documents} 个文档、${result.deleted_chunks} 个片段`);
      },
    });
  }

  function startPaneResize(event: ReactPointerEvent<HTMLDivElement>, target: PaneResizeTarget) {
    if (event.button !== 0) return;
    event.preventDefault();
    const config = paneResizeConfig[target];
    const startX = event.clientX;
    const startValue = paneSizes[target];
    document.body.classList.add('agent-resizing');

    const handleMove = (moveEvent: PointerEvent) => {
      const rawDelta = moveEvent.clientX - startX;
      const delta = config.reverse ? -rawDelta : rawDelta;
      const next = clampNumber(startValue + delta, config.min, config.max);
      setPaneSizes((current) => (current[target] === next ? current : { ...current, [target]: next }));
    };

    const stopResize = () => {
      document.body.classList.remove('agent-resizing');
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', stopResize);
      window.removeEventListener('pointercancel', stopResize);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', stopResize);
    window.addEventListener('pointercancel', stopResize);
  }

  function resetPaneSize(target: PaneResizeTarget) {
    setPaneSizes((current) => ({ ...current, [target]: defaultPaneSizes[target] }));
  }

  async function handleAsk() {
    const text = prompt.trim();
    if (!text && !attachments.length) {
      message.warning('请输入设计问题或建模目标');
      return;
    }

    const userText = text || '请结合附件内容进行分析。';
    const outgoingAttachments = attachments;
    const assistantId = `${Date.now()}-assistant`;
    const payload = buildAiMessage(userText, mode, outgoingAttachments, activeProject.name);

    setChat((current) => [
      ...current,
      {
        id: `${Date.now()}-u`,
        role: 'user',
        content: userText,
        time: nowTime(),
        attachments: outgoingAttachments.map(toChatAttachment),
      },
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        time: nowTime(),
        state: 'working',
        streaming: true,
      },
    ]);
    setPrompt('');
    setStatus('chatting');
    let streamedAnswer = '';
    const chatTaskType = knowledgeMode === 'auto' ? 'chat' : knowledgeMode;
    try {
      await client.streamChat(payload, chatTaskType, conversationPayload, {
        onDelta: (delta) => {
          streamedAnswer = mergeStreamContent(streamedAnswer, delta);
          setChat((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    content: streamedAnswer,
                  }
                : item,
            ),
          );
        },
        onDone: (result) => {
          streamedAnswer = streamedAnswer || result.answer || '已收到。我会先帮助你澄清需求，确认后再进入SysML建模。';
          const finalAnswer = appendToolAndKnowledgeSummary(streamedAnswer, result.tool_calls, result.artifacts);
          setChat((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    content: finalAnswer,
                    state: 'ok',
                    streaming: false,
                    time: nowTime(),
                  }
                : item,
            ),
          );
        },
        onError: (detail) => {
          streamedAnswer = detail || 'AI流式输出失败，请检查后端服务。';
          setChat((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    content: streamedAnswer,
                    streaming: false,
                    state: undefined,
                    time: nowTime(),
                  }
                : item,
            ),
          );
        },
      });
      setAttachments([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch {
      setChat((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                content: 'AI对话流式输出失败，请检查后端服务或大语言模型配置。',
                streaming: false,
                state: undefined,
                time: nowTime(),
              }
            : item,
        ),
      );
      message.error('AI对话失败');
    } finally {
      setStatus((current) => (current === 'chatting' ? 'idle' : current));
    }
  }

  async function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    setStatus('uploading');
    const nextAttachments: AttachedFile[] = [];

    for (const file of files) {
      const id = `${Date.now()}-${file.name}-${Math.random()}`;
      const extracted = await extractTemporaryAttachment(file);

      nextAttachments.push({
        id,
        name: file.name,
        size: file.size,
        type: file.type || fileExtension(file.name) || 'unknown',
        status: extracted.status,
        content: truncateAttachmentContent(extracted.content || attachmentMetadata(file)),
      });
    }

    setAttachments((current) => [...current, ...nextAttachments]);
    setStatus('idle');
    if (fileInputRef.current) fileInputRef.current.value = '';
    const parsedCount = nextAttachments.filter((item) => item.status === 'parsed' || item.status === 'ready').length;
    const metadataOnly = nextAttachments.filter((item) => item.status === 'metadata').length;
    message.success(
      metadataOnly
        ? `已添加 ${nextAttachments.length} 个临时附件，已解析 ${parsedCount} 个正文，${metadataOnly} 个仅作为文件元数据`
        : `已添加 ${nextAttachments.length} 个临时附件，正文已进入本轮上下文`,
    );
  }

  async function handleKnowledgeFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    setStatus('uploading');
    let successCount = 0;
    let failedCount = 0;

    for (const file of files) {
      try {
        await client.uploadDocument(file);
        successCount += 1;
      } catch {
        failedCount += 1;
      }
    }

    await refreshKnowledgeSummary();
    setStatus('idle');
    if (knowledgeFileInputRef.current) knowledgeFileInputRef.current.value = '';

    if (failedCount) {
      message.warning(`已入库 ${successCount} 个知识库文档，${failedCount} 个上传失败`);
    } else {
      message.success(`已入库 ${successCount} 个知识库文档`);
    }
  }

  function removeAttachment(id: string) {
    setAttachments((current) => current.filter((item) => item.id !== id));
  }

  async function generateModel() {
    const baseText = resolveGenerationSource(prompt.trim(), chat);
    if (!baseText && !attachments.length) {
      message.warning('请先通过对话描述需求、边界、接口或约束，再点击生成SysML工程');
      setActiveTab('sysml');
      return null;
    }
    const text = buildAiMessage(baseText || '请结合附件内容生成SysML工程。', mode, attachments, activeProject.name);
    const startedAt = Date.now();
    setStatus('generating');
    setPublishResult(null);
    setLiveModel(null);
    setPreReviewReport(null);
    setInternalDiagramFocusId(null);
    setInternalDiagramViews({});
    setInternalDiagramError('');
    setLastSyncTime('--');
    try {
      const result = await client.generateSysmlProject('', text, [...conversationPayload, { role: 'user', content: text }]);
      const prebuiltInternalCount = countInternalDiagramViews(result.diagram_views);
      const behaviorViewCount = countBehaviorDiagramViews(result.diagram_views);
      setProjectResult(result);
      setInternalDiagramViews(diagramViewsToInternalCache(result.diagram_views));
      setGenerationDuration(formatDuration(Date.now() - startedAt));
      setGeneratedAt(nowTime());
      setSelectedId(result.elements[0]?.id || null);
      setActiveTab('sysml');
      setChat((current) => [
        ...current,
        {
          id: `${Date.now()}-gen`,
          role: 'assistant',
          content: `已生成候选方案 ${result.project_name}：${result.elements.length} 个元素，${result.relationships.length} 条关系。${prebuiltInternalCount ? `已预生成 ${prebuiltInternalCount} 张关键模块内部模块图，双击模块可直接下钻查看。` : ''}${behaviorViewCount ? `已补充 ${behaviorViewCount} 张行为图用于 MagicDraw 完整工程。` : ''}请在预览区确认或修正后提交合并请求，由管理员审核入库。`,
          time: nowTime(),
          state: 'ok',
        },
      ]);
      setAttachments([]);
      setPrompt('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      message.success('候选SysML方案已生成，等待预览确认');
      return result;
    } catch {
      message.error('SysML工程生成失败');
      return null;
    } finally {
      setStatus('idle');
    }
  }

  async function openInternalDiagram(targetId?: string) {
    if (!projectResult) {
      message.warning('请先生成SysML工程，再查看模块内部图');
      return;
    }
    const focus = resolveFocusedBlock(projectResult.elements, projectResult.relationships, targetId || selectedId);
    if (!focus || !['Block', 'Interface'].includes(focus.type)) {
      message.warning('请先在模型画布中选择一个 Block 或接口模块');
      return;
    }
    setInternalDiagramFocusId(focus.id);
    if (targetId) setSelectedId(focus.id);
    setInternalDiagramOpen(true);
    const cachedView = internalDiagramViews[focus.id] || findInternalDiagramViewForFocus(projectResult.diagram_views, focus.id);
    if (cachedView) {
      if (!internalDiagramViews[focus.id]) {
        setInternalDiagramViews((current) => ({ ...current, [focus.id]: { ...cachedView, focus_element_id: focus.id } }));
      }
      return;
    }
    await generateInternalDiagramForFocus(focus);
  }

  async function generateInternalDiagramForFocus(focus = internalDiagramFocus, force = false) {
    if (!projectResult || !focus) return;
    if (!force && internalDiagramViews[focus.id]) return;
    setInternalDiagramLoading(true);
    setInternalDiagramError('');
    try {
      const contextPrompt = [
        `当前项目：${projectResult.project_name || activeProject.name}`,
        `用户原始输入/当前对话：${resolveGenerationSource(prompt.trim(), chat) || activeProject.name}`,
        `工程摘要：${projectResult.summary || ''}`,
        `建模假设：${(projectResult.assumptions || []).join('；')}`,
      ]
        .filter(Boolean)
        .join('\n');
      const view = await client.generateInternalBlockDiagram({
        project_name: projectResult.project_name,
        prompt: contextPrompt,
        focus_element: focus,
        elements: projectResult.elements,
        relationships: projectResult.relationships,
      });
      cacheInternalDiagramView(focus.id, view);
      if (force) message.success(`${focus.name} 内部模块图已重新生成`);
    } catch {
      setInternalDiagramError('AI 构建内部模块图失败，请稍后重试');
      message.error('AI 构建内部模块图失败');
    } finally {
      setInternalDiagramLoading(false);
    }
  }

  function diagramViewsForExchange() {
    return uniqueDiagramViews(
      [...(projectResult?.diagram_views || []), ...Object.values(internalDiagramViews)].filter((view) => view.elements.length > 0),
    ).slice(0, 32);
  }

  function diagramViewsForDisplay() {
    return uniqueDiagramViews([...(projectResult?.diagram_views || []), ...Object.values(internalDiagramViews)])
      .filter(diagramViewHasCanvas)
      .slice(0, 32);
  }

  function cacheInternalDiagramView(focusId: string, view: SysMLDiagramView) {
    const nextView = { ...view, focus_element_id: view.focus_element_id || focusId };
    setInternalDiagramViews((current) => ({ ...current, [focusId]: nextView }));
    updateActiveWorkspace((current) => {
      if (!current.projectResult) return current;
      return {
        ...current,
        projectResult: {
          ...current.projectResult,
          diagram_views: uniqueDiagramViews([...(current.projectResult.diagram_views || []), nextView]),
        },
      };
    });
  }

  async function acceptDraft() {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再采纳');
      return;
    }
    setStatus('accepting');
    try {
      const result = await client.acceptModelDraft(draftId, '预览确认后采纳入库');
      setProjectResult(result.draft);
      setPublishResult(null);
      setLastSyncTime('--');
      setChat((current) => [
        ...current,
        {
          id: `${Date.now()}-accept`,
          role: 'assistant',
          content: `已采纳当前预览模型并写入SysML模型库：${result.draft.elements.length} 个元素，${result.draft.relationships.length} 条关系。`,
          time: nowTime(),
          state: 'ok',
        },
      ]);
      message.success('候选模型已采纳并入库');
    } catch {
      message.error('采纳模型失败');
    } finally {
      setStatus('idle');
    }
  }

  async function submitDraftMergeRequest() {
    const draftId = projectResult?.draft_id;
    if (!draftId || !projectResult) {
      message.warning('当前模型没有草稿编号，请重新生成后再提交合并请求');
      return;
    }
    setStatus('submitting');
    try {
      const mergeRequest = await client.submitMergeRequest({
        draft_id: draftId,
        title: `${projectResult.project_name} 入库审核`,
        description: '设计师预览确认后，从开发分支提交到发布分支。',
        source_branch: sessionRole === 'admin' ? 'dev/admin' : 'dev/designer-01',
        target_branch: 'release/main',
        submitter: sessionRole === 'admin' ? 'admin' : 'designer',
      });
      setProjectResult({ ...projectResult, draft_status: 'submitted' });
      setPublishResult(null);
      setLastSyncTime('--');
      setMergeRequests((current) => [mergeRequest, ...current.filter((item) => item.id !== mergeRequest.id)]);
      setSelectedMergeRequestId(mergeRequest.id);
      setActiveTab('merge');
      setChat((current) => [
        ...current,
        {
          id: `${Date.now()}-merge-request`,
          role: 'assistant',
          content: `已提交合并请求 MR-${String(mergeRequest.id).padStart(4, '0')}。当前状态：${mergeRequest.status === 'conflict' ? '存在冲突，等待管理员处理' : '等待管理员审核'}。`,
          time: nowTime(),
          state: 'ok',
        },
      ]);
      message.success('合并请求已提交，等待管理员审核');
    } catch {
      message.error('提交合并请求失败');
    } finally {
      setStatus('idle');
    }
  }

  function rejectDraft() {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号');
      return;
    }
    modal.confirm({
      title: '拒绝候选方案',
      content: '确定拒绝当前候选模型吗？后台会记录为负反馈，当前预览结果仍可导出但不能直接推送。',
      okText: '拒绝',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const result = await client.rejectModelDraft(draftId, '用户拒绝当前候选方案');
        setProjectResult(result);
        setPublishResult(null);
        message.success('已记录拒绝反馈');
      },
    });
  }

  function startManualRelationshipEdit() {
    if (!elements.length) {
      message.warning('当前候选模型还没有可修改的元素');
      return;
    }
    if (relationships.length) {
      setSelectedRelationshipId(selectedRelationshipId || relationships[0].id);
    }
    setActiveTab('sysml');
  }

  async function updateDraftElement(elementId: string, patch: { name: string; type: string; description?: string; package?: string | null; source_requirement?: string | null; status?: string }) {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再修改元素');
      return;
    }
    setStatus('editing');
    try {
      const result = await client.updateDraftElement(draftId, elementId, {
        ...patch,
        operator: 'demo-user',
        comment: '用户在预览区手动修改元素',
      });
      setProjectResult(result);
      setPublishResult(null);
      setPreReviewReport(null);
      setLastSyncTime('--');
      setSelectedId(elementId);
      message.success('元素已更新，SysML文本已同步重算');
    } catch {
      message.error('元素更新失败');
    } finally {
      setStatus('idle');
    }
  }

  async function updateDraftRelationship(relationshipId: string, patch: { source: string; target: string; type: string; description?: string }) {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再修改关系');
      return;
    }
    setStatus('editing');
    try {
      const result = await client.updateDraftRelationship(draftId, relationshipId, {
        ...patch,
        operator: 'demo-user',
        comment: '用户在预览区手动调整连接线',
      });
      setProjectResult(result);
      setPublishResult(null);
      setPreReviewReport(null);
      setLastSyncTime('--');
      setSelectedRelationshipId(relationshipId);
      message.success('连接线已更新，SysML文本已同步重算');
    } catch {
      message.error('连接线更新失败');
    } finally {
      setStatus('idle');
    }
  }

  async function createDraftRelationship(patch: { source: string; target: string; type: string; description?: string }) {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再新增关系');
      return;
    }
    const previousIds = new Set(relationships.map((item) => item.id));
    setStatus('editing');
    try {
      const result = await client.createDraftRelationship(draftId, {
        ...patch,
        operator: 'demo-user',
        comment: '用户在预览区手动新增连接线',
      });
      const created = result.relationships.find((item) => !previousIds.has(item.id)) || result.relationships[result.relationships.length - 1];
      setProjectResult(result);
      setPublishResult(null);
      setPreReviewReport(null);
      setLastSyncTime('--');
      setSelectedRelationshipId(created?.id || null);
      message.success('连接线已新增，SysML文本已同步重算');
    } catch {
      message.error('新增连接线失败');
    } finally {
      setStatus('idle');
    }
  }

  function deleteDraftRelationship(relationshipId: string) {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再删除关系');
      return;
    }
    modal.confirm({
      title: '删除连接线',
      content: `确定删除 ${relationshipId} 吗？删除后会同步更新候选草稿和SysML文本。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setStatus('editing');
        try {
          const result = await client.deleteDraftRelationship(draftId, relationshipId);
          setProjectResult(result);
          setPublishResult(null);
          setPreReviewReport(null);
          setLastSyncTime('--');
          setSelectedRelationshipId(result.relationships[0]?.id || null);
          message.success('连接线已删除，SysML文本已同步重算');
        } catch {
          message.error('删除连接线失败');
        } finally {
          setStatus('idle');
        }
      },
    });
  }

  async function runDraftValidation() {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('请先生成候选模型，再执行模型校验');
      return;
    }
    setStatus('validating');
    try {
      const report = await client.validateModelDraft(draftId);
      setPreReviewReport(report);
      setPreReviewOpen(true);
      message.success('模型预评审完成');
    } catch {
      message.error('模型预评审失败');
    } finally {
      setStatus('idle');
    }
  }

  async function fixDraftValidationIssues(issueIds: string[]) {
    const draftId = projectResult?.draft_id;
    if (!draftId) {
      message.warning('当前模型没有草稿编号，请重新生成后再修复');
      return;
    }
    if (!issueIds.length) {
      message.info('当前没有可自动修复的问题');
      return;
    }
    setStatus('editing');
    try {
      const result = await client.fixModelDraftIssues(draftId, issueIds);
      setProjectResult(result.draft);
      setPublishResult(null);
      setPreReviewReport(result.report);
      setLastSyncTime('--');
      message.success(`已自动修复 ${result.fixed_issue_ids.length} 项问题`);
    } catch {
      message.error('一键修复失败');
    } finally {
      setStatus('idle');
    }
  }

  async function runSandboxImpactAnalysis(payload: ChangeImpactSandboxRequest) {
    if (!projectResult || !elements.length) {
      message.warning('请先生成 SysML 模型，再执行变更影响分析');
      setActiveTab('sysml');
      return;
    }
    setStatus('analyzing');
    try {
      const report = await client.runChangeImpactAnalysis({
        ...payload,
        project_name: projectResult.project_name,
        elements,
        relationships,
      });
      setImpactReport(report);
      setActiveTab('impact');
      message.success('沙箱变更影响分析已完成');
    } catch {
      message.error('变更影响分析失败');
    } finally {
      setStatus('idle');
    }
  }

  async function resolveMergeConflict(mergeRequestId: number, conflictId: string, resolution: 'use_candidate' | 'keep_release') {
    if (sessionRole !== 'admin') {
      message.warning('只有管理员可以解决冲突');
      return;
    }
    setStatus('merging');
    try {
      const result = await client.resolveMergeConflict(mergeRequestId, conflictId, resolution);
      setMergeRequests((current) => current.map((item) => (item.id === result.id ? result : item)));
      setSelectedMergeRequestId(result.id);
      message.success(resolution === 'use_candidate' ? '已采用开发分支版本' : '已保留发布分支版本');
    } catch {
      message.error('冲突解决失败');
    } finally {
      setStatus('idle');
    }
  }

  async function mergeIntoRelease(mergeRequestId: number) {
    if (sessionRole !== 'admin') {
      message.warning('只有管理员可以合并入库');
      return;
    }
    setStatus('merging');
    try {
      const result = await client.mergeIntoRelease(mergeRequestId, '管理员审核通过，合并入发布分支');
      setMergeRequests((current) => current.map((item) => (item.id === result.merge_request.id ? result.merge_request : item)));
      setSelectedMergeRequestId(result.merge_request.id);
      if (projectResult?.draft_id === result.merge_request.draft_id) {
        setProjectResult({ ...projectResult, draft_status: 'accepted' });
      }
      message.success('合并入库完成，候选元素已转正为权威图谱元素');
    } catch {
      message.error('合并入库失败，请确认冲突已全部解决');
    } finally {
      setStatus('idle');
    }
  }

  async function rejectMergeRequest(mergeRequestId: number) {
    if (sessionRole !== 'admin') {
      message.warning('只有管理员可以拒绝合并请求');
      return;
    }
    setStatus('merging');
    try {
      const result = await client.rejectMergeRequest(mergeRequestId, '管理员拒绝本次合并请求');
      setMergeRequests((current) => current.map((item) => (item.id === result.id ? result : item)));
      setSelectedMergeRequestId(result.id);
      message.success('合并请求已拒绝');
    } catch {
      message.error('拒绝合并请求失败');
    } finally {
      setStatus('idle');
    }
  }

  async function previewPushToMagicDraw() {
    if (!projectResult) {
      message.warning('请先生成SysML工程，再进行预览推送');
      setActiveTab('sysml');
      return;
    }
    if (projectResult.draft_status === 'rejected') {
      message.warning('当前候选模型已拒绝，请重新生成或修正后再预览推送');
      setActiveTab('sysml');
      return;
    }
    await publishToMagicDraw('preview');
  }

  async function pushToMagicDraw() {
    if (!projectResult) {
      message.warning('请先生成SysML工程，再发布推送到MagicDraw');
      setActiveTab('sysml');
      return;
    }
    if (!isDraftAccepted(projectResult)) {
      message.warning('请先提交合并请求并由管理员合并入库，再进行发布推送');
      setActiveTab('sysml');
      return;
    }
    await publishToMagicDraw('release');
  }

  async function publishToMagicDraw(stage: 'preview' | 'release') {
    if (!projectResult || pushStage) return;
    const result = projectResult;
    const preview = stage === 'preview';
    const packageName = preview ? `PREVIEW_${result.project_name}` : result.project_name;
    const focusedDiagramViews = diagramViewsForExchange();
    setPushStage(stage);
    setStatus('syncing');
    try {
      const published = await client.publishMagicDraw(result.elements, result.relationships, packageName, focusedDiagramViews);
      setPublishResult(published);
      setLastSyncTime(`${preview ? '预览' : '发布'} ${nowTime()}`);
      setActiveTab('sync');
      setChat((current) => [
        ...current,
        {
          id: `${Date.now()}-${stage}-push`,
          role: 'assistant',
          content:
            published.mode === 'bridge'
              ? `${preview ? '预览推送' : '发布推送'}已同步到 MagicDraw，包名 ${published.package_name}，元素 ${summaryText(published, 'elements')}，关系 ${summaryText(published, 'relationships')}。`
              : `Bridge未连接，已生成${preview ? '预览' : '发布'}交换包：${published.files?.directory || published.message}`,
          time: nowTime(),
          state: published.mode === 'bridge' ? 'ok' : 'working',
        },
      ]);
      message.success(
        published.mode === 'bridge'
          ? `${preview ? '预览推送' : '发布推送'}已完成`
          : `已生成MagicDraw${preview ? '预览' : '发布'}交换包`,
      );
      refreshBridge({ silent: true });
    } catch {
      message.error(`${preview ? '预览推送' : '发布推送'}MagicDraw失败`);
    } finally {
      setPushStage(null);
      setStatus('idle');
    }
  }

  async function refreshBridge(options: { silent?: boolean } = {}): Promise<MagicDrawStatus | null> {
    if (!options.silent) setStatus('reading');
    try {
      const nextStatus = await client.magicDrawStatus();
      setMagicDrawStatus(nextStatus);
      if (nextStatus.bridge_available && nextStatus.project_open !== false) {
        try {
          setLiveModel(await client.readMagicDrawCurrentModel());
        } catch {
          setLiveModel(null);
        }
      }
      if (!options.silent) message.success('同步状态已刷新');
      return nextStatus;
    } catch {
      setMagicDrawStatus(null);
      if (!options.silent) message.error('读取MagicDraw状态失败');
      return null;
    } finally {
      if (!options.silent) setStatus('idle');
    }
  }

  async function runSimulation() {
    if (!elements.length) {
      message.warning('请先生成SysML工程');
      return;
    }
    setStatus('simulating');
    try {
      const result = await client.runSimulation(elements[0].id);
      setSimulationSummary(String(result?.message || result?.status || '仿真完成'));
      message.success('系统仿真已完成');
    } catch {
      setSimulationSummary('仿真失败');
      message.error('系统仿真失败');
    } finally {
      setStatus('idle');
    }
  }

  function exportPackage() {
    if (!projectResult) {
      message.warning('请先生成SysML工程');
      return;
    }
    const payload = {
      project: projectResult.project_name,
      sysml_text: projectResult.sysml_text,
      elements: projectResult.elements,
      relationships: projectResult.relationships,
      diagram_views: diagramViewsForExchange(),
      magicdraw: publishResult,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${projectResult.project_name}_package.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function createProject() {
    const count = authorizedProjects.length + 1;
    const projectWorkspace = isWorkspaceScoped && workspace ? workspace : activeProject.workspace || activeProject.name;
    const newProject: ProjectItem = {
      id: `custom-${Date.now()}`,
      name: `新项目 ${count}`,
      workspace: projectWorkspace,
      prompt: '',
    };
    setProjects((current) => [newProject, ...current]);
    setWorkspaces((current) => ({ ...current, [newProject.id]: createWorkspace(newProject) }));
    setActiveProjectId(newProject.id);
    setEditingProjectId(newProject.id);
    setEditingProjectName(newProject.name);
  }

  function startProjectRename(project: ProjectItem) {
    if (project.protected && sessionRole === 'designer') {
      message.info('系统基线项目由管理员维护，设计师可新建自己的工作项目');
      return;
    }
    setEditingProjectId(project.id);
    setEditingProjectName(project.name);
  }

  function commitProjectRename(projectId: string) {
    const nextName = editingProjectName.trim();
    if (!nextName) {
      message.warning('项目名称不能为空');
      return;
    }
    setProjects((current) => current.map((item) => (item.id === projectId ? { ...item, name: nextName } : item)));
    setEditingProjectId(null);
    setEditingProjectName('');
  }

  function deleteProject(project: ProjectItem) {
    if (project.protected && sessionRole === 'designer') {
      message.info('系统基线项目由管理员维护，不能由设计师删除');
      return;
    }
    if (authorizedProjects.length <= 1) {
      message.warning('至少保留一个项目');
      return;
    }
    modal.confirm({
      title: '删除项目',
      content: `确定删除“${project.name}”？该项目中的聊天记录、SysML生成结果和同步预览都会一起移除。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        const remaining = projects.filter((item) => item.id !== project.id);
        const remainingAuthorized = remaining.filter((item) => (isWorkspaceScoped ? item.workspace === workspace : true));
        const nextActiveId = activeProjectId === project.id ? remainingAuthorized[0]?.id : activeProjectId;
        setProjects(remaining);
        setWorkspaces((current) => {
          const next = { ...current };
          delete next[project.id];
          return next;
        });
        if (nextActiveId && nextActiveId !== activeProjectId) {
          setActiveProjectId(nextActiveId);
        }
        if (editingProjectId === project.id) {
          setEditingProjectId(null);
          setEditingProjectName('');
        }
        message.success('项目已删除');
      },
    });
  }

  function canModifyProject(project: ProjectItem) {
    return !(project.protected && sessionRole === 'designer');
  }

  return (
    <div className="agent-station" style={stationStyle}>
      <aside className="agent-project-rail">
        <div className="agent-rail-top">
          <strong>项目</strong>
          <Button size="small" icon={<PlusOutlined />} onClick={createProject}>
            新建项目
          </Button>
        </div>
        <Input
          className="agent-search"
          prefix={<SearchOutlined />}
          value={query}
          placeholder="搜索项目"
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="agent-project-section">全部项目</div>
        <div className="agent-project-list">
          {visibleProjects.map((item) => (
            <div
              className={`agent-project-item ${item.id === activeProjectId ? 'active' : ''}`}
              key={item.id}
              onClick={() => setActiveProjectId(item.id)}
              onDoubleClick={() => startProjectRename(item)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') setActiveProjectId(item.id);
              }}
              role="button"
              tabIndex={0}
            >
              <FileTextOutlined className="agent-project-icon" />
              <span>
                {editingProjectId === item.id ? (
                  <Input
                    autoFocus
                    className="agent-project-name-input"
                    size="small"
                    value={editingProjectName}
                    onBlur={() => commitProjectRename(item.id)}
                    onChange={(event) => setEditingProjectName(event.target.value)}
                    onClick={(event) => event.stopPropagation()}
                    onPressEnter={() => commitProjectRename(item.id)}
                  />
                ) : (
                  <strong>{item.name}</strong>
                )}
              </span>
              {canModifyProject(item) && (
                <>
                  <Button
                    className="agent-project-edit"
                    icon={<EditOutlined />}
                    size="small"
                    type="text"
                    onClick={(event) => {
                      event.stopPropagation();
                      startProjectRename(item);
                    }}
                  />
                  <Button
                    className="agent-project-delete"
                    icon={<DeleteOutlined />}
                    size="small"
                    type="text"
                    onClick={(event) => {
                      event.stopPropagation();
                      deleteProject(item);
                    }}
                  />
                </>
              )}
            </div>
          ))}
        </div>
        <div className="agent-rail-footer">
          <span>项目总数 {authorizedProjects.length}</span>
          <Button block ghost icon={<SettingOutlined />}>
            项目管理
          </Button>
        </div>
      </aside>

      {resizeHandle('project', '调整项目栏宽度')}

      <section className="agent-chat-panel">
        <div className="agent-chat-header">
          <div>
            <Typography.Title level={4}>AI 智能体</Typography.Title>
            <Typography.Text type="secondary">MBSE 助理</Typography.Text>
          </div>
          <Button type="text" icon={<FullscreenOutlined />} />
        </div>
        <div className="agent-profile">
          <div className="agent-avatar">
            <RobotOutlined />
          </div>
          <div>
            <strong>MBSE 助理</strong>
            <span>专注于 MBSE / SysML 建模与系统工程设计。</span>
          </div>
          <Tag color="green">在线</Tag>
        </div>
        <div className="agent-knowledge-card">
          <input ref={knowledgeFileInputRef} className="agent-file-input" type="file" multiple onChange={handleKnowledgeFilesSelected} />
          <span>
            <DatabaseOutlined /> 知识库
          </span>
          <strong>{knowledgeSummary ? `${knowledgeSummary.document_count} 文档 / ${knowledgeSummary.chunk_count} 片段` : '未连接'}</strong>
          <Tag color={knowledgeMode === 'knowledge_qa' ? 'blue' : knowledgeMode === 'direct_chat' ? 'default' : 'green'}>
            {knowledgeModeLabel(knowledgeMode)}
          </Tag>
          <Button size="small" icon={<CloudUploadOutlined />} loading={status === 'uploading'} onClick={() => knowledgeFileInputRef.current?.click()}>
            上传入库
          </Button>
          <Button
            danger
            disabled={!knowledgeSummary?.document_count && !knowledgeSummary?.chunk_count}
            icon={<DeleteOutlined />}
            size="small"
            type="text"
            onClick={resetKnowledgeBase}
          />
          <Button size="small" type="text" icon={<ReloadOutlined />} onClick={refreshKnowledgeSummary} />
        </div>
        <div className="agent-chat-stream" ref={chatStreamRef}>
          {chat.slice(-8).map((item) => (
            <div className={`agent-chat-bubble ${item.role}`} key={item.id}>
              <div className="agent-bubble-icon">{item.role === 'user' ? '我' : <RobotOutlined />}</div>
              <div className="agent-bubble-body">
                <div className="agent-bubble-content" ref={item.streaming ? streamingContentRef : undefined}>
                  <MarkdownMessage content={item.content} streaming={item.streaming} />
                </div>
                {item.streaming && (
                  <div className="agent-stream-progress" aria-label="AI正在流式输出">
                    <span>正在流式输出</span>
                    <strong>{item.content.length ? `${item.content.length} 字` : '连接中'}</strong>
                    <i />
                  </div>
                )}
                {!!item.attachments?.length && (
                  <div className="agent-bubble-attachments">
                    {item.attachments.map((file) => (
                      <span key={`${item.id}-${file.name}-${file.size}`}>
                        <PaperClipOutlined /> {file.name}
                      </span>
                    ))}
                  </div>
                )}
                <span className="agent-bubble-time">
                  {item.state === 'ok' && <CheckCircleOutlined />} {item.time}
                </span>
              </div>
            </div>
          ))}
        </div>
        <div className="agent-quick-actions">
          <Button type="primary" icon={<BranchesOutlined />} loading={status === 'generating'} disabled={!canGenerateModel} onClick={generateModel}>
            生成
          </Button>
          <Button icon={<CloudUploadOutlined />} loading={pushStage === 'preview'} disabled={!canPreviewPushModel || (!!pushStage && pushStage !== 'preview')} onClick={previewPushToMagicDraw}>
            预览推送
          </Button>
          <Button icon={<CloudUploadOutlined />} loading={pushStage === 'release'} disabled={!canPushModel || (!!pushStage && pushStage !== 'release')} onClick={pushToMagicDraw}>
            发布推送
          </Button>
          <Button icon={<DownloadOutlined />} onClick={exportPackage}>
            导出
          </Button>
          <Button icon={<EllipsisOutlined />} />
        </div>
        <div className="agent-input-box">
          <input ref={fileInputRef} className="agent-file-input" type="file" multiple onChange={handleFilesSelected} />
          <Input.TextArea value={prompt} rows={4} onChange={(event) => setPrompt(event.target.value)} placeholder="输入您的需求或问题..." />
          {!!attachments.length && (
            <div className="agent-attachment-list">
              {attachments.map((file) => (
                <div className="agent-attachment-chip" key={file.id}>
                  <FileTextOutlined />
                  <span>{file.name}</span>
                  <em>{formatBytes(file.size)}</em>
                  <Tag color={file.status === 'ready' ? 'blue' : 'gold'}>
                    {file.status === 'ready' ? '临时' : '元数据'}
                  </Tag>
                  <Button size="small" type="text" icon={<CloseOutlined />} onClick={() => removeAttachment(file.id)} />
                </div>
              ))}
            </div>
          )}
          <div className="agent-input-toolbar">
            <Space>
              <Tooltip title="上传临时附件">
                <Button type="text" icon={<PaperClipOutlined />} loading={status === 'uploading'} onClick={() => fileInputRef.current?.click()} />
              </Tooltip>
              <Tooltip title="当前对话上下文">
                <Button type="text" icon={<ApartmentOutlined />} />
              </Tooltip>
              <Tooltip title="模型结构上下文">
                <Button type="text" icon={<BranchesOutlined />} disabled={!elements.length} />
              </Tooltip>
            </Space>
            <Space>
              <Select
                className="agent-knowledge-mode"
                size="small"
                value={knowledgeMode}
                onChange={(value) => setKnowledgeMode(value as KnowledgeMode)}
                options={[
                  { value: 'auto', label: '自动识别' },
                  { value: 'direct_chat', label: '直接问答' },
                  { value: 'knowledge_qa', label: '知识库问答' },
                ]}
              />
              <Select
                size="small"
                value={mode}
                onChange={(value) => setMode(value as ResponseMode)}
                options={[
                  { value: 'fast', label: '快速回答' },
                  { value: 'deep', label: '深度思考' },
                  { value: 'review', label: '评审模式' },
                ]}
              />
              <Button type="primary" icon={<SendOutlined />} loading={status === 'chatting'} onClick={handleAsk} />
            </Space>
          </div>
        </div>
      </section>

      {resizeHandle('chat', '调整AI对话栏宽度')}

      <main className="agent-main-panel">
        <Toolbar
          bridgeOnline={bridgeOnline}
          bridgeProjectOpen={bridgeProjectOpen}
          bridgeProjectName={bridgeProjectName}
          bridgeProjectPathConfigured={bridgeProjectPathConfigured}
          status={status}
          syncState={
            publishResult
              ? isPreviewPublish(publishResult)
                ? canPushModel
                  ? '待发布'
                  : '已预览'
                : '已发布'
              : projectResult
                ? canPushModel
                  ? '待发布'
                  : canPreviewPushModel
                    ? '可预览'
                    : '待审核'
                : '待生成'
          }
          canGenerate={canGenerateModel}
          canPreviewPush={canPreviewPushModel}
          canPush={canPushModel}
          pushStage={pushStage}
          onGenerate={generateModel}
          onRefresh={refreshBridge}
          onPreviewPush={previewPushToMagicDraw}
          onPush={pushToMagicDraw}
          onExport={exportPackage}
          onSimulate={runSimulation}
        />
        <WorkflowProgress steps={workflow} />
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'sysml',
              label: 'SysML 生成',
              children: (
                <div className="agent-sysml-generate-page">
                  <div className="agent-sysml-stage">
                    <SysmlPreview result={projectResult} selectedId={selectedId} onSelect={setSelectedId} />
                    <DiagramPanel
                      elements={elements}
                      relationships={relationships}
                      layout={null}
                      diagramViews={diagramViewsForDisplay()}
                      selectedId={selectedId}
                      selectedRelationshipId={selectedRelationshipId}
                      onSelect={setSelectedId}
                      onSelectRelationship={setSelectedRelationshipId}
                      onOpenInternalDiagram={openInternalDiagram}
                    />
                  </div>
                  {projectResult && (
                    <DraftReviewBar
                      result={projectResult}
                      hasReport={!!preReviewReport}
                      status={status}
                      onAccept={submitDraftMergeRequest}
                      onEdit={startManualRelationshipEdit}
                      onOpenReport={() => setPreReviewOpen(true)}
                      onReject={rejectDraft}
                      onValidate={runDraftValidation}
                    />
                  )}
                  {projectResult && isDraftEditable(projectResult) && (
                    <DraftManualEditPanel
                      element={editableElement}
                      elements={elements}
                      loading={status === 'editing'}
                      relationship={editableRelationship}
                      relationships={relationships}
                      selectedElementId={editableElement?.id || ''}
                      selectedRelationshipId={editableRelationship?.id || ''}
                      onCreateRelationship={createDraftRelationship}
                      onDeleteRelationship={deleteDraftRelationship}
                      onSelectElement={setSelectedId}
                      onSelectRelationship={setSelectedRelationshipId}
                      onUpdateElement={updateDraftElement}
                      onUpdateRelationship={updateDraftRelationship}
                    />
                  )}
                  {projectResult && (
                    <GenerationStatusBar
                      generatedAt={generatedAt}
                      generationDuration={generationDuration}
                      projectResult={projectResult}
                      publishResult={publishResult}
                      validation={previewValidation}
                    />
                  )}
                  {projectResult && previewValidation.issues.length > 0 && <PreviewValidationPanel validation={previewValidation} publishResult={null} />}
                  <PreReviewReportModal
                    loading={status === 'editing'}
                    onClose={() => setPreReviewOpen(false)}
                    onFix={fixDraftValidationIssues}
                    onRunValidation={runDraftValidation}
                    open={preReviewOpen}
                    report={preReviewReport}
                    validating={status === 'validating'}
                  />
                  {projectResult && (
                    <Modal
                      className="agent-internal-diagram-modal"
                      footer={null}
                      open={internalDiagramOpen}
                      title={focusedDiagramModalTitle(dialogInternalDiagramFocus)}
                      width="min(1540px, 94vw)"
                      onCancel={() => setInternalDiagramOpen(false)}
                    >
                      <DiagramAlternativesPanel
                        error={internalDiagramError}
                        focus={dialogInternalDiagramFocus}
                        loading={internalDiagramLoading}
                        view={activeInternalDiagramView}
                        onRegenerate={() => generateInternalDiagramForFocus(dialogInternalDiagramFocus, true)}
                      />
                    </Modal>
                  )}
                </div>
              ),
            },
            {
              key: 'impact',
              label: '变更影响分析',
              children: (
                <ChangeImpactPanel
                  elements={elements}
                  loading={status === 'analyzing'}
                  projectName={projectResult?.project_name || activeProject.name}
                  relationships={relationships}
                  report={impactReport}
                  selectedId={selectedId}
                  taskContext={activeProject.name}
                  onAnalyze={runSandboxImpactAnalysis}
                  onSelectTarget={setSelectedId}
                />
              ),
            },
            {
              key: 'merge',
              label: '入库管理',
              children: (
                <MergeManagementPanel
                  loading={status === 'submitting' || status === 'merging'}
                  mergeRequests={mergeRequests}
                  role={sessionRole}
                  selectedMergeRequest={selectedMergeRequest}
                  onMerge={mergeIntoRelease}
                  onRefresh={refreshMergeRequests}
                  onReject={rejectMergeRequest}
                  onResolve={resolveMergeConflict}
                  onSelect={setSelectedMergeRequestId}
                  onSubmitCurrent={projectResult?.draft_id ? submitDraftMergeRequest : undefined}
                />
              ),
            },
            {
              key: 'sync',
              label: 'MagicDraw 同步',
              children:
                projectResult && publishResult ? (
                  <div className="agent-sync-page">
                    <div className="agent-sync-strip">
                      <Metric label="已创建" value={String(summary.created)} />
                      <Metric label="已更新" value={String(summary.updated)} />
                      <Metric label="已映射" value={String(summary.mapped)} />
                      <Metric label="无冲突" value={String(summary.conflicts)} invert />
                    </div>
                    <div className="agent-sync-layout">
                      <ModelExplorer groups={groupedElements} projectName={projectResult.project_name} selectedId={selectedId} onSelect={setSelectedId} />
                      {resizeHandle('explorer', '调整工程浏览器宽度')}
                      <DiagramPanel
                        elements={elements}
                        relationships={relationships}
                        layout={publishResult.exchange_payload?.diagram_layout || null}
                        diagramViews={diagramViewsForDisplay()}
                        selectedId={selectedId}
                        selectedRelationshipId={selectedRelationshipId}
                        onSelect={setSelectedId}
                        onSelectRelationship={setSelectedRelationshipId}
                        onOpenInternalDiagram={openInternalDiagram}
                      />
                    </div>
                    <div className="agent-bottom-grid">
                      <SyncTable rows={syncRows} />
                      {resizeHandle('summary', '调整同步摘要宽度')}
                      <SyncSummary
                        summary={summary}
                        lastSyncTime={lastSyncTime}
                        bridgeOnline={bridgeOnline}
                        bridgeProjectOpen={bridgeProjectOpen}
                        bridgeProjectPathConfigured={bridgeProjectPathConfigured}
                        simulationSummary={simulationSummary}
                      />
                    </div>
                  </div>
                ) : (
                  <MagicDrawPendingPanel
                    projectResult={projectResult}
                    bridgeOnline={bridgeOnline}
                    bridgeProjectOpen={bridgeProjectOpen}
                    bridgeProjectPathConfigured={bridgeProjectPathConfigured}
                    status={status}
                    onGenerate={generateModel}
                    onPreviewPush={previewPushToMagicDraw}
                    onPush={pushToMagicDraw}
                    canGenerate={canGenerateModel}
                    canPreviewPush={canPreviewPushModel}
                    canPush={canPushModel}
                    pushStage={pushStage}
                  />
                ),
            },
          ]}
        />
      </main>
    </div>
  );
}

function Toolbar({
  bridgeOnline,
  bridgeProjectOpen,
  bridgeProjectName,
  bridgeProjectPathConfigured,
  status,
  syncState,
  canGenerate,
  canPreviewPush,
  canPush,
  pushStage,
  onGenerate,
  onRefresh,
  onPreviewPush,
  onPush,
  onExport,
  onSimulate,
}: {
  bridgeOnline: boolean;
  bridgeProjectOpen: boolean | null;
  bridgeProjectName: string;
  bridgeProjectPathConfigured: boolean;
  status: WorkStatus;
  syncState: string;
  canGenerate: boolean;
  canPreviewPush: boolean;
  canPush: boolean;
  pushStage: MagicDrawPushStage;
  onGenerate: () => void;
  onRefresh: () => void;
  onPreviewPush: () => void;
  onPush: () => void;
  onExport: () => void;
  onSimulate: () => void;
}) {
  const bridgeWaitingForImport = bridgeOnline && bridgeProjectOpen === false && !bridgeProjectPathConfigured;
  const bridgeStateText = bridgeOnline ? '已连接' : '未连接';
  const bridgeTagColor = bridgeOnline ? 'green' : 'gold';
  const bridgeTip = !bridgeOnline
    ? '未连接到MagicDraw Bridge，将只生成本地交换包'
    : bridgeWaitingForImport
      ? 'Bridge在线，未检测到当前工程对象；预览推送仍会直接调用MagicDraw导入接口'
      : bridgeProjectName
        ? `当前工程：${bridgeProjectName}`
        : 'MagicDraw Bridge已连接';
  const previewTip = canPreviewPush ? '推送到MagicDraw预览包，不写入正式库' : '请先生成候选SysML模型';
  const releaseTip = canPush ? '正式发布到MagicDraw' : '请先提交合并请求并由管理员合并入库';
  return (
    <div className="agent-toolbar">
      <Space size={14} wrap>
        <Tooltip title={bridgeTip}>
          <Tag color={bridgeTagColor}>MagicDraw {bridgeStateText}</Tag>
        </Tooltip>
        <Tag color={syncState === '已发布' ? 'green' : syncState === '已预览' || syncState === '待发布' || syncState === '可预览' ? 'blue' : syncState === '待审核' ? 'gold' : 'default'}>
          <CheckCircleOutlined /> 同步状态 {syncState}
        </Tag>
      </Space>
      <Space size={6} wrap>
        <Tooltip title="结合当前输入和历史对话生成SysML工程">
          <Button icon={<BranchesOutlined />} loading={status === 'generating'} disabled={!canGenerate} onClick={onGenerate}>
            生成
          </Button>
        </Tooltip>
        <Tooltip title="刷新并读取Bridge状态">
          <Button icon={<ReloadOutlined />} loading={status === 'reading'} onClick={onRefresh}>
            同步
          </Button>
        </Tooltip>
        <Tooltip title={previewTip}>
          <Button icon={<CloudUploadOutlined />} loading={pushStage === 'preview'} disabled={!canPreviewPush || (!!pushStage && pushStage !== 'preview')} onClick={onPreviewPush}>
            预览推送
          </Button>
        </Tooltip>
        <Tooltip title={releaseTip}>
          <Button icon={<CloudUploadOutlined />} loading={pushStage === 'release'} disabled={!canPush || (!!pushStage && pushStage !== 'release')} onClick={onPush}>
            发布推送
          </Button>
        </Tooltip>
        <Tooltip title="导出当前工程包">
          <Button icon={<DownloadOutlined />} onClick={onExport}>
            导出
          </Button>
        </Tooltip>
        <Tooltip title="运行系统仿真">
          <Button icon={<ExperimentOutlined />} loading={status === 'simulating'} onClick={onSimulate}>
            运行仿真
          </Button>
        </Tooltip>
        <Button icon={<EllipsisOutlined />}>更多</Button>
        <Button type="text" icon={<SettingOutlined />} />
        <Button type="text" icon={<FullscreenOutlined />} />
      </Space>
    </div>
  );
}

function WorkflowProgress({
  steps,
}: {
  steps: Array<{ key: string; label: string; state: 'done' | 'active' | 'idle'; index: number }>;
}) {
  return (
    <div className="agent-workflow-strip">
      {steps.map((step) => (
        <div className={`agent-workflow-step ${step.state}`} key={step.key}>
          <span>{step.state === 'done' ? <CheckCircleOutlined /> : step.index}</span>
          <strong>{step.label}</strong>
        </div>
      ))}
    </div>
  );
}

function MagicDrawPendingPanel({
  projectResult,
  bridgeOnline,
  bridgeProjectOpen,
  bridgeProjectPathConfigured,
  status,
  onGenerate,
  onPreviewPush,
  onPush,
  canGenerate,
  canPreviewPush,
  canPush,
  pushStage,
}: {
  projectResult: SysMLProjectGenerateResult | null;
  bridgeOnline: boolean;
  bridgeProjectOpen: boolean | null;
  bridgeProjectPathConfigured: boolean;
  status: WorkStatus;
  onGenerate: () => void;
  onPreviewPush: () => void;
  onPush: () => void;
  canGenerate: boolean;
  canPreviewPush: boolean;
  canPush: boolean;
  pushStage: MagicDrawPushStage;
}) {
  const hasModel = !!projectResult;
  const bridgeWaitingForImport = bridgeOnline && bridgeProjectOpen === false && !bridgeProjectPathConfigured;
  const bridgeState = !bridgeOnline ? '未连接' : bridgeWaitingForImport ? '等待导入' : '可导入';
  return (
    <section className="agent-sync-pending">
      <div className="agent-sync-pending-card">
        <div className="agent-sync-pending-icon">
          {hasModel ? <CloudUploadOutlined /> : <BranchesOutlined />}
        </div>
        <div>
          <strong>{hasModel ? 'MagicDraw 等待推送' : '尚未生成SysML工程'}</strong>
          <span>
            {hasModel
              ? '可先推送到预览包检查MagicDraw效果；管理员审核合并入库后，再执行发布推送。'
              : '生成SysML工程后，这里会进入待预览状态；预览推送不会写入正式库。'}
          </span>
        </div>
        <Space wrap>
          {!hasModel && (
            <Button type="primary" icon={<BranchesOutlined />} loading={status === 'generating'} disabled={!canGenerate} onClick={onGenerate}>
              生成
            </Button>
          )}
          {hasModel && (
            <>
              <Tooltip title="推送到MagicDraw预览包，不写入正式库">
                <Button type="primary" icon={<CloudUploadOutlined />} loading={pushStage === 'preview'} disabled={!canPreviewPush || (!!pushStage && pushStage !== 'preview')} onClick={onPreviewPush}>
                  预览推送
                </Button>
              </Tooltip>
              <Tooltip title={canPush ? '正式发布到MagicDraw' : '等待管理员审核合并后发布'}>
                <Button icon={<CloudUploadOutlined />} loading={pushStage === 'release'} disabled={!canPush || (!!pushStage && pushStage !== 'release')} onClick={onPush}>
                  {canPush ? '发布推送' : '等待审核'}
                </Button>
              </Tooltip>
            </>
          )}
        </Space>
      </div>
      <div className="agent-sync-pending-metrics">
        <Metric label={hasModel ? '本地元素' : '待生成元素'} value={String(projectResult?.elements.length || 0)} compact />
        <Metric label={hasModel ? '本地关系' : '待生成关系'} value={String(projectResult?.relationships.length || 0)} compact />
        <Metric label="Bridge状态" value={bridgeState} compact warning={!bridgeOnline} />
        <Metric label="返回结果" value={hasModel ? (canPush ? '待发布' : '可预览') : '待生成'} compact warning={hasModel && !canPreviewPush} />
      </div>
    </section>
  );
}

function ChangeImpactPanel({
  elements,
  relationships,
  report,
  selectedId,
  projectName,
  taskContext,
  loading,
  onAnalyze,
  onSelectTarget,
}: {
  elements: ModelElement[];
  relationships: ModelRelationship[];
  report: ChangeImpactSandboxResponse | null;
  selectedId: string | null;
  projectName: string;
  taskContext: string;
  loading: boolean;
  onAnalyze: (payload: ChangeImpactSandboxRequest) => void;
  onSelectTarget: (id: string) => void;
}) {
  const [targetId, setTargetId] = useState(selectedId || elements[0]?.id || '');
  const [attributeName, setAttributeName] = useState('');
  const [oldValue, setOldValue] = useState('');
  const [newValue, setNewValue] = useState('');
  const [unit, setUnit] = useState('');
  const [changeDescription, setChangeDescription] = useState('');
  const [depth, setDepth] = useState(3);

  useEffect(() => {
    if (selectedId && selectedId !== targetId) {
      setTargetId(selectedId);
    } else if (!targetId && elements[0]?.id) {
      setTargetId(elements[0].id);
    }
  }, [selectedId, elements, targetId]);

  const target = elements.find((item) => item.id === targetId) || elements[0] || null;
  const targetOptions = elements.map((item) => ({
    value: item.id,
    label: `${item.id} ${item.name}`,
  }));

  function submit() {
    if (!target) return;
    const description =
      changeDescription.trim() ||
      `${target.name} ${attributeName || '参数'}由 ${oldValue || '原值'} 变更为 ${newValue || '目标值'}${unit || ''}`;
    onAnalyze({
      project_name: projectName,
      target_id: target.id,
      target_name: target.name,
      attribute_name: attributeName || '变更属性',
      old_value: oldValue,
      new_value: newValue,
      unit,
      change_description: description,
      task_context: taskContext,
      depth,
      relationships,
    });
  }

  if (!elements.length) {
    return (
      <section className="agent-impact-page empty">
        <div className="agent-impact-empty">
          <BranchesOutlined />
          <strong>尚未生成模型</strong>
          <span>生成 SysML 模型后，可在这里选择任意对象并执行沙箱变更影响分析。</span>
        </div>
      </section>
    );
  }

  return (
    <section className="agent-impact-page">
      <div className="agent-impact-config">
        <div className="agent-panel-title">
          <strong>沙箱变更</strong>
          <span>{projectName}</span>
        </div>
        <div className="agent-impact-fields">
          <Select
            size="small"
            value={targetId}
            options={targetOptions}
            onChange={(value) => {
              setTargetId(value);
              onSelectTarget(value);
            }}
          />
          <Input size="small" value={attributeName} placeholder="变更属性，如带宽/功率/轨道高度" onChange={(event) => setAttributeName(event.target.value)} />
          <Input size="small" value={oldValue} placeholder="原值" onChange={(event) => setOldValue(event.target.value)} />
          <Input size="small" value={newValue} placeholder="目标值" onChange={(event) => setNewValue(event.target.value)} />
          <Input size="small" value={unit} placeholder="单位" onChange={(event) => setUnit(event.target.value)} />
          <Select
            size="small"
            value={depth}
            options={[
              { value: 2, label: '2 层' },
              { value: 3, label: '3 层' },
              { value: 4, label: '4 层' },
            ]}
            onChange={setDepth}
          />
          <Input.TextArea
            className="agent-impact-description"
            value={changeDescription}
            rows={2}
            placeholder="变更说明，例如：将星间链路带宽由 500Mbps 提升到 1Gbps"
            onChange={(event) => setChangeDescription(event.target.value)}
          />
          <Space className="agent-impact-actions">
            <Tag color="blue">沙箱预演</Tag>
            <Tag color="default">{relationships.length} 条关系</Tag>
            <Button type="primary" icon={<ExperimentOutlined />} loading={loading} onClick={submit}>
              执行影响分析
            </Button>
          </Space>
        </div>
      </div>

      {report ? (
        <>
          <div className="agent-impact-summary">
            <Metric label="综合风险" value={riskLabel(report.risk_level)} compact warning={report.risk_level !== 'low'} />
            <Metric label="直接影响" value={String(report.direct_impacts.length)} compact warning={report.direct_impacts.some((item) => item.severity === 'high')} />
            <Metric label="间接影响" value={String(report.indirect_impacts.length)} compact warning={report.indirect_impacts.some((item) => item.severity === 'high')} />
            <Metric label="任务场景" value={taskProfileLabel(report.task_profile)} compact />
          </div>
          <div className="agent-impact-layout">
            <ChangeImpactTopology report={report} />
            <ChangeImpactMatrixTable rows={report.impact_matrix} />
          </div>
          <div className="agent-impact-notes">
            <div>
              <strong>建议操作</strong>
              {report.suggestions.map((item, index) => (
                <span key={`suggestion-${index}`}>{item}</span>
              ))}
            </div>
            <div>
              <strong>分析假设</strong>
              {report.assumptions.map((item, index) => (
                <span key={`assumption-${index}`}>{item}</span>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="agent-impact-empty">
          <ApartmentOutlined />
          <strong>等待沙箱分析</strong>
          <span>选择对象并填写变更内容后，系统会生成影响拓扑和影响矩阵。</span>
        </div>
      )}
    </section>
  );
}

function ChangeImpactTopology({ report }: { report: ChangeImpactSandboxResponse }) {
  const nodes = report.topology.nodes;
  const edges = report.topology.edges;
  const columns = [0, 1, 2];
  const width = 920;
  const nodeWidth = 190;
  const nodeHeight = 64;
  const xByLevel: Record<number, number> = { 0: 36, 1: 360, 2: 690 };
  const grouped = columns.map((level) => nodes.filter((node) => Math.min(2, node.level) === level));
  const height = Math.max(330, Math.max(...grouped.map((items) => items.length), 1) * 92 + 56);
  const positions = new Map<string, { x: number; y: number; width: number; height: number }>();

  grouped.forEach((items, columnIndex) => {
    const gap = height / (items.length + 1);
    items.forEach((node, index) => {
      positions.set(node.id, {
        x: xByLevel[columns[columnIndex]],
        y: Math.max(28, gap * (index + 1) - nodeHeight / 2),
        width: nodeWidth,
        height: nodeHeight,
      });
    });
  });

  return (
    <section className="agent-impact-topology">
      <div className="agent-panel-title">
        <strong>影响拓扑图</strong>
        <span>{report.summary}</span>
      </div>
      <div className="agent-impact-topology-canvas">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="change impact topology">
          <defs>
            <marker id="impact-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          </defs>
          <g>
            {edges.map((edge) => {
              const source = positions.get(edge.source);
              const target = positions.get(edge.target);
              if (!source || !target) return null;
              const sx = source.x + source.width;
              const sy = source.y + source.height / 2;
              const tx = target.x;
              const ty = target.y + target.height / 2;
              const mid = Math.max(48, (tx - sx) / 2);
              return (
                <g className={`agent-impact-edge ${edge.directness} ${edge.severity}`} key={edge.id}>
                  <path d={`M ${sx} ${sy} C ${sx + mid} ${sy}, ${tx - mid} ${ty}, ${tx} ${ty}`} markerEnd="url(#impact-arrow)" />
                  <text x={(sx + tx) / 2} y={(sy + ty) / 2 - 6}>
                    {edge.label}
                  </text>
                </g>
              );
            })}
          </g>
          <g>
            {nodes.map((node) => {
              const box = positions.get(node.id);
              if (!box) return null;
              const lines = splitLabel(node.label.replace(/\n/g, ' '), 11, 2);
              return (
                <g className={`agent-impact-node ${node.risk} level-${Math.min(2, node.level)}`} key={node.id}>
                  <rect x={box.x} y={box.y} width={box.width} height={box.height} rx="6" />
                  <text className="impact-node-type" x={box.x + box.width / 2} y={box.y + 18}>
                    {node.category}
                  </text>
                  {lines.map((line, index) => (
                    <text className="impact-node-name" x={box.x + box.width / 2} y={box.y + 40 + index * 15} key={`${node.id}-${line}`}>
                      {line}
                    </text>
                  ))}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}

function ChangeImpactMatrixTable({ rows }: { rows: ChangeImpactMatrixRow[] }) {
  const columns: ColumnsType<ChangeImpactMatrixRow> = [
    { title: '对象', dataIndex: 'affected_object', width: 180 },
    { title: '影响', dataIndex: 'impact_type', width: 120 },
    {
      title: '层级',
      dataIndex: 'directness',
      width: 86,
      render: (value: ChangeImpactMatrixRow['directness']) => <Tag color={value === 'direct' ? 'blue' : 'purple'}>{value === 'direct' ? '直接' : '间接'}</Tag>,
    },
    {
      title: '风险',
      dataIndex: 'severity',
      width: 82,
      render: (value: ChangeImpactMatrixRow['severity']) => <Tag color={riskTagColor(value)}>{riskLabel(value)}</Tag>,
    },
    { title: '路径', dataIndex: 'path', width: 240 },
    { title: '原因', dataIndex: 'reason', width: 260 },
    { title: '建议', dataIndex: 'recommendation', width: 240 },
  ];

  return (
    <section className="agent-impact-matrix">
      <div className="agent-panel-title">
        <strong>影响矩阵</strong>
        <span>共 {rows.length} 项</span>
      </div>
      <Table size="small" rowKey="id" columns={columns} dataSource={rows} pagination={{ pageSize: 6 }} scroll={{ x: 1210 }} />
    </section>
  );
}

function MergeManagementPanel({
  loading,
  mergeRequests,
  role,
  selectedMergeRequest,
  onMerge,
  onRefresh,
  onReject,
  onResolve,
  onSelect,
  onSubmitCurrent,
}: {
  loading: boolean;
  mergeRequests: MergeRequestRecord[];
  role: 'admin' | 'designer';
  selectedMergeRequest: MergeRequestRecord | null;
  onMerge: (mergeRequestId: number) => void;
  onRefresh: () => void;
  onReject: (mergeRequestId: number) => void;
  onResolve: (mergeRequestId: number, conflictId: string, resolution: 'use_candidate' | 'keep_release') => void;
  onSelect: (mergeRequestId: number) => void;
  onSubmitCurrent?: () => void;
}) {
  const rows = selectedMergeRequest ? buildMergeChangeRows(selectedMergeRequest) : [];
  const unresolvedCount = selectedMergeRequest?.conflicts.filter((item) => !item.resolved).length || 0;
  const canReview = role === 'admin' && !!selectedMergeRequest && !['merged', 'rejected'].includes(selectedMergeRequest.status);
  const canMerge = canReview && unresolvedCount === 0;
  const changeColumns: ColumnsType<ReturnType<typeof buildMergeChangeRows>[number]> = [
    { title: '类型', dataIndex: 'object_type', width: 92, render: (value) => mergeObjectTypeLabel(String(value)) },
    { title: '动作', dataIndex: 'action', width: 92, render: (value) => <Tag color={mergeActionColor(String(value))}>{mergeActionLabel(String(value))}</Tag> },
    { title: '对象', dataIndex: 'name', width: 220 },
    { title: '字段变化', dataIndex: 'diff_text' },
  ];

  return (
    <section className="agent-merge-page">
      <aside className="agent-merge-list">
        <div className="agent-panel-title">
          <strong>合并请求</strong>
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
        </div>
        {onSubmitCurrent && (
          <Button block type="primary" icon={<CloudUploadOutlined />} loading={loading} onClick={onSubmitCurrent}>
            提交当前草稿
          </Button>
        )}
        <div className="agent-merge-request-list">
          {mergeRequests.length ? (
            mergeRequests.map((item) => (
              <button
                className={`agent-merge-request-item ${selectedMergeRequest?.id === item.id ? 'active' : ''}`}
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
              >
                <span>MR-{String(item.id).padStart(4, '0')}</span>
                <strong>{item.title || item.project_name}</strong>
                <Tag color={mergeStatusColor(item.status)}>{mergeStatusLabel(item.status)}</Tag>
              </button>
            ))
          ) : (
            <div className="agent-merge-empty">
              <DatabaseOutlined />
              <strong>暂无合并请求</strong>
              <span>{role === 'admin' ? '等待设计师提交入库审核。' : '当前项目还没有提交审核。'}</span>
            </div>
          )}
        </div>
      </aside>

      <div className="agent-merge-detail">
        {selectedMergeRequest ? (
          <>
            <div className="agent-merge-header">
              <div>
                <strong>MR-{String(selectedMergeRequest.id).padStart(4, '0')} {selectedMergeRequest.title}</strong>
                <span>
                  {selectedMergeRequest.source_branch}
                  {' -> '}
                  {selectedMergeRequest.target_branch}
                </span>
              </div>
              <Space wrap>
                <Tag color={mergeStatusColor(selectedMergeRequest.status)}>{mergeStatusLabel(selectedMergeRequest.status)}</Tag>
                <Tag color="blue">提交人 {selectedMergeRequest.submitter}</Tag>
                <Tag color={unresolvedCount ? 'red' : 'green'}>未解决冲突 {unresolvedCount}</Tag>
                <Button danger disabled={!canReview} loading={loading} onClick={() => onReject(selectedMergeRequest.id)}>
                  拒绝
                </Button>
                <Button type="primary" disabled={!canMerge} loading={loading} icon={<CheckCircleOutlined />} onClick={() => onMerge(selectedMergeRequest.id)}>
                  合并入库
                </Button>
              </Space>
            </div>

            <div className="agent-merge-metrics">
              <Metric label="新增元素" value={String(mergeSummaryValue(selectedMergeRequest, 'elements_added'))} compact />
              <Metric label="修改元素" value={String(mergeSummaryValue(selectedMergeRequest, 'elements_modified'))} compact warning={mergeSummaryValue(selectedMergeRequest, 'elements_modified') > 0} />
              <Metric label="新增关系" value={String(mergeSummaryValue(selectedMergeRequest, 'relationships_added'))} compact />
              <Metric label="冲突点" value={String(selectedMergeRequest.conflicts.length)} compact warning={selectedMergeRequest.conflicts.length > 0} />
            </div>

            <div className="agent-merge-workspace">
              <section className="agent-merge-change-table">
                <div className="agent-panel-title">
                  <strong>实体变更清单</strong>
                  <span>绿色新增、蓝色修改、橙色冲突</span>
                </div>
                <Table size="small" rowKey="key" columns={changeColumns} dataSource={rows} pagination={{ pageSize: 6 }} />
              </section>
              <section className="agent-merge-conflicts">
                <div className="agent-panel-title">
                  <strong>冲突解决</strong>
                  <span>{role === 'admin' ? '管理员审核并选择合并策略' : '设计师只读查看审核状态'}</span>
                </div>
                {selectedMergeRequest.conflicts.length ? (
                  selectedMergeRequest.conflicts.map((conflict) => (
                    <MergeConflictRow
                      conflict={conflict}
                      disabled={role !== 'admin' || selectedMergeRequest.status === 'merged' || selectedMergeRequest.status === 'rejected'}
                      key={conflict.id}
                      loading={loading}
                      mergeRequestId={selectedMergeRequest.id}
                      onResolve={onResolve}
                    />
                  ))
                ) : (
                  <div className="agent-merge-no-conflict">
                    <CheckCircleOutlined />
                    <strong>未发现冲突，可由管理员直接合并入库。</strong>
                  </div>
                )}
              </section>
            </div>

            <section className="agent-merge-audit">
              <div className="agent-panel-title">
                <strong>操作日志审计</strong>
                <span>记录提交、冲突处理和入库操作</span>
              </div>
              <div className="agent-merge-audit-list">
                {selectedMergeRequest.audit_logs.map((log) => (
                  <div className="agent-merge-audit-row" key={log.id}>
                    <span>{formatAuditTime(log.created_at)}</span>
                    <strong>{log.operator}</strong>
                    <em>{log.role}</em>
                    <p>{log.message}</p>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : (
          <div className="agent-merge-empty large">
            <DatabaseOutlined />
            <strong>等待合并请求</strong>
            <span>设计师提交审核后，管理员可在这里完成冲突合并与数据入库。</span>
          </div>
        )}
      </div>
    </section>
  );
}

function MergeConflictRow({
  conflict,
  disabled,
  loading,
  mergeRequestId,
  onResolve,
}: {
  conflict: MergeConflictRecord;
  disabled: boolean;
  loading: boolean;
  mergeRequestId: number;
  onResolve: (mergeRequestId: number, conflictId: string, resolution: 'use_candidate' | 'keep_release') => void;
}) {
  return (
    <div className={`agent-merge-conflict-row ${conflict.resolved ? 'resolved' : ''}`}>
      <div>
        <Tag color={conflict.severity === 'high' ? 'red' : 'gold'}>{conflict.resolved ? '已解决' : '冲突'}</Tag>
        <strong>{conflict.message}</strong>
        <span>
          {mergeObjectTypeLabel(conflict.object_type)} {conflict.object_id} / {conflict.field}
        </span>
      </div>
      <div className="agent-merge-conflict-values">
        <span>发布：{stringifyCell(conflict.release_value)}</span>
        <span>开发：{stringifyCell(conflict.candidate_value)}</span>
      </div>
      <Space className="agent-merge-conflict-actions" wrap>
        <Button size="small" disabled={disabled || conflict.resolved} loading={loading} onClick={() => onResolve(mergeRequestId, conflict.id, 'keep_release')}>
          保留发布
        </Button>
        <Button size="small" type="primary" disabled={disabled || conflict.resolved} loading={loading} onClick={() => onResolve(mergeRequestId, conflict.id, 'use_candidate')}>
          采用开发
        </Button>
      </Space>
    </div>
  );
}

function riskLabel(risk: 'low' | 'medium' | 'high') {
  if (risk === 'high') return '高';
  if (risk === 'medium') return '中';
  return '低';
}

function riskTagColor(risk: 'low' | 'medium' | 'high') {
  if (risk === 'high') return 'red';
  if (risk === 'medium') return 'gold';
  return 'green';
}

function taskProfileLabel(profile: string) {
  if (profile === 'communication_satellite') return '通信卫星';
  if (profile === 'remote_sensing') return '遥感任务';
  if (profile === 'navigation') return '导航任务';
  if (profile === 'flight_control') return '飞控任务';
  return '通用系统';
}

function buildMergeChangeRows(request: MergeRequestRecord) {
  const groups = [
    ['elements_added', 'element', 'add'],
    ['elements_modified', 'element', 'modify'],
    ['relationships_added', 'relationship', 'add'],
    ['relationships_modified', 'relationship', 'modify'],
  ] as const;
  return groups.flatMap(([key, objectType, action]) => {
    const items = Array.isArray(request.change_set[key]) ? (request.change_set[key] as Array<Record<string, unknown>>) : [];
    return items.map((item, index) => ({
      key: `${key}-${String(item.id || index)}`,
      object_type: objectType,
      action,
      name: String(item.name || item.id || '--'),
      diff_text: mergeDiffText(item.diff),
    }));
  });
}

function mergeDiffText(value: unknown) {
  if (!value || typeof value !== 'object') return '新增对象';
  const diff = value as Record<string, { release?: unknown; candidate?: unknown }>;
  const entries = Object.entries(diff);
  if (!entries.length) return '新增对象';
  return entries.map(([field, item]) => `${field}: ${stringifyCell(item.release)} -> ${stringifyCell(item.candidate)}`).join('；');
}

function mergeSummaryValue(request: MergeRequestRecord, key: string) {
  const summary = (request.change_set.summary || {}) as Record<string, unknown>;
  const value = Number(summary[key] || 0);
  return Number.isFinite(value) ? value : 0;
}

function mergeStatusLabel(status: string) {
  if (status === 'merged') return '已合并';
  if (status === 'rejected') return '已拒绝';
  if (status === 'conflict') return '有冲突';
  return '待审核';
}

function mergeStatusColor(status: string) {
  if (status === 'merged') return 'green';
  if (status === 'rejected') return 'red';
  if (status === 'conflict') return 'gold';
  return 'blue';
}

function mergeActionLabel(action: string) {
  if (action === 'add') return '新增';
  if (action === 'modify') return '修改';
  if (action === 'delete') return '删除';
  return action;
}

function mergeActionColor(action: string) {
  if (action === 'add') return 'green';
  if (action === 'modify') return 'blue';
  if (action === 'delete') return 'red';
  return 'default';
}

function mergeObjectTypeLabel(value: string) {
  if (value === 'relationship') return '关系';
  if (value === 'element') return '实体';
  return value;
}

function stringifyCell(value: unknown) {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

function formatAuditTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function DraftReviewBar({
  hasReport,
  result,
  status,
  onAccept,
  onEdit,
  onOpenReport,
  onReject,
  onValidate,
}: {
  hasReport: boolean;
  result: SysMLProjectGenerateResult;
  status: WorkStatus;
  onAccept: () => void;
  onEdit: () => void;
  onOpenReport: () => void;
  onReject: () => void;
  onValidate: () => void;
}) {
  const draftStatus = result.draft_status || 'preview';
  const accepted = draftStatus === 'accepted';
  const rejected = draftStatus === 'rejected';
  const revised = draftStatus === 'revised';
  const submitted = draftStatus === 'submitted';
  return (
    <section className={`agent-draft-review ${accepted ? 'accepted' : rejected ? 'rejected' : revised || submitted ? 'revised' : ''}`}>
      <div>
        <strong>预览与确认</strong>
        <span>{draftReviewText(draftStatus, result.draft_id)}</span>
      </div>
      <Space wrap>
        <Tag color={accepted ? 'green' : rejected ? 'red' : revised || submitted ? 'gold' : 'blue'}>
          {draftStatusLabel(draftStatus)}
        </Tag>
        <Button icon={<EditOutlined />} disabled={accepted || rejected || submitted || !result.elements.length} onClick={onEdit}>
          人工修改
        </Button>
        <Button loading={status === 'validating'} disabled={!result.draft_id} onClick={hasReport ? onOpenReport : onValidate}>
          {hasReport ? '预评审报告' : '执行模型校验'}
        </Button>
        {hasReport && (
          <Button loading={status === 'validating'} disabled={!result.draft_id} onClick={onValidate}>
            重新校验
          </Button>
        )}
        <Button danger disabled={accepted || rejected || submitted} onClick={onReject}>
          拒绝
        </Button>
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={status === 'submitting'}
          disabled={accepted || rejected || submitted}
          onClick={onAccept}
        >
          {accepted ? '已合并入库' : submitted ? '已提交审核' : '提交合并请求'}
        </Button>
      </Space>
    </section>
  );
}

function DraftManualEditPanel({
  element,
  elements,
  relationship,
  relationships,
  selectedElementId,
  selectedRelationshipId,
  loading,
  onCreateRelationship,
  onDeleteRelationship,
  onSelectElement,
  onSelectRelationship,
  onUpdateElement,
  onUpdateRelationship,
}: {
  element: ModelElement | null;
  elements: ModelElement[];
  relationship: ModelRelationship | null;
  relationships: ModelRelationship[];
  selectedElementId: string;
  selectedRelationshipId: string;
  loading: boolean;
  onCreateRelationship: (patch: { source: string; target: string; type: string; description?: string }) => void;
  onDeleteRelationship: (relationshipId: string) => void;
  onSelectElement: (id: string) => void;
  onSelectRelationship: (id: string | null) => void;
  onUpdateElement: (elementId: string, patch: { name: string; type: string; description?: string; package?: string | null; source_requirement?: string | null; status?: string }) => void;
  onUpdateRelationship: (relationshipId: string, patch: { source: string; target: string; type: string; description?: string }) => void;
}) {
  return (
    <section className="agent-manual-edit-panel">
      <ElementEditor
        element={element}
        elements={elements}
        loading={loading}
        selectedElementId={selectedElementId}
        onSave={onUpdateElement}
        onSelectElement={onSelectElement}
      />
      <RelationshipEditor
        elements={elements}
        loading={loading}
        relationship={relationship}
        relationships={relationships}
        selectedRelationshipId={selectedRelationshipId}
        onCreate={onCreateRelationship}
        onDelete={onDeleteRelationship}
        onSave={onUpdateRelationship}
        onSelectRelationship={onSelectRelationship}
      />
    </section>
  );
}

function ElementEditor({
  element,
  elements,
  selectedElementId,
  loading,
  onSelectElement,
  onSave,
}: {
  element: ModelElement | null;
  elements: ModelElement[];
  selectedElementId: string;
  loading: boolean;
  onSelectElement: (id: string) => void;
  onSave: (elementId: string, patch: { name: string; type: string; description?: string; package?: string | null; source_requirement?: string | null; status?: string }) => void;
}) {
  const [name, setName] = useState(element?.name || '');
  const [type, setType] = useState(element?.type || 'Block');
  const [packageName, setPackageName] = useState(element?.package || defaultPackage(element?.type || 'Block'));
  const [sourceRequirement, setSourceRequirement] = useState(element?.source_requirement || '');
  const [statusValue, setStatusValue] = useState(element?.status || 'candidate');
  const [description, setDescription] = useState(element?.description || '');

  useEffect(() => {
    setName(element?.name || '');
    setType(element?.type || 'Block');
    setPackageName(element?.package || defaultPackage(element?.type || 'Block'));
    setSourceRequirement(element?.source_requirement || '');
    setStatusValue(element?.status || 'candidate');
    setDescription(element?.description || '');
  }, [element]);

  const elementOptions = elements.map((item) => ({ value: item.id, label: `${item.id} ${item.name}` }));
  const unchanged =
    !!element &&
    name === element.name &&
    type === element.type &&
    packageName === (element.package || defaultPackage(element.type)) &&
    sourceRequirement === (element.source_requirement || '') &&
    statusValue === element.status &&
    description === element.description;

  return (
    <div className="agent-element-editor">
      <div className="agent-editor-title">
        <strong>元素编辑</strong>
        <span>修改名称、类型、描述和包路径</span>
      </div>
      <div className="agent-element-fields">
        <Select size="small" value={selectedElementId} options={elementOptions} onChange={onSelectElement} />
        <Input size="small" value={name} placeholder="元素名称" onChange={(event) => setName(event.target.value)} />
        <Select size="small" value={type} options={modelElementTypeOptions()} onChange={(value) => setType(value)} />
        <Select size="small" value={packageName} options={packageOptions()} onChange={setPackageName} />
        <Input size="small" value={sourceRequirement} placeholder="来源需求，可为空" onChange={(event) => setSourceRequirement(event.target.value)} />
        <Select size="small" value={statusValue} options={modelStatusOptions()} onChange={setStatusValue} />
        <Input className="agent-field-wide" size="small" value={description} placeholder="元素描述" onChange={(event) => setDescription(event.target.value)} />
      </div>
      <Space className="agent-editor-actions">
        <Button
          size="small"
          onClick={() => {
            setName(element?.name || '');
            setType(element?.type || 'Block');
            setPackageName(element?.package || defaultPackage(element?.type || 'Block'));
            setSourceRequirement(element?.source_requirement || '');
            setStatusValue(element?.status || 'candidate');
            setDescription(element?.description || '');
          }}
        >
          重置
        </Button>
        <Button
          size="small"
          type="primary"
          loading={loading}
          disabled={!element || unchanged || !name.trim()}
          onClick={() =>
            element &&
            onSave(element.id, {
              name,
              type,
              description,
              package: packageName,
              source_requirement: sourceRequirement || null,
              status: statusValue,
            })
          }
        >
          保存元素
        </Button>
      </Space>
    </div>
  );
}

function RelationshipEditor({
  elements,
  relationship,
  relationships,
  selectedRelationshipId,
  loading,
  onCreate,
  onDelete,
  onSelectRelationship,
  onSave,
}: {
  elements: ModelElement[];
  relationship: ModelRelationship | null;
  relationships: ModelRelationship[];
  selectedRelationshipId: string;
  loading: boolean;
  onCreate: (patch: { source: string; target: string; type: string; description?: string }) => void;
  onDelete: (relationshipId: string) => void;
  onSelectRelationship: (id: string | null) => void;
  onSave: (relationshipId: string, patch: { source: string; target: string; type: string; description?: string }) => void;
}) {
  const [mode, setMode] = useState<'edit' | 'create'>(relationships.length ? 'edit' : 'create');
  const [source, setSource] = useState(relationship?.source || elements[0]?.id || '');
  const [target, setTarget] = useState(relationship?.target || elements[1]?.id || elements[0]?.id || '');
  const [type, setType] = useState(relationship?.type || 'trace');
  const [description, setDescription] = useState(relationship?.description || '');

  useEffect(() => {
    if (!relationships.length) setMode('create');
  }, [relationships.length]);

  useEffect(() => {
    if (mode !== 'edit') return;
    setSource(relationship?.source || elements[0]?.id || '');
    setTarget(relationship?.target || elements[1]?.id || elements[0]?.id || '');
    setType(relationship?.type || 'trace');
    setDescription(relationship?.description || '');
  }, [relationship, elements, mode]);

  useEffect(() => {
    if (mode !== 'create') return;
    setSource(elements[0]?.id || '');
    setTarget(elements[1]?.id || elements[0]?.id || '');
    setType('trace');
    setDescription('');
  }, [elements, mode]);

  const elementOptions = elements.map((item) => ({ value: item.id, label: `${item.id} ${item.name}` }));
  const relationshipOptions = relationships.map((item) => ({
    value: item.id,
    label: `${item.id} ${item.source} -> ${item.target}`,
  }));
  const unchanged =
    mode === 'edit' &&
    !!relationship &&
    source === relationship.source &&
    target === relationship.target &&
    type === relationship.type &&
    description === (relationship.description || '');
  const canSubmit = !!source && !!target && (mode === 'create' || !!relationship);

  return (
    <div className="agent-relationship-editor">
      <div className="agent-editor-title">
        <strong>连接线编辑</strong>
        <span>新增、删除或调整关系后会同步重算SysML文本</span>
      </div>
      <div className="agent-relationship-fields">
        <Segmented
          size="small"
          value={mode}
          options={[
            { value: 'edit', label: '修改已有', disabled: !relationships.length },
            { value: 'create', label: '新增连接线' },
          ]}
          onChange={(value) => setMode(value as 'edit' | 'create')}
        />
        {mode === 'edit' && (
          <Select size="small" value={selectedRelationshipId || undefined} options={relationshipOptions} placeholder="选择关系" onChange={onSelectRelationship} />
        )}
        <Select size="small" value={source} options={elementOptions} placeholder="源元素" onChange={setSource} />
        <Select size="small" value={target} options={elementOptions} placeholder="目标元素" onChange={setTarget} />
        <Select size="small" value={type} options={relationshipTypeOptions()} onChange={setType} />
        <Input className="agent-field-wide" size="small" value={description} placeholder="关系说明" onChange={(event) => setDescription(event.target.value)} />
      </div>
      <Space className="agent-editor-actions">
        <Button
          size="small"
          onClick={() => {
            if (mode === 'edit') {
              setSource(relationship?.source || elements[0]?.id || '');
              setTarget(relationship?.target || elements[1]?.id || elements[0]?.id || '');
              setType(relationship?.type || 'trace');
              setDescription(relationship?.description || '');
            } else {
              setSource(elements[0]?.id || '');
              setTarget(elements[1]?.id || elements[0]?.id || '');
              setType('trace');
              setDescription('');
            }
          }}
        >
          重置
        </Button>
        {mode === 'edit' && relationship && (
          <Button danger size="small" icon={<DeleteOutlined />} loading={loading} onClick={() => onDelete(relationship.id)}>
            删除
          </Button>
        )}
        <Button
          size="small"
          type="primary"
          loading={loading}
          disabled={!canSubmit || (mode === 'edit' && unchanged)}
          onClick={() =>
            mode === 'create'
              ? onCreate({ source, target, type, description })
              : relationship && onSave(relationship.id, { source, target, type, description })
          }
        >
          {mode === 'create' ? '新增连接线' : '保存关系'}
        </Button>
      </Space>
    </div>
  );
}

function PreReviewReportModal({
  loading,
  onClose,
  onFix,
  onRunValidation,
  open,
  report,
  validating,
}: {
  loading: boolean;
  onClose: () => void;
  onFix: (issueIds: string[]) => void;
  onRunValidation: () => void;
  open: boolean;
  report: DraftValidationReport | null;
  validating: boolean;
}) {
  const fixableIssues = report?.issues.filter((issue) => issue.fixable) || [];
  const footer = [
    <Button key="rerun" loading={validating} onClick={onRunValidation}>
      重新校验
    </Button>,
    <Button key="close" onClick={onClose}>
      关闭
    </Button>,
    <Button
      disabled={!fixableIssues.length}
      key="fix-all"
      loading={loading}
      type="primary"
      onClick={() => onFix(fixableIssues.map((issue) => issue.id))}
    >
      修复全部可修复项
    </Button>,
  ];

  return (
    <Modal
      className="agent-pre-review-modal"
      footer={footer}
      onCancel={onClose}
      open={open}
      title="预评审报告"
      width={920}
    >
      {!report ? (
        <div className="agent-pre-review-empty">
          <strong>尚未执行模型校验</strong>
          <Button loading={validating} type="primary" onClick={onRunValidation}>
            执行模型校验
          </Button>
        </div>
      ) : (
        <div className="agent-pre-review-report">
          <div className="agent-pre-review-summary">
            <Progress percent={report.score} size={84} strokeColor={report.score >= 90 ? '#16a34a' : report.score >= 75 ? '#f59e0b' : '#dc2626'} type="circle" />
            <div>
              <strong>{report.conclusion}</strong>
              <span>
                错误 {report.statistics.error_count || 0} / 警告 {report.statistics.warning_count || 0} / 提示 {report.statistics.info_count || 0} / 可修复 {report.statistics.fixable_count || 0}
              </span>
            </div>
          </div>
          <div className="agent-pre-review-issues">
            {report.issues.length ? (
              report.issues.map((issue) => (
                <PreReviewIssueRow issue={issue} key={issue.id} loading={loading} onFix={onFix} />
              ))
            ) : (
              <div className="agent-pre-review-pass">
                <CheckCircleOutlined />
                <strong>未发现规则问题</strong>
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function PreReviewIssueRow({
  issue,
  loading,
  onFix,
}: {
  issue: DraftValidationIssue;
  loading: boolean;
  onFix: (issueIds: string[]) => void;
}) {
  return (
    <div className={`agent-pre-review-issue ${issue.severity}`}>
      <div>
        <Tag color={issueSeverityColor(issue.severity)}>{issueSeverityLabel(issue.severity)}</Tag>
        <strong>{issue.message}</strong>
        <span>{issue.object_id} · {issue.rule_id}</span>
      </div>
      <p>{issue.suggestion}</p>
      <Button disabled={!issue.fixable} loading={loading} size="small" type={issue.fixable ? 'primary' : 'default'} onClick={() => onFix([issue.id])}>
        {issue.fixable ? '一键修复' : '需人工确认'}
      </Button>
    </div>
  );
}

function issueSeverityColor(severity: DraftValidationIssue['severity']) {
  if (severity === 'error') return 'red';
  if (severity === 'warning') return 'gold';
  return 'blue';
}

function issueSeverityLabel(severity: DraftValidationIssue['severity']) {
  if (severity === 'error') return '错误';
  if (severity === 'warning') return '警告';
  return '提示';
}

function generationSourceLabel(source?: string) {
  if (source === 'llm') return 'AI生成';
  if (source === 'curated_fallback') return '模板兜底';
  if (source === 'dynamic_fallback') return '动态兜底';
  return '未知';
}

function modelElementTypeOptions() {
  return [
    { value: 'Requirement', label: 'Requirement' },
    { value: 'Block', label: 'Block' },
    { value: 'UseCase', label: 'UseCase' },
    { value: 'Activity', label: 'Activity' },
    { value: 'Interface', label: 'Interface' },
    { value: 'ConstraintBlock', label: 'ConstraintBlock' },
  ];
}

function packageOptions() {
  return [
    { value: '01_Requirements', label: '01_Requirements' },
    { value: '02_Structure', label: '02_Structure' },
    { value: '03_Behavior', label: '03_Behavior' },
    { value: '04_Interfaces', label: '04_Interfaces' },
    { value: '05_Constraints', label: '05_Constraints' },
    { value: '06_Traceability', label: '06_Traceability' },
  ];
}

function modelStatusOptions() {
  return [
    { value: 'candidate', label: 'candidate' },
    { value: 'revised', label: 'revised' },
    { value: 'reviewed', label: 'reviewed' },
  ];
}

function relationshipTypeOptions() {
  return ['contains', 'satisfy', 'trace', 'refine', 'allocate', 'verify', 'dependency'].map((item) => ({
    value: item,
    label: item,
  }));
}

function draftStatusLabel(status?: string) {
  if (status === 'accepted') return '已入库';
  if (status === 'rejected') return '已拒绝';
  if (status === 'submitted') return '待审核';
  if (status === 'revised') return '已修正';
  return '候选方案';
}

function draftReviewText(status: string, draftId?: number | null) {
  const prefix = draftId ? `草稿 #${draftId}` : '当前草稿';
  if (status === 'accepted') return `${prefix} 已写入模型库，可以继续推送MagicDraw。`;
  if (status === 'rejected') return `${prefix} 已记录为拒绝反馈，不会入库。`;
  if (status === 'submitted') return `${prefix} 已提交合并请求，等待管理员审核并合并入库。`;
  if (status === 'revised') return `${prefix} 已包含人工修正，提交审核后将以修正后的模型进入入库流程。`;
  return `${prefix} 尚未入库，可先修正模型，确认后提交合并请求。`;
}

function isDraftAccepted(result: SysMLProjectGenerateResult | null) {
  return !!result && result.draft_status === 'accepted';
}

function isPreviewPublish(result: MagicDrawPublishResult | null) {
  return !!result && result.package_name.startsWith('PREVIEW_');
}

function isDraftEditable(result: SysMLProjectGenerateResult | null) {
  return !!result && result.draft_status !== 'accepted' && result.draft_status !== 'rejected';
}

function GenerationStatusBar({
  generatedAt,
  generationDuration,
  projectResult,
  publishResult,
  validation,
}: {
  generatedAt: string;
  generationDuration: string;
  projectResult: SysMLProjectGenerateResult | null;
  publishResult: MagicDrawPublishResult | null;
  validation: PreviewValidation;
}) {
  const status = !projectResult
    ? '等待生成'
    : publishResult
      ? isPreviewPublish(publishResult)
        ? '已预览'
        : '已发布'
      : !isDraftAccepted(projectResult)
        ? draftStatusLabel(projectResult.draft_status)
        : validation.status === 'warn'
          ? '需校验'
          : '已采纳';
  return (
    <div className={`agent-generation-status ${validation.status === 'warn' ? 'warning' : projectResult ? 'ok' : ''}`}>
      <div>
        <CheckCircleOutlined />
        <span>生成状态</span>
        <strong>{status}</strong>
      </div>
      <div>
        <span>元素数量</span>
        <strong>{projectResult?.elements.length || 0}</strong>
      </div>
      <div>
        <span>关系数量</span>
        <strong>{projectResult?.relationships.length || 0}</strong>
      </div>
      <div>
        <span>生成来源</span>
        <strong>{generationSourceLabel(projectResult?.generation_source)}</strong>
      </div>
      <div>
        <span>生成耗时</span>
        <strong>{generationDuration}</strong>
      </div>
      <div>
        <span>生成时间</span>
        <strong>{generatedAt}</strong>
      </div>
    </div>
  );
}

function PreviewValidationPanel({
  validation,
  publishResult,
}: {
  validation: PreviewValidation;
  publishResult: MagicDrawPublishResult | null;
}) {
  const title = validation.status === 'idle' ? '等待预览校验' : validation.status === 'pass' ? '预览校验通过' : '预览校验待处理';
  const detail =
    validation.status === 'idle'
      ? '生成SysML工程后，将检查元素、关系、SysML文本和前端画布是否同源。推送MagicDraw后会校验Bridge返回布局。'
      : validation.issues.length
        ? validation.issues.join('；')
        : '元素、关系和预览布局数量一致，可进入MagicDraw推送或复核。';

  return (
    <div className={`agent-validation-panel ${validation.status}`}>
      <div>
        <CheckCircleOutlined />
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <div className="agent-validation-metrics">
        <Metric label="模型元素" value={String(validation.elementCount)} compact />
        <Metric label="模型关系" value={String(validation.relationshipCount)} compact />
        <Metric label="画布节点" value={String(validation.layoutNodeCount)} compact warning={validation.layoutNodeCount !== validation.elementCount} />
        <Metric label="画布连线" value={String(validation.layoutEdgeCount)} compact warning={validation.layoutEdgeCount > validation.relationshipCount} />
      </div>
    </div>
  );
}

function ModelExplorer({
  groups,
  projectName,
  selectedId,
  onSelect,
}: {
  groups: Array<{ packageName: string; elements: ModelElement[] }>;
  projectName: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="agent-explorer">
      <div className="agent-panel-title">
        <strong>工程浏览器</strong>
        <Button size="small" icon={<CompressOutlined />} />
      </div>
      <Input size="small" prefix={<SearchOutlined />} placeholder="搜索模型元素" />
      <div className="agent-tree-root">
        <FolderOpenOutlined /> {projectName}
      </div>
      <div className="agent-tree">
        {groups.map((group) => (
          <div className="agent-tree-group" key={group.packageName}>
            <div className="agent-tree-package">
              <FolderOpenOutlined /> {packageLabel(group.packageName)}
            </div>
            {group.elements.slice(0, 8).map((item) => (
              <button
                className={`agent-tree-node ${selectedId === item.id ? 'selected' : ''}`}
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
              >
                <FileTextOutlined />
                <span>{item.id}</span>
                <strong>{item.name}</strong>
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="agent-explorer-footer">
        <Button size="small" icon={<ReloadOutlined />}>
          刷新
        </Button>
        <Button size="small" icon={<SearchOutlined />}>
          过滤器
        </Button>
      </div>
    </section>
  );
}

function DiagramPanel({
  elements,
  relationships,
  layout,
  diagramViews = [],
  selectedId,
  selectedRelationshipId,
  onSelect,
  onSelectRelationship,
  onOpenInternalDiagram,
}: {
  elements: ModelElement[];
  relationships: ModelRelationship[];
  layout?: MagicDrawDiagramLayout | null;
  diagramViews?: SysMLDiagramView[];
  selectedId: string | null;
  selectedRelationshipId: string | null;
  onSelect: (id: string) => void;
  onSelectRelationship: (id: string) => void;
  onOpenInternalDiagram: (id?: string) => void;
}) {
  const [activeDiagramViewId, setActiveDiagramViewId] = useState('canvas');
  const diagram = useMemo(() => buildDiagram(elements, relationships), [elements, relationships]);
  const layoutDrawing = useMemo(() => (layout ? buildLayoutDrawing(layout) : null), [layout]);
  const displayDiagramViews = useMemo(() => uniqueDiagramViews(diagramViews).filter(diagramViewHasCanvas), [diagramViews]);
  const activeDiagramView = activeDiagramViewId === 'canvas' ? null : displayDiagramViews.find((view) => view.id === activeDiagramViewId) || null;
  const diagramViewOptions = useMemo(
    () => [
      { value: 'canvas', label: '统一画布' },
      ...displayDiagramViews.map((view) => ({
        value: view.id,
        label: `${diagramTypeShortLabel(view.diagram_type)} · ${view.name}`,
      })),
    ],
    [displayDiagramViews],
  );
  const hasLayoutDrawing = !!layoutDrawing?.nodes.length;
  useEffect(() => {
    if (activeDiagramViewId !== 'canvas' && !displayDiagramViews.some((view) => view.id === activeDiagramViewId)) {
      setActiveDiagramViewId('canvas');
    }
  }, [activeDiagramViewId, displayDiagramViews]);

  return (
    <section className="agent-diagram-panel">
      <div className="agent-diagram-title">
        <div>
          <strong>模型画布</strong>
          <span>
            {activeDiagramView
              ? `${diagramTypeLabel(activeDiagramView.diagram_type)} · ${activeDiagramView.name}`
              : hasLayoutDrawing
                ? `${layout?.diagram_name || 'AI_MBSE_Trace_View'}（统一布局）`
                : '需求视图图（Requirements Diagram）'}
          </span>
        </div>
        <Space size={6}>
          {displayDiagramViews.length > 0 && (
            <Select
              className="agent-diagram-view-select"
              size="small"
              value={activeDiagramViewId}
              options={diagramViewOptions}
              onChange={setActiveDiagramViewId}
            />
          )}
          <Button size="small" icon={<FullscreenOutlined />} />
        </Space>
      </div>
      <div className="agent-canvas-toolbar">
        <Button size="small" icon={<BranchesOutlined />} />
        <Button size="small" icon={<SearchOutlined />} />
        <Button size="small" icon={<ApartmentOutlined />} />
        <Button size="small" icon={<DatabaseOutlined />} />
        <Select size="small" value="100%" options={[{ value: '100%' }, { value: '125%' }, { value: '80%' }]} />
        <Select size="small" value="布局" options={[{ value: '布局' }, { value: '分层' }, { value: '网格' }]} />
      </div>
      <div className="agent-diagram-canvas">
        {activeDiagramView ? (
          <DiagramViewCanvas view={activeDiagramView} />
        ) : hasLayoutDrawing ? (
          <svg
            className="magicdraw-drawing-svg agent-layout-svg"
            width={layoutDrawing.width}
            height={layoutDrawing.height}
            viewBox={`0 0 ${layoutDrawing.width} ${layoutDrawing.height}`}
            role="img"
            aria-label="Unified MagicDraw diagram layout"
          >
            <defs>
              <marker id="agent-layout-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
            </defs>
            <g className="magicdraw-drawing-links">
              {layoutDrawing.edges.map((edge) => (
                <g
                  className={`magicdraw-drawing-link ${selectedRelationshipId === edge.id ? 'selected' : ''}`}
                  key={edge.id}
                  onClick={() => onSelectRelationship(edge.id)}
                >
                  <path d={edge.path} markerEnd="url(#agent-layout-arrow)" />
                  <text x={edge.labelX} y={edge.labelY}>
                    {edge.label}
                  </text>
                </g>
              ))}
            </g>
            <g className="magicdraw-drawing-nodes">
              {layoutDrawing.nodes.map((node) => (
                <g
                  className={`magicdraw-drawing-node ${node.cssType} ${selectedId === node.id ? 'selected' : ''}`}
                  key={node.id}
                  onClick={() => onSelect(node.id)}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    onSelect(node.id);
                    onOpenInternalDiagram(node.id);
                  }}
                >
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
        ) : elements.length ? (
          <svg width={diagram.width} height={diagram.height} viewBox={`0 0 ${diagram.width} ${diagram.height}`} role="img" aria-label="MagicDraw style diagram">
            <defs>
              <marker id="agent-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
            </defs>
            {diagram.edges.map((edge) => (
              <g
                className={`agent-edge ${edge.dashed ? 'dashed' : ''} ${selectedRelationshipId === edge.id ? 'selected' : ''}`}
                key={edge.id}
                onClick={() => onSelectRelationship(edge.id)}
              >
                <path d={edge.path} markerEnd="url(#agent-arrow)" />
                {edge.label && (
                  <text x={edge.labelX} y={edge.labelY}>
                    {edge.label}
                  </text>
                )}
              </g>
            ))}
            <rect className="agent-package-frame" x={diagram.packageFrame.x} y={diagram.packageFrame.y} width={diagram.packageFrame.width} height={diagram.packageFrame.height} />
            <text className="agent-package-title" x={diagram.packageFrame.x + 18} y={diagram.packageFrame.y + 22}>
              «package» 模型包
            </text>
            {diagram.nodes.map((node) => (
              <g
                className={`agent-node ${node.type.toLowerCase()} ${selectedId === node.id ? 'selected' : ''}`}
                key={node.id}
                onClick={() => onSelect(node.id)}
                onDoubleClick={(event) => {
                  event.stopPropagation();
                  onSelect(node.id);
                  onOpenInternalDiagram(node.id);
                }}
              >
                {node.shape === 'actor' ? (
                  <>
                    <rect x={node.x} y={node.y} width={node.width} height={node.height} rx="4" />
                    <circle cx={node.x + node.width / 2} cy={node.y + 18} r="7" />
                    <line x1={node.x + node.width / 2} y1={node.y + 25} x2={node.x + node.width / 2} y2={node.y + 48} />
                    <line x1={node.x + node.width / 2 - 14} y1={node.y + 35} x2={node.x + node.width / 2 + 14} y2={node.y + 35} />
                    <line x1={node.x + node.width / 2} y1={node.y + 48} x2={node.x + node.width / 2 - 13} y2={node.y + 65} />
                    <line x1={node.x + node.width / 2} y1={node.y + 48} x2={node.x + node.width / 2 + 13} y2={node.y + 65} />
                  </>
                ) : node.shape === 'ellipse' ? (
                  <ellipse cx={node.x + node.width / 2} cy={node.y + node.height / 2} rx={node.width / 2} ry={node.height / 2} />
                ) : (
                  <rect x={node.x} y={node.y} width={node.width} height={node.height} rx={node.shape === 'soft' ? 8 : 3} />
                )}
                <text className="agent-node-stereo" x={node.x + node.width / 2} y={node.y + 18}>
                  {node.stereo}
                </text>
                {node.lines.map((line, index) => (
                  <text className="agent-node-name" x={node.x + node.width / 2} y={node.y + 38 + index * 16} key={`${node.id}-${line}`}>
                    {line}
                  </text>
                ))}
              </g>
            ))}
          </svg>
        ) : (
          <div className="agent-empty-diagram">
            <ApartmentOutlined />
            <strong>等待生成模型</strong>
            <span>点击左侧“生成”后，这里会展示类似MagicDraw的需求图视图。</span>
          </div>
        )}
      </div>
    </section>
  );
}

function focusedDiagramModalTitle(focus: ModelElement | null) {
  return focus?.type === 'Interface' ? '接口关联视图下钻' : 'Block 内部模块图下钻';
}

function focusedDiagramCopy(focus: ModelElement | null) {
  if (focus?.type === 'Interface') {
    return {
      title: 'AI 接口关联视图',
      subtitle: '展示该接口关联的上下游模块、连接关系和数据/链路方向；可按当前上下文重新生成。',
      loadingTitle: 'AI 正在构建接口关联视图',
      loadingText: '系统会基于当前接口、关联模块和连接关系重建接口下钻视图。',
      errorTitle: '接口关联视图生成失败',
      emptyTitle: '等待生成接口关联视图',
      emptyText: '双击接口后会展示该接口的关联模块、连接关系和链路说明。',
      rationale: '该下钻图用于检查当前接口连接的参与模块、链路方向和关联关系。',
    };
  }
  return {
    title: 'AI 内部模块图',
    subtitle: '优先展示生成时预构建的 IBD；点击重新生成时再按当前上下文重建。',
    loadingTitle: 'AI 正在构建内部模块图',
    loadingText: '系统会基于当前 Block、总体模型上下文和用户原始意图重建 IBD。',
    errorTitle: '内部模块图生成失败',
    emptyTitle: '等待生成内部模块图',
    emptyText: '双击 Block 后会展示该模块的内部组成、接口和连接关系。',
    rationale: '该下钻图用于检查当前 Block 的内部组成、接口和连接关系。',
  };
}

function DiagramAlternativesPanel({
  view,
  focus,
  loading,
  error,
  onRegenerate,
}: {
  view: SysMLDiagramView | null;
  focus: ModelElement | null;
  loading: boolean;
  error: string;
  onRegenerate: () => void;
}) {
  const activeView = view;
  const copy = focusedDiagramCopy(focus);
  const blockCount = activeView?.elements.filter((item) => item.type === 'Block').length || 0;
  const interfaceCount = activeView?.elements.filter((item) => item.type === 'Interface').length || 0;
  const connectorCount = activeView?.relationships.filter((item) => item.type === 'connector').length || 0;
  const metricItems = [
    { label: 'Block', value: blockCount },
    { label: 'Interface', value: interfaceCount },
    { label: 'Connector', value: connectorCount },
    { label: '元素总数', value: activeView?.elements.length || 0 },
  ];

  return (
    <section className="agent-diagram-alternatives">
      <div className="agent-diagram-alt-header">
        <div>
          <strong>{focus ? `${focus.name} - ${copy.title}` : copy.title}</strong>
          <span>{copy.subtitle}</span>
        </div>
        <div className="agent-diagram-alt-controls">
          <Button size="small" icon={<ReloadOutlined />} loading={loading} disabled={!focus} onClick={onRegenerate}>
            重新生成
          </Button>
        </div>
      </div>
      <div className="agent-diagram-alt-body">
        {loading && !activeView ? (
          <div className="agent-diagram-alt-canvas">
            <div className="agent-diagram-empty-state">
              <ApartmentOutlined />
              <strong>{copy.loadingTitle}</strong>
              <span>{copy.loadingText}</span>
            </div>
          </div>
        ) : error && !activeView ? (
          <div className="agent-diagram-alt-canvas">
            <div className="agent-diagram-empty-state">
              <ApartmentOutlined />
              <strong>{copy.errorTitle}</strong>
              <span>{error}</span>
            </div>
          </div>
        ) : activeView ? (
          <DiagramViewCanvas view={activeView} />
        ) : (
          <div className="agent-diagram-alt-canvas">
            <div className="agent-diagram-empty-state">
              <ApartmentOutlined />
              <strong>{copy.emptyTitle}</strong>
              <span>{copy.emptyText}</span>
            </div>
          </div>
        )}
        <aside className="agent-diagram-alt-detail">
          <div>
            <strong>{activeView?.name || focus?.name || '当前模块'}</strong>
            <span>{activeView?.description || '优先使用生成时预构建的 IBD，需要时可重新生成。'}</span>
          </div>
          <div className="agent-diagram-alt-metrics">
            {metricItems.map((item) => (
              <Metric label={item.label} value={String(item.value)} compact key={item.label} />
            ))}
          </div>
          <Typography.Paragraph className="agent-diagram-alt-rationale" ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
            {activeView?.rationale || copy.rationale}
          </Typography.Paragraph>
          {activeView?.sysml_text && (
            <pre className="agent-diagram-alt-code">
              <code>{activeView.sysml_text}</code>
            </pre>
          )}
        </aside>
      </div>
    </section>
  );
}

function DiagramViewCanvas({ view }: { view: SysMLDiagramView }) {
  const drawing = useMemo(() => buildDiagramViewDrawing(view), [view]);
  const markerId = `diagram-view-arrow-${safeDomId(view.id)}`;
  if (!drawing.nodes.length) {
    return (
      <div className="agent-diagram-alt-canvas">
        <div className="agent-diagram-empty-state">
          <ApartmentOutlined />
          <strong>尚未定义内部模块</strong>
          <span>当前 Block 没有 contains 子模块或接口连接。请先补全该 Block 的内部结构，再查看真实 IBD。</span>
        </div>
      </div>
    );
  }
  return (
    <div className="agent-diagram-alt-canvas">
      <svg className="diagram-view-svg" width={drawing.width} height={drawing.height} viewBox={`0 0 ${drawing.width} ${drawing.height}`} role="img" aria-label={view.name}>
        <defs>
          <marker id={markerId} markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
        <g className="diagram-view-edges">
          {drawing.edges.map((edge) => (
            <g className="diagram-view-edge" key={edge.id}>
              <path d={edge.path} markerEnd={`url(#${markerId})`} />
              {edge.label && (
                <text x={edge.labelX} y={edge.labelY}>
                  {edge.label}
                </text>
              )}
            </g>
          ))}
        </g>
        <g className="diagram-view-nodes">
          {drawing.nodes.map((node) => (
            <g className={`diagram-view-node ${node.cssType}`} key={node.id}>
              {node.shape === 'actor' ? (
                <>
                  <rect className="actor-hitbox" x={node.x} y={node.y} width={node.width} height={node.height} rx="6" />
                  <circle cx={node.x + node.width / 2} cy={node.y + 20} r="8" />
                  <line x1={node.x + node.width / 2} y1={node.y + 28} x2={node.x + node.width / 2} y2={node.y + 52} />
                  <line x1={node.x + node.width / 2 - 16} y1={node.y + 38} x2={node.x + node.width / 2 + 16} y2={node.y + 38} />
                  <line x1={node.x + node.width / 2} y1={node.y + 52} x2={node.x + node.width / 2 - 14} y2={node.y + 70} />
                  <line x1={node.x + node.width / 2} y1={node.y + 52} x2={node.x + node.width / 2 + 14} y2={node.y + 70} />
                </>
              ) : node.shape === 'ellipse' ? (
                <ellipse cx={node.x + node.width / 2} cy={node.y + node.height / 2} rx={node.width / 2} ry={node.height / 2} />
              ) : (
                <rect x={node.x} y={node.y} width={node.width} height={node.height} rx={node.shape === 'soft' ? 8 : 3} />
              )}
              {node.shape !== 'actor' && (
                <text className="node-stereo" x={node.x + node.width / 2} y={node.y + 18}>
                  {node.stereotype}
                </text>
              )}
              {node.lines.map((line, index) => (
                <text className="node-name" x={node.x + node.width / 2} y={node.y + (node.shape === 'actor' ? 88 : 40) + index * 15} key={`${node.id}-${line}`}>
                  {line}
                </text>
              ))}
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

function SyncTable({ rows }: { rows: SyncRow[] }) {
  const columns: ColumnsType<SyncRow> = [
    { title: '类型', dataIndex: 'category', width: 90 },
    { title: '名称', dataIndex: 'name' },
    { title: '操作', dataIndex: 'action', width: 90 },
    { title: '状态', dataIndex: 'status', width: 90, render: (value) => <Tag color={value === '成功' ? 'green' : 'blue'}>{value}</Tag> },
    { title: '详情', dataIndex: 'detail' },
  ];
  return (
    <section className="agent-detail-table">
      <div className="agent-panel-title">
        <strong>同步详细结果</strong>
        <span>共 {rows.length} 条</span>
      </div>
      <Table size="small" rowKey="id" columns={columns} dataSource={rows} pagination={{ pageSize: 5 }} />
    </section>
  );
}

function SyncSummary({
  summary,
  lastSyncTime,
  bridgeOnline,
  bridgeProjectOpen,
  bridgeProjectPathConfigured,
  simulationSummary,
}: {
  summary: ReturnType<typeof buildSummary>;
  lastSyncTime: string;
  bridgeOnline: boolean;
  bridgeProjectOpen: boolean | null;
  bridgeProjectPathConfigured: boolean;
  simulationSummary: string;
}) {
  const bridgeWaitingForImport = bridgeOnline && bridgeProjectOpen === false && !bridgeProjectPathConfigured;
  const bridgeState = !bridgeOnline ? 'Bridge 未连接' : bridgeWaitingForImport ? 'Bridge 等待导入' : 'Bridge 可导入';
  return (
    <section className="agent-summary-panel">
      <div className="agent-panel-title">
        <strong>同步摘要</strong>
      </div>
      <div className="agent-summary-metrics">
        <Metric label="导入元素" value={String(summary.created)} compact />
        <Metric label="关系映射" value={String(summary.mapped)} compact />
        <Metric label="冲突" value={String(summary.conflicts)} compact warning={summary.conflicts > 0} />
      </div>
      <div className="agent-summary-box">
        <span>最后同步</span>
        <strong>{lastSyncTime}</strong>
      </div>
      <div className="agent-summary-box">
        <span>连接状态</span>
        <strong className={bridgeOnline ? 'ok' : 'warn'}>{bridgeState}</strong>
      </div>
      <div className="agent-summary-box">
        <span>仿真结果</span>
        <strong>{simulationSummary}</strong>
      </div>
    </section>
  );
}

function SysmlPreview({
  result,
  selectedId,
  onSelect,
}: {
  result: SysMLProjectGenerateResult | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const codeWindowRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!selectedId) return;
    const selectedLine = codeWindowRef.current?.querySelector(`[data-element-id="${selectedId}"]`);
    selectedLine?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selectedId, result?.sysml_text]);

  if (!result) {
    return (
      <section className="agent-sysml-preview empty">
        <div className="agent-panel-title">
          <strong>SysML textual view</strong>
          <span>等待生成</span>
        </div>
        <div className="agent-code-empty">
          <BranchesOutlined />
          <strong>尚未生成SysML脚本</strong>
          <span>点击“生成”后，这里会显示可高亮、可联动预览图的SysML textual view。</span>
        </div>
      </section>
    );
  }

  const lines = result.sysml_text.split('\n');
  const elementIds = new Set(result.elements.map((item) => item.id));
  return (
    <section className="agent-sysml-preview">
      <div className="agent-panel-title">
        <strong>SysML textual view</strong>
        <span>{result.project_name}</span>
      </div>
      <div className="agent-code-window" ref={codeWindowRef}>
        {lines.map((line, index) => {
          const lineElementId = findSysmlLineElementId(line, elementIds);
          const isSelected = !!lineElementId && lineElementId === selectedId;
          return (
            <div
              className={`agent-code-line ${lineElementId ? 'linked' : ''} ${isSelected ? 'selected' : ''}`}
              data-element-id={lineElementId || undefined}
              key={`${index}-${line}`}
              onClick={() => lineElementId && onSelect(lineElementId)}
              role={lineElementId ? 'button' : undefined}
              tabIndex={lineElementId ? 0 : undefined}
              title={lineElementId ? `选中预览图元素 ${lineElementId}` : undefined}
              onKeyDown={(event) => {
                if (lineElementId && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault();
                  onSelect(lineElementId);
                }
              }}
            >
              <span>{String(index + 1).padStart(2, '0')}</span>
              <code>{renderSysmlLine(line || ' ', selectedId)}</code>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function findSysmlLineElementId(line: string, elementIds: Set<string>) {
  const matches = line.match(/\b(?:REQ|BLK|UC|IF|CON|ACT)-\d{3}\b/g) || [];
  return matches.find((id) => elementIds.has(id)) || null;
}

function renderSysmlLine(line: string, selectedId: string | null): ReactNode[] {
  const tokenPattern = /(\/\/.*$|"(?:\\.|[^"])*"|«[^»]+»|\b(?:package|requirement|part|def|use|case|interface|action|constraint|dependency|from|to|attribute|doc)\b|\b(?:REQ|BLK|UC|IF|CON|ACT)-\d{3}\b|[{};=])/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(line))) {
    if (match.index > cursor) {
      nodes.push(line.slice(cursor, match.index));
    }
    const token = match[0];
    nodes.push(
      <span className={`sysml-token ${sysmlTokenClass(token)} ${selectedId === token ? 'active-id' : ''}`} key={`${match.index}-${token}`}>
        {token}
      </span>,
    );
    cursor = match.index + token.length;
  }

  if (cursor < line.length) {
    nodes.push(line.slice(cursor));
  }
  return nodes;
}

function sysmlTokenClass(token: string) {
  if (token.startsWith('//')) return 'comment';
  if (token.startsWith('"')) return 'string';
  if (/^(?:REQ|BLK|UC|IF|CON|ACT)-\d{3}$/.test(token)) return 'id';
  if (/^[{};=]$/.test(token)) return 'symbol';
  if (token.startsWith('«')) return 'stereo';
  return 'keyword';
}

function Metric({
  label,
  value,
  invert,
  compact,
  warning,
}: {
  label: string;
  value: string;
  invert?: boolean;
  compact?: boolean;
  warning?: boolean;
}) {
  return (
    <div className={`agent-metric ${compact ? 'compact' : ''} ${warning ? 'warning' : ''}`}>
      <CheckCircleOutlined />
      <span>{label}</span>
      <strong>{invert ? (value === '0' ? '0' : value) : value}</strong>
    </div>
  );
}

function groupElements(elements: ModelElement[]) {
  const groups = new Map<string, ModelElement[]>();
  for (const item of elements) {
    const key = item.package || defaultPackage(item.type);
    groups.set(key, [...(groups.get(key) || []), item]);
  }
  return Array.from(groups.entries()).map(([packageName, items]) => ({ packageName, elements: items }));
}

function buildSyncRows(elements: ModelElement[], relationships: ModelRelationship[], publishResult: MagicDrawPublishResult | null): SyncRow[] {
  if (!publishResult) return [];
  const mode = publishResult?.mode === 'bridge';
  const elementRows = elements.slice(0, 12).map((item, index) => ({
    id: item.id,
    category: typeName(item.type),
    name: `${item.id} ${item.name}`,
    action: mode && index % 3 === 1 ? '已更新' : '已创建',
    status: mode ? '成功' : '待推送',
    detail: `创建于 ${packageLabel(item.package || defaultPackage(item.type))}`,
  }));
  const relRows = relationships.slice(0, 8).map((item) => ({
    id: item.id,
    category: '关系',
    name: `${item.source} -> ${item.target}`,
    action: '已映射',
    status: mode ? '成功' : '待推送',
    detail: item.description || item.type,
  }));
  return [...elementRows, ...relRows];
}

function buildSummary(
  elements: ModelElement[],
  relationships: ModelRelationship[],
  publishResult: MagicDrawPublishResult | null,
  liveModel: MagicDrawBridgeOperationResult | null,
) {
  if (!publishResult) {
    return {
      created: 0,
      updated: 0,
      mapped: 0,
      conflicts: 0,
      liveElements: 0,
      liveRelationships: 0,
    };
  }
  const response = publishResult?.bridge_response || {};
  const created = numberValue(response.elements_created) || elements.length;
  const updated = numberValue(response.elements_reused) || Math.min(4, Math.floor(elements.length / 8));
  const mapped = numberValue(response.relationships_created) + numberValue(response.relationships_reused) || relationships.length;
  const liveResponse = liveModel?.bridge_response || {};
  const conflicts = Number(response.conflicts || 0);
  return {
    created,
    updated,
    mapped,
    conflicts,
    liveElements: numberValue(liveResponse.element_count),
    liveRelationships: numberValue(liveResponse.relationship_count),
  };
}

function buildPreviewValidation(projectResult: SysMLProjectGenerateResult | null, publishResult: MagicDrawPublishResult | null): PreviewValidation {
  const elements = projectResult?.elements || [];
  const relationships = projectResult?.relationships || [];
  if (!elements.length) {
    return {
      status: 'idle',
      issues: [],
      elementCount: 0,
      relationshipCount: 0,
      layoutNodeCount: 0,
      layoutEdgeCount: 0,
    };
  }

  const elementIds = new Set(elements.map((item) => item.id));
  const validRelationships = relationships.filter((item) => elementIds.has(item.source) && elementIds.has(item.target));
  const localDiagram = buildDiagram(elements, validRelationships);
  const layout = publishResult?.exchange_payload?.diagram_layout;
  const exchangeElements = publishResult?.exchange_payload?.elements || [];
  const exchangeRelationships = publishResult?.exchange_payload?.relationships || [];
  const layoutNodeCount = layout?.nodes?.length ?? localDiagram.nodes.length;
  const layoutEdgeCount = layout?.edges?.length ?? localDiagram.edges.length;
  const expectedNodeCount = publishResult ? exchangeElements.length || elements.length : elements.length;
  const expectedEdgeCount = publishResult ? exchangeRelationships.length || validRelationships.length : validRelationships.length;
  const issues: string[] = [];

  if (!relationships.length) {
    issues.push('模型尚未生成关系，无法形成可追溯视图');
  }
  if (validRelationships.length !== relationships.length) {
    issues.push(`模型存在 ${relationships.length - validRelationships.length} 条关系引用了不存在的元素，已从画布/推送关系中排除`);
  }
  const missingSysmlIds = elements.map((item) => item.id).filter((id) => !sysmlTextContainsId(projectResult?.sysml_text || '', id));
  if (missingSysmlIds.length) {
    issues.push(`SysML文本缺少模型元素ID：${missingSysmlIds.slice(0, 6).join('、')}${missingSysmlIds.length > 6 ? '等' : ''}`);
  }
  const missingRelationshipIds = validRelationships.map((item) => item.id).filter((id) => !sysmlTextContainsId(projectResult?.sysml_text || '', id));
  if (missingRelationshipIds.length) {
    issues.push(`SysML文本缺少关系ID：${missingRelationshipIds.slice(0, 6).join('、')}${missingRelationshipIds.length > 6 ? '等' : ''}`);
  }
  if (publishResult && !layout) {
    issues.push('MagicDraw返回结果缺少统一diagram_layout');
  }
  if (layoutNodeCount !== expectedNodeCount) {
    issues.push(`画布节点数 ${layoutNodeCount} 与可展示元素数 ${expectedNodeCount} 不一致`);
  }
  if (layoutEdgeCount !== expectedEdgeCount) {
    issues.push(`画布连线数 ${layoutEdgeCount} 与有效关系数 ${expectedEdgeCount} 不一致`);
  }

  return {
    status: issues.length ? 'warn' : 'pass',
    issues,
    elementCount: elements.length,
    relationshipCount: relationships.length,
    layoutNodeCount,
    layoutEdgeCount,
  };
}

function sysmlTextContainsId(sysmlText: string, id: string) {
  return sysmlText.includes(id) || sysmlText.includes(sysmlIdentifier(id));
}

function sysmlIdentifier(value: string) {
  const normalized = String(value || 'Element')
    .trim()
    .replace(/[^0-9A-Za-z_\u4e00-\u9fff]+/g, '_')
    .replace(/^_+|_+$/g, '');
  const safe = normalized || 'Element';
  return /^[0-9]/.test(safe) ? `E_${safe}` : safe;
}

function buildWorkflow(
  projectResult: SysMLProjectGenerateResult | null,
  publishResult: MagicDrawPublishResult | null,
  validation: PreviewValidation,
  status: WorkStatus,
) {
  if (status === 'generating') {
    return [
      { key: 'understand', label: '理解需求', index: 1, state: 'done' },
      { key: 'script', label: '生成脚本', index: 2, state: 'active' },
      { key: 'validate', label: '等待确认', index: 3, state: 'idle' },
      { key: 'push', label: '等待推送', index: 4, state: 'idle' },
    ] as Array<{ key: string; label: string; index: number; state: 'done' | 'active' | 'idle' }>;
  }

  const hasModel = !!projectResult;
  const hasPublish = !!publishResult;
  const previewPublished = isPreviewPublish(publishResult);
  const releasePublished = hasPublish && !previewPublished;
  const accepted = isDraftAccepted(projectResult);
  const previewReady = validation.status === 'pass';
  return [
    { key: 'understand', label: '理解需求', index: 1, state: hasModel ? 'done' : 'active' },
    { key: 'script', label: '生成脚本', index: 2, state: hasModel ? 'done' : 'idle' },
    {
      key: 'validate',
      label: accepted ? '已采纳' : previewReady ? '预览确认' : '预览校验',
      index: 3,
      state: accepted ? 'done' : hasModel ? 'active' : 'idle',
    },
    {
      key: 'push',
      label: releasePublished ? '已发布' : accepted ? '等待发布' : previewPublished ? '已预览' : hasModel ? '可预览' : '等待采纳',
      index: 4,
      state: releasePublished ? 'done' : hasModel ? 'active' : 'idle',
    },
  ] as Array<{ key: string; label: string; index: number; state: 'done' | 'active' | 'idle' }>;
}

function buildDiagram(elements: ModelElement[], relationships: ModelRelationship[]) {
  const nodes: DiagramNode[] = [];
  const columns = [
    { title: '需求', types: ['Requirement'], x: 90, width: 220 },
    { title: '结构', types: ['Block'], x: 390, width: 220 },
    { title: '行为', types: ['UseCase', 'Activity'], x: 690, width: 210 },
    { title: '接口/约束', types: ['Interface', 'ConstraintBlock'], x: 980, width: 210 },
  ];
  const columnByType = new Map<string, (typeof columns)[number]>();
  columns.forEach((column) => column.types.forEach((type) => columnByType.set(type, column)));
  const rowByColumn = new Map<number, number>();

  elements.forEach((item) => {
    const column = columnByType.get(item.type) || columns[1];
    const row = rowByColumn.get(column.x) || 0;
    rowByColumn.set(column.x, row + 1);
    nodes.push({
      id: item.id,
      type: item.type,
      name: item.name,
      stereo: diagramStereo(item.type),
      shape: diagramShape(item.type),
      x: column.x,
      y: 86 + row * 82,
      width: column.width,
      height: item.type === 'UseCase' ? 56 : 58,
      lines: splitLabel(`${item.id} ${item.name}`, item.type === 'Interface' ? 12 : 15, 2),
    });
  });

  const nodeMap = new Map(nodes.map((item) => [item.id, item]));
  const edges: DiagramEdge[] = [];
  relationships.forEach((rel) => {
    const source = nodeMap.get(rel.source);
    const target = nodeMap.get(rel.target);
    if (!source || !target) return;
    edges.push(
      lineEdge(
        rel.id,
        { x: source.x + source.width, y: source.y + source.height / 2 },
        { x: target.x, y: target.y + target.height / 2 },
        `«${rel.type}»`,
        rel.type !== 'contains',
      ),
    );
  });

  if (!nodes.length) {
    return {
      nodes,
      edges,
      width: 980,
      height: 520,
      packageFrame: {
        x: 54,
        y: 46,
        width: 872,
        height: 410,
      },
    };
  }

  const minNodeX = Math.min(...nodes.map((node) => node.x));
  const maxNodeRight = Math.max(...nodes.map((node) => node.x + node.width));
  const maxY = Math.max(460, ...nodes.map((node) => node.y + node.height + 88));
  const framePaddingX = 48;
  const framePaddingTop = 40;
  const framePaddingBottom = 52;
  const frameX = Math.max(32, minNodeX - framePaddingX);
  const frameRight = maxNodeRight + framePaddingX;
  const width = Math.max(1280, frameRight + 56);
  return {
    nodes,
    edges,
    width,
    height: maxY,
    packageFrame: {
      x: frameX,
      y: 46,
      width: frameRight - frameX,
      height: maxY - 46 - framePaddingBottom + framePaddingTop,
    },
  };
}

function diagramStereo(type: string) {
  return (
    {
      Requirement: '«requirement»',
      Block: '«block»',
      UseCase: '«use case»',
      Activity: '«activity»',
      Interface: '«interface»',
      ConstraintBlock: '«constraint»',
    }[type] || '«element»'
  );
}

function diagramShape(type: string): DiagramNode['shape'] {
  if (type === 'UseCase') return 'ellipse';
  if (type === 'Interface') return 'soft';
  return 'rect';
}

function lineEdge(id: string, start: Point, end: Point, label: string, dashed = false): DiagramEdge {
  const midX = (start.x + end.x) / 2;
  const path = `M ${start.x} ${start.y} C ${midX} ${start.y}, ${midX} ${end.y}, ${end.x} ${end.y}`;
  return { id, path, label, labelX: midX, labelY: (start.y + end.y) / 2 - 6, dashed };
}

interface Point {
  x: number;
  y: number;
}

interface DiagramNode {
  id: string;
  type: string;
  name: string;
  stereo: string;
  shape: 'rect' | 'soft' | 'ellipse' | 'actor';
  x: number;
  y: number;
  width: number;
  height: number;
  lines: string[];
}

interface DiagramEdge {
  id: string;
  path: string;
  label: string;
  labelX: number;
  labelY: number;
  dashed: boolean;
}

interface LayoutDrawingNode {
  id: string;
  cssType: string;
  stereotype: string;
  shape: 'rect' | 'soft' | 'ellipse';
  lines: string[];
  x: number;
  y: number;
  width: number;
  height: number;
}

interface LayoutDrawingEdge {
  id: string;
  label: string;
  path: string;
  labelX: number;
  labelY: number;
}

function buildFocusedBlockDiagramViews(elements: ModelElement[], relationships: ModelRelationship[], selectedId: string | null): SysMLDiagramView[] | null {
  if (!elements.length) return null;
  const elementById = new Map(elements.map((item) => [item.id, item]));
  const focus = resolveFocusedBlock(elements, relationships, selectedId);
  if (!focus) return null;

  const internalElements = focusedInternalElements(focus, elements, relationships, elementById);
  const structuralElements = internalElements;
  if (!structuralElements.length) {
    return buildEmptyFocusedBlockDiagramViews(focus);
  }

  const ibdRelationships = focusedInternalRelationships(focus, structuralElements, relationships);
  const variantName = `下钻：${focus.name}`;
  const ibdLayout = buildFocusedDiagramLayout(`${focus.name} - 内部模块图（IBD）`, structuralElements, ibdRelationships);

  return [
    {
      id: `FOCUS-${focus.id}-IBD`,
      variant_id: `FOCUS-${focus.id}`,
      variant_name: variantName,
      diagram_type: 'ibd',
      name: `${focus.name} - 内部模块图（IBD）`,
      description: `当前下钻对象：${focus.name}。该图展示这个 Block 内部包含的模块、接口以及它们之间的连接。`,
      rationale: '这是 Block 的内部结构视角，用于回答“这个模块内部由哪些部分组成、接口如何连接”。',
      elements: structuralElements,
      relationships: ibdRelationships,
      layout: ibdLayout,
      sysml_text: '',
      trace_links: [],
    },
  ];
}

function buildEmptyFocusedBlockDiagramViews(focus: ModelElement): SysMLDiagramView[] {
  const emptyIbdLayout = buildViewLayout(`${focus.name} - 内部模块图（IBD）`, [], [], 980, 420);
  const variantName = `下钻：${focus.name}`;
  return [
    {
      id: `FOCUS-${focus.id}-IBD`,
      variant_id: `FOCUS-${focus.id}`,
      variant_name: variantName,
      diagram_type: 'ibd',
      name: `${focus.name} - 内部模块图（IBD）`,
      description: `当前模型中，${focus.name} 还没有通过 contains/接口连接定义内部子模块，因此不能绘制真实 IBD。`,
      rationale: '为避免误导，系统不会用总体模型里的其它 Block 来填充这个 Block 的内部结构。',
      elements: [],
      relationships: [],
      layout: emptyIbdLayout,
      sysml_text: '',
      trace_links: [],
    },
  ];
}

function resolveFocusedBlock(elements: ModelElement[], relationships: ModelRelationship[], selectedId: string | null) {
  const elementById = new Map(elements.map((item) => [item.id, item]));
  const selected = selectedId ? elementById.get(selectedId) : null;
  if (selected?.type === 'Block' || selected?.type === 'Interface') return selected;
  if (selected) {
    const connectedBlock = relationships
      .flatMap((rel) => (rel.source === selected.id ? [elementById.get(rel.target)] : rel.target === selected.id ? [elementById.get(rel.source)] : []))
      .find((item): item is ModelElement => !!item && item.type === 'Block');
    if (connectedBlock) return connectedBlock;
  }
  const containedTargets = new Set(relationships.filter((rel) => rel.type === 'contains').map((rel) => rel.target));
  return elements.find((item) => item.type === 'Block' && !containedTargets.has(item.id)) || elements.find((item) => item.type === 'Block') || elements[0];
}

function focusedInternalElements(
  focus: ModelElement,
  elements: ModelElement[],
  relationships: ModelRelationship[],
  elementById: Map<string, ModelElement>,
) {
  const directChildren = relationships
    .filter((rel) => rel.type === 'contains' && rel.source === focus.id)
    .map((rel) => elementById.get(rel.target))
    .filter((item): item is ModelElement => !!item && ['Block', 'Interface', 'ConstraintBlock'].includes(item.type));
  const directChildIds = new Set(directChildren.map((item) => item.id));
  const relatedInterfaces = relationships
    .filter((rel) => ['allocate', 'dependency', 'trace'].includes(rel.type) && (rel.source === focus.id || rel.target === focus.id || directChildIds.has(rel.source) || directChildIds.has(rel.target)))
    .flatMap((rel) => [elementById.get(rel.source), elementById.get(rel.target)])
    .filter((item): item is ModelElement => !!item && item.type === 'Interface');
  const relatedForInterface =
    focus.type === 'Interface'
      ? relationships
          .filter((rel) => rel.source === focus.id || rel.target === focus.id)
          .flatMap((rel) => [elementById.get(rel.source), elementById.get(rel.target)])
          .filter((item): item is ModelElement => !!item && item.id !== focus.id && ['Block', 'Interface'].includes(item.type))
      : [];
  return uniqueElements([...(focus.type === 'Interface' ? [focus] : []), ...directChildren, ...relatedInterfaces, ...relatedForInterface]).slice(0, 10);
}

function focusedInternalRelationships(focus: ModelElement, structuralElements: ModelElement[], relationships: ModelRelationship[]) {
  const ids = new Set(structuralElements.map((item) => item.id));
  return relationships
    .filter((rel) => ids.has(rel.source) && ids.has(rel.target))
    .map((rel, index) => ({
      id: `DREL-FOCUS-IBD-${index + 1}`,
      source: rel.source,
      target: rel.target,
      type: rel.type === 'contains' ? 'connector' : rel.type,
      description: rel.description || `${focus.name} 内部连接`,
    }));
}

function uniqueElements(items: ModelElement[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function buildFocusedDiagramLayout(
  diagramName: string,
  elements: ModelElement[],
  relationships: ModelRelationship[],
) {
  const nodes = elements.map((item, index) => ({
    id: item.id,
    element_id: item.id,
    name: item.name,
    label: item.name,
    type: item.type,
    stereotype_label: item.type === 'Interface' ? 'interface' : 'part',
    shape: item.type === 'Interface' ? 'soft' : 'rect',
    x: 80 + (index % 4) * 250,
    y: 110 + Math.floor(index / 4) * 150,
    width: 205,
    height: 76,
  }));
  const width = 1140;
  const height = Math.max(520, 240 + Math.ceil(elements.length / 4) * 150);
  return buildViewLayout(diagramName, nodes, relationships, width, height);
}

function buildViewLayout(diagramName: string, nodes: DiagramViewLayoutNode[], relationships: ModelRelationship[], width: number, height: number) {
  const nodeById = new Map(nodes.map((node) => [String(node.id), node]));
  const edges = relationships
    .map((rel) => {
      const source = nodeById.get(rel.source);
      const target = nodeById.get(rel.target);
      if (!source || !target) return null;
      const points = viewEdgePoints(source, target);
      return {
        id: rel.id,
        relationship_id: rel.id,
        source: rel.source,
        target: rel.target,
        type: rel.type,
        label: rel.type,
        points,
        label_x: (points[0].x + points[points.length - 1].x) / 2,
        label_y: (points[0].y + points[points.length - 1].y) / 2 - 8,
      };
    })
    .filter((item): item is NonNullable<typeof item> => !!item);
  return {
    schema: 'ai-mbse.diagram-view-layout.v1',
    diagram_name: diagramName,
    layout_source: 'frontend-focused-block',
    width,
    height,
    nodes,
    edges,
  };
}

function viewEdgePoints(source: DiagramViewLayoutNode, target: DiagramViewLayoutNode) {
  const sourceX = Number(source.x || 0);
  const sourceY = Number(source.y || 0);
  const sourceW = Number(source.width || 180);
  const sourceH = Number(source.height || 72);
  const targetX = Number(target.x || 0);
  const targetY = Number(target.y || 0);
  const targetW = Number(target.width || 180);
  const targetH = Number(target.height || 72);
  const start = sourceX <= targetX ? { x: sourceX + sourceW, y: sourceY + sourceH / 2 } : { x: sourceX, y: sourceY + sourceH / 2 };
  const end = sourceX <= targetX ? { x: targetX, y: targetY + targetH / 2 } : { x: targetX + targetW, y: targetY + targetH / 2 };
  const midX = (start.x + end.x) / 2;
  return [start, { x: midX, y: start.y }, { x: midX, y: end.y }, end];
}

interface DiagramViewDrawingNode {
  id: string;
  cssType: string;
  stereotype: string;
  shape: 'rect' | 'soft' | 'ellipse' | 'actor';
  lines: string[];
  x: number;
  y: number;
  width: number;
  height: number;
}

interface DiagramViewDrawingEdge {
  id: string;
  label: string;
  path: string;
  labelX: number;
  labelY: number;
}

function buildDiagramViewDrawing(view: SysMLDiagramView) {
  const layout = view.layout || {};
  const nodes = (layout.nodes || []).map<DiagramViewDrawingNode>((node) => ({
    id: String(node.id || node.element_id || node.label || ''),
    cssType: diagramViewCssType(String(node.type || 'Block')),
    stereotype: node.stereotype_label || layoutStereotype(String(node.type || 'Block')),
    shape: diagramViewShape(String(node.shape || node.type || 'rect')),
    lines: splitLayoutLabel(node.label || node.name || node.id || 'UnnamedElement', 14, 2),
    x: Number(node.x || 0),
    y: Number(node.y || 0),
    width: Number(node.width || 190),
    height: Number(node.height || 72),
  }));
  const edges = (layout.edges || []).map<DiagramViewDrawingEdge>((edge) => ({
    id: String(edge.id || edge.relationship_id || `${edge.source}-${edge.target}`),
    label: truncateLayoutText(String(edge.label || edge.type || 'connector'), 18),
    path: diagramViewPathFromPoints(edge.points || []),
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

function buildLayoutDrawing(layout: MagicDrawDiagramLayout) {
  const nodes = (layout.nodes || []).map<LayoutDrawingNode>((node) => ({
    id: String(node.id || node.element_id || node.label || ''),
    cssType: String(node.type || 'Block').toLowerCase(),
    stereotype: node.stereotype_label || layoutStereotype(String(node.type || 'Block')),
    shape: layoutShape(String(node.shape || node.type || 'rect')),
    lines: splitLayoutLabel(node.label || node.name || node.id || 'UnnamedElement', 18, 2),
    x: Number(node.x || 0),
    y: Number(node.y || 0),
    width: Number(node.width || 220),
    height: Number(node.height || 72),
  }));
  const edges = (layout.edges || []).map<LayoutDrawingEdge>((edge) => ({
    id: String(edge.id || edge.relationship_id || `${edge.source}-${edge.target}`),
    label: truncateLayoutText(String(edge.label || edge.type || 'trace'), 18),
    path: layoutPathFromPoints(edge.points || []),
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

function diagramViewPathFromPoints(points?: Array<{ x: number; y: number }>) {
  if (!points?.length) return '';
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
}

function layoutPathFromPoints(points: MagicDrawLayoutEdge['points']) {
  if (!points?.length) return '';
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
}

function layoutStereotype(type: string) {
  if (type === 'Activity') return '«activity»';
  if (type === 'Block') return '«block»';
  if (type === 'Requirement') return '«requirement»';
  if (type === 'UseCase') return '«use case»';
  if (type === 'Interface') return '«interface»';
  if (type === 'ConstraintBlock') return '«constraint»';
  return '«element»';
}

function layoutShape(value: string): LayoutDrawingNode['shape'] {
  if (value === 'ellipse' || value === 'UseCase') return 'ellipse';
  if (value === 'soft' || value === 'Interface') return 'soft';
  return 'rect';
}

function diagramViewShape(value: string): DiagramViewDrawingNode['shape'] {
  if (value === 'actor' || value === 'Actor') return 'actor';
  if (value === 'ellipse' || value === 'UseCase') return 'ellipse';
  if (value === 'soft' || value === 'Interface') return 'soft';
  return 'rect';
}

function diagramViewCssType(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, '') || 'element';
}

function safeDomId(value: string) {
  return String(value || 'diagram').replace(/[^a-zA-Z0-9_-]+/g, '-');
}

function splitLayoutLabel(value: string, size: number, maxLines: number) {
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

function truncateLayoutText(value: string, size: number) {
  const text = String(value || '').trim();
  return text.length > size ? `${text.slice(0, size - 1)}…` : text;
}

function defaultPackage(type: string) {
  if (type === 'Requirement') return '01_Requirements';
  if (type === 'Block') return '02_Structure';
  if (type === 'UseCase' || type === 'Activity') return '03_Behavior';
  if (type === 'Interface') return '04_Interfaces';
  if (type === 'ConstraintBlock') return '05_Constraints';
  return '06_Traceability';
}

function packageLabel(value: string) {
  return value
    .replace('01_Requirements', '需求模型（Requirements Model）')
    .replace('02_Structure', '结构模型（Structure Model）')
    .replace('03_Behavior', '行为模型（Behavior Model）')
    .replace('04_Interfaces', '接口包')
    .replace('05_Constraints', '约束包')
    .replace('06_Traceability', '分析模型（Analysis Model）');
}

function typeName(value: string) {
  return {
    Requirement: '需求',
    Block: '模块',
    UseCase: '用例',
    Interface: '接口',
    Activity: '活动',
    ConstraintBlock: '约束',
  }[value] || value;
}

function splitLabel(value: string, size: number, maxLines: number) {
  const text = String(value || '').trim();
  const lines: string[] = [];
  for (let index = 0; index < text.length && lines.length < maxLines; index += size) {
    lines.push(text.slice(index, index + size));
  }
  if (text.length > size * maxLines && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, Math.max(1, size - 1))}…`;
  }
  return lines.length ? lines : ['未命名'];
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function summaryText(result: MagicDrawPublishResult, key: 'elements' | 'relationships') {
  const response = result.bridge_response || {};
  const created = numberValue(response[`${key}_created`]);
  const reused = numberValue(response[`${key}_reused`]);
  return String(created + reused || (key === 'elements' ? result.exchange_payload?.elements?.length : result.exchange_payload?.relationships?.length) || 0);
}

function uniqueDiagramViews(views: SysMLDiagramView[]) {
  const seen = new Set<string>();
  return views.filter((view) => {
    const key = view.id || `${view.variant_id}-${view.diagram_type}-${view.name}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function diagramViewHasCanvas(view: SysMLDiagramView) {
  return !!(view.layout?.nodes?.length || view.elements?.length);
}

function diagramTypeLabel(value: SysMLDiagramView['diagram_type']) {
  return {
    use_case: '用例图',
    ibd: '内部模块图',
    activity: '活动图',
    sequence: '顺序图',
    state: '运行状态图',
  }[value];
}

function diagramTypeShortLabel(value: SysMLDiagramView['diagram_type']) {
  return {
    use_case: '用例',
    ibd: '结构',
    activity: '活动',
    sequence: '交互',
    state: '状态',
  }[value];
}

function diagramViewsToInternalCache(views?: SysMLDiagramView[]) {
  const cache: Record<string, SysMLDiagramView> = {};
  for (const view of views || []) {
    const focusId = internalFocusIdForView(view);
    if (focusId) {
      cache[focusId] = { ...view, focus_element_id: focusId };
    }
  }
  return cache;
}

function findInternalDiagramViewForFocus(views: SysMLDiagramView[] | undefined, focusId: string) {
  return (views || []).find((view) => internalFocusIdForView(view) === focusId) || null;
}

function internalFocusIdForView(view: SysMLDiagramView) {
  if (view.diagram_type !== 'ibd' || !view.elements?.length) return '';
  const explicit = typeof view.focus_element_id === 'string' ? view.focus_element_id.trim() : '';
  if (explicit) return explicit;
  const match = /^FOCUS-(.+)-IBD$/i.exec(String(view.id || ''));
  return match?.[1] || '';
}

function countInternalDiagramViews(views?: SysMLDiagramView[]) {
  return Object.keys(diagramViewsToInternalCache(views)).length;
}

function countBehaviorDiagramViews(views?: SysMLDiagramView[]) {
  return (views || []).filter((view) => ['activity', 'sequence', 'state'].includes(view.diagram_type)).length;
}

function createInitialWorkspaces(projects: ProjectItem[]) {
  return Object.fromEntries(projects.map((project) => [project.id, createWorkspace(project)]));
}

function createWorkspace(project: ProjectItem): ProjectWorkspace {
  return {
    prompt: '',
    chat: createInitialChat(),
    projectResult: null,
    publishResult: null,
    liveModel: null,
    selectedId: null,
    selectedRelationshipId: null,
    activeTab: 'sysml',
    lastSyncTime: '--',
    simulationSummary: '待运行',
    generationDuration: '--',
    generatedAt: '--',
    preReviewReport: null,
    impactReport: null,
  };
}

function createInitialChat(): ChatBubble[] {
  return [
    {
      id: `${Date.now()}-hello-${Math.random()}`,
      role: 'assistant',
      content: '我是 MBSE 助理。我们先理解和澄清需求、边界、接口与变更影响；确认充分后，再点击“生成”进入SysML工程建模。',
      time: nowTime(),
    },
  ];
}

function resolveNext<T>(next: T | ((current: T) => T), current: T) {
  return typeof next === 'function' ? (next as (current: T) => T)(current) : next;
}

function buildAiMessage(text: string, mode: ResponseMode, attachments: AttachedFile[], projectName: string) {
  const intent = classifyConversationIntent(text);
  const sections = [
    `当前对话名称：${projectName}（仅用于侧栏归档和用户识别，不是建模需求，不得据此推断系统类型或生成模型）`,
    `当前阶段：${conversationStage(intent)}`,
    `回答模式：${modeLabel(mode)}`,
    `工作流约束：${chatWorkflowInstruction(intent)}`,
    `模式要求：${modeInstruction(mode, intent)}`,
    `用户输入：${text}`,
  ];

  if (attachments.length) {
    sections.push(
      [
        '附件上下文：',
        ...attachments.map((file, index) =>
          [
            `${index + 1}. ${file.name}（${file.type || 'unknown'}，${formatBytes(file.size)}，${file.status || 'ready'}）`,
            file.content ? `内容摘录：\n${file.content}` : '内容摘录：无可解析文本，仅提供文件元数据。',
          ].join('\n'),
        ),
      ].join('\n\n'),
    );
  }

  return sections.join('\n\n');
}

function resolveGenerationSource(prompt: string, chat: ChatBubble[]) {
  const current = prompt.trim();
  const history = buildGenerationHistory(chat);
  const parts: string[] = [];

  if (history) {
    parts.push(`历史对话工程上下文：\n${history}`);
  }
  if (current && classifyConversationIntent(current) !== 'greeting') {
    parts.push(`${isGenerateConfirmation(current) ? '用户生成指令' : '当前补充输入'}：\n${current}`);
  }

  return parts.join('\n\n').trim();
}

function buildGenerationHistory(chat: ChatBubble[]) {
  const snippets = chat
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item) => {
      const content = item.content.trim();
      if (!content || item.streaming) return '';
      if (item.role === 'user') {
        if (classifyConversationIntent(content) === 'greeting' || isGenerateConfirmation(content)) return '';
        return isModelingSeed(content) || hasEngineeringTerms(content) ? `用户：${content}` : '';
      }
      if (content.startsWith('已生成 ') || content.startsWith('已成功同步到 MagicDraw')) return '';
      return isSubstantialEngineeringContext(content) ? `AI整理：${content}` : '';
    })
    .filter(Boolean)
    .slice(-8);

  return snippets.join('\n\n');
}

function isModelingSeed(text: string) {
  const normalized = text.trim();
  if (!normalized || classifyConversationIntent(normalized) === 'greeting') {
    return false;
  }

  const hasEngineeringObject =
    /(系统|需求|边界|接口|功能|链路|流程|约束|指标|架构|总体|方案|模型|工程|SysML|MagicDraw|MBSE|卫星|星座|飞机|无人机|雷达|地面站|火箭|飞控|载荷|网络)/i.test(
      normalized,
    );
  const hasEngineeringAction = /(生成|设计|建模|建立|构建|输出|形成|创建|梳理|提取|分析|分解|定义|设计一个|总体设计)/i.test(normalized);
  const hasStructuredRequirement = /(需求|边界|接口|功能|链路|流程|约束|指标|场景|利益相关|参与方|任务|用例|验收)/i.test(normalized);

  return normalized.length >= 6 && hasEngineeringObject && (hasEngineeringAction || hasStructuredRequirement);
}

function hasEngineeringTerms(text: string) {
  return /(系统|需求|边界|接口|功能|链路|流程|约束|指标|架构|总体|方案|模型|工程|SysML|MagicDraw|MBSE|卫星|星座|飞机|无人机|雷达|地面站|火箭|飞控|载荷|网络|用例|活动|结构|模块)/i.test(
    text,
  );
}

function isGenerateConfirmation(text: string) {
  const normalized = text.trim().toLowerCase().replace(/[，。！？!?\s]/g, '');
  if (!normalized || /(不要|先别|不用|禁止|别).{0,6}(生成|建模|出模型|出工程)/.test(normalized)) {
    return false;
  }
  return /(生成|建模|开始|确认|确定|可以了|执行|做吧|生成吧|帮我生成|开始生成|可以生成|确认生成|按上面生成|按上面的来|按这个生成|就按这个|照此生成|生成图|生成图表|生成模型|生成工程|生成sysml|形成sysml|建模吧|出模型|出工程|出图)/i.test(
    normalized,
  );
}

function isSubstantialEngineeringContext(text: string) {
  const normalized = text.trim();
  if (normalized.length < 80) {
    return false;
  }

  const markers = [
    '需求',
    '需求图',
    '边界',
    '接口',
    '功能',
    '链路',
    '流程',
    '约束',
    '指标',
    '用例',
    '活动',
    '活动图',
    '状态机',
    '结构',
    '模块',
    '内部块',
    '参数图',
    '包图',
    '交互',
    '数据',
    '性能',
    'SysML',
    'MagicDraw',
    '工程',
  ];
  const markerCount = markers.reduce((count, marker) => (normalized.includes(marker) ? count + 1 : count), 0);
  return markerCount >= 3 && /(需求|总体|系统|SysML|MagicDraw|工程|模型|图|方案)/i.test(normalized);
}

type ConversationIntent = 'greeting' | 'requirement_understanding' | 'impact_analysis' | 'modeling_question' | 'general';

function classifyConversationIntent(text: string): ConversationIntent {
  const normalized = text.trim().toLowerCase().replace(/[，。！？!?\s]/g, '');
  if (['在吗', '你在吗', '你好', '您好', 'hi', 'hello', 'hey', '哈喽', '收到', '好的', 'ok'].includes(normalized)) {
    return 'greeting';
  }
  if (/(变更|修改|调整|变化|影响|波及|追溯|依赖|风险|冲突)/i.test(text)) {
    return 'impact_analysis';
  }
  if (/(怎么建模|如何建模|建模流程|模型怎么|sysml怎么|magicdraw怎么|mbse怎么)/i.test(text)) {
    return 'modeling_question';
  }
  if (/(需求|边界|接口|功能|链路|流程|约束|指标|场景|利益相关|参与方|任务|用例|验收)/i.test(text)) {
    return 'requirement_understanding';
  }
  return 'general';
}

function conversationStage(intent: ConversationIntent) {
  if (intent === 'greeting') return '普通寒暄';
  if (intent === 'impact_analysis') return '变更影响分析';
  if (intent === 'modeling_question') return '建模方法答疑';
  if (intent === 'requirement_understanding') return '需求理解与澄清';
  return '普通问答';
}

function chatWorkflowInstruction(intent: ConversationIntent) {
  const base =
    '当前只是AI对话阶段，不自动生成SysML工程、不自动推送MagicDraw、不声称已经建模；只有用户点击“生成”或明确要求生成工程时才进入建模。';
  if (intent === 'greeting') {
    return `${base} 用户只是寒暄时，简短回应在线，并邀请用户描述系统、需求或变更问题。`;
  }
  if (intent === 'impact_analysis') {
    return `${base} 对变更问题，应围绕需求、功能、结构、接口、行为、约束、验证和MagicDraw交付物的影响路径进行分析，并列出待确认项。`;
  }
  if (intent === 'requirement_understanding') {
    return `${base} 优先帮助用户澄清需求、系统边界、功能链路、接口、行为流程、约束条件和验收标准；信息不足时提问，不直接产出工程。`;
  }
  return `${base} 根据用户问题回答，并在合适时提示可继续做需求澄清、变更影响分析或点击“生成”形成SysML工程。`;
}

function modeLabel(mode: ResponseMode) {
  if (mode === 'fast') return '快速回答';
  if (mode === 'review') return '评审模式';
  return '深度思考';
}

function knowledgeModeLabel(mode: KnowledgeMode) {
  if (mode === 'direct_chat') return '直接问答';
  if (mode === 'knowledge_qa') return '知识库问答';
  return '自动识别';
}

function modeInstruction(mode: ResponseMode, intent: ConversationIntent = 'general') {
  if (mode === 'fast') {
    return '优先给出结论、关键判断和下一步动作，避免长篇展开。';
  }
  if (mode === 'review') {
    return '以系统工程评审视角回答，重点指出需求缺口、边界遗漏、接口冲突、约束风险和待确认项。';
  }
  if (intent === 'greeting') {
    return '自然、简短地回应，不展开建模内容。';
  }
  if (intent === 'impact_analysis') {
    return '结构化分析变更影响范围、传播路径、受影响模型元素、风险等级和建议处置动作。';
  }
  return '先做需求理解和澄清，必要时给出下一轮问题清单；不要把普通聊天直接扩展成工程生成结果。';
}

function appendToolAndKnowledgeSummary(answer: string, toolCalls: ToolCall[] = [], artifacts: Record<string, unknown> = {}) {
  const lines: string[] = [];
  const callLabels = toolCalls.map((item) => item.summary).filter(Boolean);
  if (callLabels.length) {
    lines.push(`调用能力：${callLabels.join('；')}`);
  }

  const knowledge = Array.isArray(artifacts.knowledge) ? (artifacts.knowledge as Array<Record<string, unknown>>) : [];
  if (knowledge.length) {
    lines.push('知识依据：');
    knowledge.slice(0, 4).forEach((item, index) => {
      const source = String(item.source || item.source_type || '知识库');
      const title = String(item.title || '未命名知识');
      const summary = String(item.summary || '').replace(/\s+/g, ' ').trim();
      lines.push(`${index + 1}. ${source} / ${title}${summary ? `：${summary.slice(0, 90)}` : ''}`);
    });
  }

  if (!lines.length) return answer;
  return `${answer.trim()}\n\n---\n${lines.join('\n')}`;
}

function toChatAttachment(file: AttachedFile): ChatAttachment {
  return {
    name: file.name,
    size: file.size,
    type: file.type,
    status: file.status,
  };
}

async function extractTemporaryAttachment(file: File): Promise<{ content: string; status: 'parsed' | 'ready' | 'metadata' }> {
  try {
    const extracted = await client.extractDocument(file);
    const content = String(extracted.content || '').trim();
    if (content) {
      return { content, status: 'parsed' };
    }
  } catch {
    // Fall back to browser-side text reading when the backend parser is unavailable.
  }

  try {
    const content = await readLocalTextSnippet(file);
    if (content) {
      return { content, status: 'ready' };
    }
  } catch {
    // Metadata fallback below keeps the attachment visible in the conversation.
  }

  return { content: '', status: 'metadata' };
}

async function readLocalTextSnippet(file: File) {
  if (!isTextLikeFile(file)) return '';
  return truncateAttachmentContent(await file.text());
}

function isTextLikeFile(file: File) {
  const lower = file.name.toLowerCase();
  return (
    file.type.startsWith('text/') ||
    [
      '.txt',
      '.md',
      '.csv',
      '.json',
      '.xml',
      '.yaml',
      '.yml',
      '.sysml',
      '.puml',
      '.plantuml',
      '.log',
      '.ini',
      '.cfg',
      '.py',
      '.ts',
      '.tsx',
      '.js',
      '.jsx',
      '.java',
      '.m',
    ].some((suffix) => lower.endsWith(suffix))
  );
}

function fileExtension(filename: string) {
  const match = /\.[^.]+$/.exec(filename);
  return match?.[0]?.slice(1) || '';
}

function attachmentMetadata(file: File) {
  return `文件名：${file.name}\n类型：${file.type || fileExtension(file.name) || 'unknown'}\n大小：${formatBytes(file.size)}\n该文件暂无可解析文本内容。`;
}

function truncateAttachmentContent(content: string, maxLength = 12000) {
  const text = String(content || '').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n\n[附件内容已截断，仅发送前 ${maxLength} 字符]`;
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDuration(milliseconds: number) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '--';
  const totalSeconds = Math.max(1, Math.round(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `00:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
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

const paneSizesStorageKey = 'ai-mbse-agent-pane-sizes';
const workbenchStorageVersion = 1;
const workbenchStoragePrefix = 'ai-mbse-agent-workbench';

function loadWorkbenchState(role: 'admin' | 'designer', workspace?: string): AgentPersistedState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(workbenchStorageKey(role, workspace));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AgentPersistedState>;
    if (parsed.version !== workbenchStorageVersion) return null;
    const projects = normalizePersistedProjects(parsed.projects);
    return {
      version: workbenchStorageVersion,
      projects,
      activeProjectId: resolvePersistedActiveProjectId(parsed.activeProjectId, projects),
      workspaces: hydratePersistedWorkspaces(projects, parsed.workspaces),
      mode: isResponseMode(parsed.mode) ? parsed.mode : 'deep',
      knowledgeMode: isKnowledgeMode(parsed.knowledgeMode) ? parsed.knowledgeMode : 'auto',
      selectedMergeRequestId: Number.isFinite(parsed.selectedMergeRequestId) ? Number(parsed.selectedMergeRequestId) : null,
    };
  } catch {
    return null;
  }
}

function saveWorkbenchState(role: 'admin' | 'designer', workspace: string | undefined, state: AgentPersistedState) {
  if (typeof window === 'undefined') return;
  try {
    const projects = normalizePersistedProjects(state.projects);
    const snapshot: AgentPersistedState = {
      version: workbenchStorageVersion,
      projects,
      activeProjectId: resolvePersistedActiveProjectId(state.activeProjectId, projects),
      workspaces: sanitizeWorkspacesForStorage(state.workspaces),
      mode: isResponseMode(state.mode) ? state.mode : 'deep',
      knowledgeMode: isKnowledgeMode(state.knowledgeMode) ? state.knowledgeMode : 'auto',
      selectedMergeRequestId: Number.isFinite(state.selectedMergeRequestId) ? Number(state.selectedMergeRequestId) : null,
    };
    window.localStorage.setItem(workbenchStorageKey(role, workspace), JSON.stringify(snapshot));
  } catch {
    // Workspace persistence is a convenience layer; the database-backed draft remains authoritative.
  }
}

function workbenchStorageKey(role: 'admin' | 'designer', workspace?: string) {
  return `${workbenchStoragePrefix}:${role}:${workspace || 'global'}`;
}

function normalizePersistedProjects(projects?: ProjectItem[]) {
  const validProjects = Array.isArray(projects) ? projects.filter(isProjectItem) : [];
  return validProjects.length ? validProjects : initialProjects;
}

function resolvePersistedActiveProjectId(activeProjectId: unknown, projects: ProjectItem[]) {
  const preferred = typeof activeProjectId === 'string' ? activeProjectId : '';
  return projects.some((project) => project.id === preferred) ? preferred : projects[0]?.id || initialProjects[0].id;
}

function hydratePersistedWorkspaces(projects: ProjectItem[], persistedWorkspaces: unknown) {
  if (!isRecord(persistedWorkspaces)) return createInitialWorkspaces(projects);
  return Object.fromEntries(
    projects.map((project) => [project.id, hydratePersistedWorkspace(project, persistedWorkspaces[project.id])]),
  );
}

function hydratePersistedWorkspace(project: ProjectItem, value: unknown): ProjectWorkspace {
  const fallback = createWorkspace(project);
  if (!isRecord(value)) return fallback;
  const chat = Array.isArray(value.chat) ? value.chat.map(normalizeChatBubble).filter(isChatBubble) : fallback.chat;
  return {
    ...fallback,
    prompt: typeof value.prompt === 'string' ? value.prompt : fallback.prompt,
    chat: chat.length ? chat.slice(-40) : fallback.chat,
    projectResult: isSysmlProjectResult(value.projectResult) ? value.projectResult : null,
    publishResult: isRecord(value.publishResult) ? (value.publishResult as unknown as MagicDrawPublishResult) : null,
    liveModel: isRecord(value.liveModel) ? (value.liveModel as unknown as MagicDrawBridgeOperationResult) : null,
    selectedId: optionalString(value.selectedId),
    selectedRelationshipId: optionalString(value.selectedRelationshipId),
    activeTab: isWorkbenchTab(value.activeTab) ? value.activeTab : fallback.activeTab,
    lastSyncTime: typeof value.lastSyncTime === 'string' ? value.lastSyncTime : fallback.lastSyncTime,
    simulationSummary: typeof value.simulationSummary === 'string' ? value.simulationSummary : fallback.simulationSummary,
    generationDuration: typeof value.generationDuration === 'string' ? value.generationDuration : fallback.generationDuration,
    generatedAt: typeof value.generatedAt === 'string' ? value.generatedAt : fallback.generatedAt,
    preReviewReport: isRecord(value.preReviewReport) ? (value.preReviewReport as unknown as DraftValidationReport) : null,
    impactReport: isRecord(value.impactReport) ? (value.impactReport as unknown as ChangeImpactSandboxResponse) : null,
  };
}

function sanitizeWorkspacesForStorage(workspaces: Record<string, ProjectWorkspace>) {
  return Object.fromEntries(
    Object.entries(workspaces).map(([key, workspace]) => [
      key,
      {
        ...workspace,
        chat: workspace.chat.slice(-40).map(sanitizeChatBubbleForStorage),
      },
    ]),
  );
}

function sanitizeChatBubbleForStorage(chat: ChatBubble): ChatBubble {
  return {
    ...chat,
    streaming: false,
    state: chat.streaming ? undefined : chat.state,
  };
}

function normalizeChatBubble(value: unknown): ChatBubble | null {
  if (!isRecord(value) || !isChatRole(value.role)) return null;
  return {
    id: typeof value.id === 'string' ? value.id : `${Date.now()}-${Math.random()}`,
    role: value.role,
    content: typeof value.content === 'string' ? value.content : '',
    time: typeof value.time === 'string' ? value.time : nowTime(),
    state: value.state === 'ok' || value.state === 'working' ? value.state : undefined,
    streaming: false,
    attachments: normalizeChatAttachments(value.attachments),
  };
}

function normalizeChatAttachments(value: unknown): ChatAttachment[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const attachments = value
    .map((item) => {
      if (!isRecord(item) || typeof item.name !== 'string') return null;
      return {
        name: item.name,
        size: Number.isFinite(item.size) ? Number(item.size) : 0,
        type: typeof item.type === 'string' ? item.type : 'unknown',
        status: typeof item.status === 'string' ? item.status : undefined,
      };
    })
    .filter(Boolean) as ChatAttachment[];
  return attachments.length ? attachments : undefined;
}

function isProjectItem(value: unknown): value is ProjectItem {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.workspace === 'string' &&
    typeof value.prompt === 'string'
  );
}

function isSysmlProjectResult(value: unknown): value is SysMLProjectGenerateResult {
  return (
    isRecord(value) &&
    typeof value.project_name === 'string' &&
    typeof value.summary === 'string' &&
    Array.isArray(value.elements) &&
    Array.isArray(value.relationships) &&
    typeof value.sysml_text === 'string'
  );
}

function isChatRole(value: unknown): value is ChatRole {
  return value === 'assistant' || value === 'user' || value === 'system';
}

function isChatBubble(value: ChatBubble | null): value is ChatBubble {
  return value !== null;
}

function isResponseMode(value: unknown): value is ResponseMode {
  return value === 'fast' || value === 'deep' || value === 'review';
}

function isKnowledgeMode(value: unknown): value is KnowledgeMode {
  return value === 'auto' || value === 'direct_chat' || value === 'knowledge_qa';
}

function isWorkbenchTab(value: unknown): value is ProjectWorkspace['activeTab'] {
  return value === 'sysml' || value === 'impact' || value === 'merge' || value === 'sync';
}

function optionalString(value: unknown) {
  return typeof value === 'string' ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function loadPaneSizes(): AgentPaneSizes {
  if (typeof window === 'undefined') return defaultPaneSizes;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(paneSizesStorageKey) || '{}') as Partial<AgentPaneSizes>;
    return normalizePaneSizes(parsed);
  } catch {
    return defaultPaneSizes;
  }
}

function savePaneSizes(sizes: AgentPaneSizes) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(paneSizesStorageKey, JSON.stringify(sizes));
}

function normalizePaneSizes(value: Partial<AgentPaneSizes>): AgentPaneSizes {
  return {
    project: clampPaneSize('project', value.project),
    chat: clampPaneSize('chat', value.chat),
    explorer: clampPaneSize('explorer', value.explorer),
    summary: clampPaneSize('summary', value.summary),
  };
}

function clampPaneSize(target: PaneResizeTarget, value: unknown) {
  const parsed = Number(value);
  const fallback = defaultPaneSizes[target];
  const config = paneResizeConfig[target];
  return clampNumber(Number.isFinite(parsed) ? parsed : fallback, config.min, config.max);
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, Math.round(value)));
}

function nowTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
}
