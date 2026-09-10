import {
  ApiOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, App, Button, Divider, Progress, Select, Space, Statistic, Tag, Tooltip, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { client } from '../api/client';
import type { ModelElement, SimulationStatus } from '../types';

type ToolKey = 'gmat' | 'simulink' | 'mock';

interface SimulationScenario {
  id: string;
  requirementId: string;
  title: string;
  need: string;
  tool: ToolKey;
  modelCandidates: string[];
  modelTypePriority: string[];
  acceptance: string;
  metrics: string[];
  evidence: string;
}

interface SimulationResultPayload {
  model_id?: string;
  tool?: string;
  score?: number;
  risk?: string;
  availability?: number;
  latency_ms?: number;
  throughput_mbps?: number;
  packet_loss_pct?: number;
  final_epoch?: string;
  position_km?: number[];
  velocity_km_s?: number[];
  radius_km?: number;
  altitude_km?: number;
  estimated_period_min?: number;
  settling_time_s?: number;
  overshoot_pct?: number;
  final_value?: number;
  peak_value?: number;
  simulated_duration_s?: number;
  sample_count?: number;
  source_model_path?: string;
  report_path?: string;
  script_path?: string;
  log_path?: string;
  analysis?: string;
  suggestions?: string[];
  [key: string]: unknown;
}

interface SimulationRunResponse {
  status?: string;
  message?: string;
  result?: SimulationResultPayload;
}

interface MetricDisplay {
  label: string;
  value: string | number;
  suffix?: string;
  precision?: number;
  hideWhenZero?: boolean;
}

const simulationScenarios: SimulationScenario[] = [
  {
    id: 'orbit',
    requirementId: 'REQ-SIM-001',
    title: '轨道高度与周期验证',
    need: '验证卫星平台在给定 LEO 轨道参数下完成传播，并输出可追溯的最终历元、轨道高度与周期估算。',
    tool: 'gmat',
    modelCandidates: ['BLK-001', 'BLK-002'],
    modelTypePriority: ['Block'],
    acceptance: '轨道传播成功，轨道高度、周期和最终历元可作为需求验证证据。',
    metrics: ['轨道高度', '轨道周期', '最终历元'],
    evidence: 'GMAT 脚本、运行日志、轨道传播报告',
  },
  {
    id: 'dynamic',
    requirementId: 'REQ-SIM-002',
    title: '动态响应稳定性验证',
    need: '验证控制、载荷或平台动态模型的响应过程，关注调节时间、稳态值、峰值与超调量。',
    tool: 'simulink',
    modelCandidates: ['BLK-003', 'BLK-004', 'UC-003'],
    modelTypePriority: ['Block', 'UseCase'],
    acceptance: '动态响应完成，调节时间与超调量满足阈值后可进入下一轮设计基线。',
    metrics: ['调节时间', '超调量', '稳态值'],
    evidence: 'Simulink 模型、批处理脚本、结果 JSON',
  },
  {
    id: 'link',
    requirementId: 'REQ-SIM-003',
    title: '用户链路可用性评估',
    need: '验证用户接入链路在方案级指标下的吞吐量、时延、丢包率和可用性，用于需求初筛。',
    tool: 'mock',
    modelCandidates: ['IF-001', 'IF-002', 'UC-001'],
    modelTypePriority: ['Interface', 'UseCase', 'Block'],
    acceptance: '链路指标达到方案级阈值，可继续推送到接口约束和验证记录。',
    metrics: ['可用性', '时延', '吞吐量'],
    evidence: '方案级仿真摘要、指标映射建议',
  },
];

const toolFallbackLabel: Record<ToolKey, string> = {
  gmat: 'GMAT',
  simulink: 'Simulink',
  mock: 'Mock',
};

const toolIconMap: Record<ToolKey, JSX.Element> = {
  gmat: <RocketOutlined />,
  simulink: <ThunderboltOutlined />,
  mock: <ApiOutlined />,
};

function hasValue(value: unknown) {
  return value !== undefined && value !== null && value !== '';
}

function toolName(tool: ToolKey, status: SimulationStatus | null) {
  if (tool === 'mock') return 'Mock 回退仿真';
  return status?.tools?.[tool]?.name || toolFallbackLabel[tool];
}

function toolMode(tool: ToolKey, status: SimulationStatus | null) {
  if (tool === 'mock') return 'fallback';
  return status?.tools?.[tool]?.available ? 'real' : status?.tools?.[tool]?.mode || '待检测';
}

function buildMetrics(payload?: SimulationResultPayload): MetricDisplay[] {
  if (!payload) return [];
  return [
    { label: '评分', value: payload.score ?? '', suffix: '/100' },
    { label: '工具', value: payload.tool || '未返回' },
    { label: '风险等级', value: payload.risk || '' },
    { label: '可用性', value: hasValue(payload.availability) ? Number(payload.availability) * 100 : '', suffix: '%', precision: 2 },
    { label: '轨道高度', value: payload.altitude_km ?? '', suffix: 'km', precision: 1 },
    { label: '轨道周期', value: payload.estimated_period_min ?? '', suffix: 'min', precision: 1 },
    { label: '调节时间', value: payload.settling_time_s ?? '', suffix: 's', precision: 2 },
    { label: '超调量', value: payload.overshoot_pct ?? '', suffix: '%', precision: 2 },
    { label: '稳态值', value: payload.final_value ?? '', precision: 3 },
    { label: '仿真时长', value: payload.simulated_duration_s ?? '', suffix: 's', precision: 1 },
    { label: '时延', value: payload.latency_ms ?? '', suffix: 'ms', hideWhenZero: true },
    { label: '吞吐量', value: payload.throughput_mbps ?? '', suffix: 'Mbps', hideWhenZero: true },
    { label: '丢包率', value: payload.packet_loss_pct ?? '', suffix: '%', precision: 2 },
  ].filter((item) => hasValue(item.value) && !(item.hideWhenZero && Number(item.value) === 0));
}

function evidenceItems(payload?: SimulationResultPayload) {
  if (!payload) return [];
  return [
    { label: '报告文件', value: payload.report_path },
    { label: '脚本文件', value: payload.script_path },
    { label: '日志文件', value: payload.log_path },
    { label: 'Simulink 模型', value: payload.source_model_path },
    { label: 'GMAT 最终历元', value: payload.final_epoch },
    { label: '模型元素', value: payload.model_id },
  ].filter((item) => hasValue(item.value));
}

function resultPlotKind(payload?: SimulationResultPayload) {
  if (!payload) return 'empty';
  if (hasValue(payload.altitude_km) || hasValue(payload.estimated_period_min)) return 'orbit';
  if (hasValue(payload.settling_time_s) || hasValue(payload.overshoot_pct)) return 'dynamic';
  return 'link';
}

export default function SimulationMock() {
  const { message } = App.useApp();
  const [elements, setElements] = useState<ModelElement[]>([]);
  const [modelId, setModelId] = useState('BLK-001');
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [selectedTool, setSelectedTool] = useState<ToolKey>('mock');
  const [selectedScenarioId, setSelectedScenarioId] = useState('orbit');
  const [result, setResult] = useState<SimulationRunResponse | null>(null);
  const [scenarioResults, setScenarioResults] = useState<Record<string, SimulationRunResponse>>({});
  const [loading, setLoading] = useState(false);
  const [loadingScenarioId, setLoadingScenarioId] = useState('');

  const selectedScenario = simulationScenarios.find((item) => item.id === selectedScenarioId);
  const selectedScenarioResult = selectedScenario ? scenarioResults[selectedScenario.id] : undefined;
  const displayedResult = selectedScenario ? selectedScenarioResult : result;
  const displayedPayload = displayedResult?.result;

  const modelOptions = useMemo(
    () =>
      elements
        .filter((item) => item.type === 'Block' || item.type === 'UseCase' || item.type === 'Interface')
        .map((item) => ({ value: item.id, label: `${item.id} ${item.name}` })),
    [elements],
  );

  const toolOptions = useMemo(() => {
    const realTools = Object.entries(status?.tools || {})
      .filter(([key]) => key === 'gmat' || key === 'simulink')
      .map(([key, tool]) => ({
        value: key,
        label: `${tool.name} (${tool.available ? 'Real' : tool.mode})`,
        disabled: false,
      }));
    return [...realTools, { value: 'mock', label: 'Mock (fallback)' }];
  }, [status]);

  const load = async () => {
    const [nextElements, nextStatus] = await Promise.all([client.listElements(), client.simulationStatus()]);
    setElements(nextElements);
    setStatus(nextStatus);
    setSelectedTool((nextStatus.preferred_tool as ToolKey) || 'mock');
    const block = nextElements.find((item) => item.type === 'Block');
    if (block) setModelId(block.id);
  };

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const resolveScenarioModel = (scenario: SimulationScenario) => {
    const directMatch = scenario.modelCandidates
      .map((candidate) => elements.find((item) => item.id === candidate))
      .find(Boolean);
    if (directMatch) return directMatch;
    const typeMatch = scenario.modelTypePriority
      .map((type) => elements.find((item) => item.type === type))
      .find(Boolean);
    return typeMatch || elements.find((item) => item.id === modelId) || elements[0];
  };

  const resolveScenarioModelId = (scenario: SimulationScenario) => {
    return resolveScenarioModel(scenario)?.id || scenario.modelCandidates[0] || modelId || 'BLK-001';
  };

  const runScenario = async (scenario: SimulationScenario) => {
    const nextModelId = resolveScenarioModelId(scenario);
    setSelectedScenarioId(scenario.id);
    setModelId(nextModelId);
    setSelectedTool(scenario.tool);
    setLoadingScenarioId(scenario.id);
    try {
      const nextResult = await client.runSimulation(nextModelId, scenario.tool);
      setResult(nextResult);
      setScenarioResults((current) => ({ ...current, [scenario.id]: nextResult }));
      message.success(`${scenario.title}已完成`);
    } catch {
      message.error('仿真验证失败，请检查后端服务或工具配置');
    } finally {
      setLoadingScenarioId('');
    }
  };

  const runManual = async () => {
    setLoading(true);
    setSelectedScenarioId('');
    try {
      const nextResult = await client.runSimulation(modelId, selectedTool);
      setResult(nextResult);
      message.success('系统仿真分析完成');
    } catch {
      message.error('系统仿真分析失败，请检查后端服务');
    } finally {
      setLoading(false);
    }
  };

  const selectedScenarioModelId = selectedScenario ? resolveScenarioModelId(selectedScenario) : modelId;
  const selectedModel = selectedScenario ? resolveScenarioModel(selectedScenario) : elements.find((item) => item.id === modelId);
  const metrics = buildMetrics(displayedPayload);
  const artifacts = evidenceItems(displayedPayload);
  const score = Number(displayedPayload?.score || 0);
  const plotKind = resultPlotKind(displayedPayload);

  return (
    <div className="page-stack simulation-validation-page">
      <div className="page-heading">
        <div>
          <h1>系统仿真验证中心</h1>
          <p>围绕特定需求组织 GMAT 轨道传播、Simulink 动态模型和方案级链路仿真，形成“需求、模型、工具、指标、证据”的验证闭环。</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load}>
          刷新状态
        </Button>
      </div>

      <Alert
        type={status?.mode === 'real' ? 'success' : 'warning'}
        showIcon
        message={status?.mode === 'real' ? '真实仿真链路已接入' : '真实工具未完全可用，系统会自动回退 Mock'}
        description={`优先工具：${status?.preferred_tool || 'mock'}。GMAT 与 Simulink 的安装、启用和模型配置状态会在下方展示。`}
      />

      <div className="simulation-status-strip">
        <div className="simulation-tool-card summary">
          <span>验证闭环</span>
          <strong>需求驱动仿真</strong>
          <p>每个场景可直接运行，并把返回指标、报告文件和建议作为模型验证证据展示。</p>
        </div>
        {(['gmat', 'simulink'] as ToolKey[]).map((tool) => {
          const toolStatus = status?.tools?.[tool];
          return (
            <div className="simulation-tool-card" key={tool}>
              <div className="simulation-tool-title">
                {toolIconMap[tool]}
                <strong>{toolName(tool, status)}</strong>
                <Tag color={toolStatus?.available ? 'green' : 'gold'}>{toolStatus?.available ? 'Real' : toolStatus?.mode || '待检测'}</Tag>
              </div>
              <p>{toolStatus?.message || '等待后端状态检测'}</p>
              {toolStatus?.path && <code>{toolStatus.path}</code>}
              {toolStatus?.model_path && <code>{toolStatus.model_path}</code>}
            </div>
          );
        })}
      </div>

      <div className="simulation-scenario-grid">
        {simulationScenarios.map((scenario) => {
          const scenarioModelId = resolveScenarioModelId(scenario);
          const scenarioResult = scenarioResults[scenario.id];
          const active = selectedScenarioId === scenario.id;
          const mode = toolMode(scenario.tool, status);
          return (
            <div
              className={`simulation-scenario-card ${active ? 'active' : ''}`}
              key={scenario.id}
              onClick={() => setSelectedScenarioId(scenario.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter') setSelectedScenarioId(scenario.id);
              }}
            >
              <div className="simulation-card-header">
                <Tag color="blue">{scenario.requirementId}</Tag>
                <Tag color={mode === 'real' ? 'green' : scenario.tool === 'mock' ? 'blue' : 'gold'}>
                  {toolName(scenario.tool, status)} · {mode}
                </Tag>
              </div>
              <h3>{scenario.title}</h3>
              <p>{scenario.need}</p>
              <div className="simulation-chain-mini">
                <span>需求</span>
                <span>{scenarioModelId}</span>
                <span>{toolFallbackLabel[scenario.tool]}</span>
                <span>证据</span>
              </div>
              <div className="simulation-card-footer">
                <Typography.Text type="secondary">{scenario.metrics.join(' / ')}</Typography.Text>
                <Button
                  size="small"
                  type={active ? 'primary' : 'default'}
                  icon={<PlayCircleOutlined />}
                  loading={loadingScenarioId === scenario.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    runScenario(scenario);
                  }}
                >
                  {scenarioResult ? '重新验证' : '运行验证'}
                </Button>
              </div>
              {scenarioResult?.result && (
                <div className="simulation-card-result">
                  <CheckCircleOutlined />
                  <span>证据已生成</span>
                  <strong>{scenarioResult.result.score ?? '--'}/100</strong>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="simulation-chain">
        <div className="simulation-chain-step">
          <span>需求</span>
          <strong>{selectedScenario?.requirementId || '自定义仿真'}</strong>
          <p>{selectedScenario?.need || '通过下方手动入口选择模型元素和仿真工具。'}</p>
        </div>
        <div className="simulation-chain-step">
          <span>模型元素</span>
          <strong>{selectedModel ? `${selectedModel.id} ${selectedModel.name}` : selectedScenarioModelId}</strong>
          <p>{selectedModel?.description || `当前场景将以 ${selectedScenarioModelId} 作为仿真上下文。`}</p>
        </div>
        <div className="simulation-chain-step">
          <span>仿真工具</span>
          <strong>{selectedScenario ? toolName(selectedScenario.tool, status) : toolName(selectedTool, status)}</strong>
          <p>{selectedScenario?.acceptance || '手动运行结果会进入下方证据区。'}</p>
        </div>
        <div className="simulation-chain-step">
          <span>证据</span>
          <strong>{selectedScenario?.evidence || '仿真结果摘要'}</strong>
          <p>{displayedResult?.message || '点击场景卡片的运行验证按钮后生成指标和报告路径。'}</p>
        </div>
      </div>

      <div className="simulation-evidence-layout">
        <div className="content-band simulation-evidence-panel">
          <div className="simulation-section-title">
            <Typography.Title level={5}>
              <ExperimentOutlined /> 验证证据
            </Typography.Title>
            {displayedPayload?.tool && <Tag color="purple">{displayedPayload.tool}</Tag>}
          </div>
          {displayedResult ? (
            <>
              <Alert type={displayedResult.status === 'real' ? 'success' : 'info'} showIcon message={displayedResult.message} />
              <div className="simulation-result-header">
                <div>
                  <span>验证评分</span>
                  <strong>{displayedPayload?.score ?? '--'}</strong>
                  <em>/100</em>
                </div>
                <Progress percent={score} strokeColor={score >= 85 ? '#16a34a' : '#f59e0b'} showInfo={false} />
              </div>
              <div className="result-grid simulation-metric-grid">
                {metrics.map((item) => (
                  <Statistic
                    key={`${item.label}-${item.value}`}
                    title={item.label}
                    value={item.value}
                    precision={item.precision}
                    suffix={item.suffix}
                    valueStyle={item.label === '风险等级' ? { color: '#138a43' } : undefined}
                  />
                ))}
              </div>
              {displayedPayload?.analysis && <Alert type="success" showIcon message={displayedPayload.analysis} />}
            </>
          ) : (
            <div className="simulation-empty-state">
              <ExperimentOutlined />
              <strong>等待仿真验证</strong>
              <p>选择上方任一需求场景并点击运行验证，系统会调用 GMAT、Simulink 或回退仿真接口生成证据。</p>
            </div>
          )}
        </div>

        <div className="content-band simulation-artifact-panel">
          <div className="simulation-section-title">
            <Typography.Title level={5}>证据包与结论</Typography.Title>
            {displayedPayload?.risk && <Tag color={displayedPayload.risk === '低' ? 'green' : 'gold'}>风险 {displayedPayload.risk}</Tag>}
          </div>
          <div className={`simulation-mini-plot ${plotKind}`}>
            <div className="simulation-plot-orbit">
              <span />
              <i />
            </div>
            <div className="simulation-plot-line">
              <span />
              <span />
              <span />
            </div>
            <div className="simulation-plot-label">
              {plotKind === 'orbit' && '轨道传播证据'}
              {plotKind === 'dynamic' && '动态响应证据'}
              {plotKind === 'link' && '链路指标证据'}
              {plotKind === 'empty' && '等待结果'}
            </div>
          </div>

          {artifacts.length > 0 ? (
            <div className="simulation-artifact-list">
              {artifacts.map((item) => (
                <div key={`${item.label}-${item.value}`}>
                  <span>{item.label}</span>
                  <Tooltip title={String(item.value)}>
                    <code>{String(item.value)}</code>
                  </Tooltip>
                </div>
              ))}
            </div>
          ) : (
            <Alert type="info" showIcon message="当前还没有生成报告路径或模型证据。" />
          )}

          {displayedPayload?.suggestions?.length ? (
            <>
              <Divider />
              <div className="simulation-suggestion-list">
                {displayedPayload.suggestions.map((item) => (
                  <Tag color="blue" key={item}>
                    {item}
                  </Tag>
                ))}
              </div>
            </>
          ) : null}
        </div>
      </div>

      <div className="content-band simulation-manual-bar">
        <div>
          <Typography.Title level={5}>手动仿真调试</Typography.Title>
          <Typography.Text type="secondary">用于临时选择任意模型元素和工具，结果同样会进入上方证据区。</Typography.Text>
        </div>
        <Space.Compact block>
          <Select
            value={modelId}
            options={modelOptions}
            onChange={setModelId}
            style={{ width: 320 }}
            placeholder="选择模型元素"
          />
          <Select
            value={selectedTool}
            options={toolOptions}
            onChange={(value) => setSelectedTool(value as ToolKey)}
            style={{ width: 240 }}
            placeholder="选择仿真工具"
          />
          <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={runManual}>
            运行系统仿真
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
