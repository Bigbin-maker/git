import {
  ApartmentOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  ReloadOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { Alert, Badge, Button, Empty, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { client } from '../api/client';
import DiagramViewCanvas from '../components/DiagramViewCanvas';
import type { MagicDrawDiagramCatalog, SysMLDiagramView } from '../types';

type DiagramType = SysMLDiagramView['diagram_type'];
type FilterKey = DiagramType | 'all';

const diagramTypeMeta: Record<DiagramType, { label: string; shortLabel: string; color: string; icon: JSX.Element; role: string }> = {
  use_case: {
    label: '用例图',
    shortLabel: '用例',
    color: 'blue',
    icon: <RobotOutlined />,
    role: '定义系统边界、外部参与者和顶层能力',
  },
  ibd: {
    label: '内部模块图',
    shortLabel: '结构',
    color: 'cyan',
    icon: <ApartmentOutlined />,
    role: '说明系统组成、接口和部件连接',
  },
  activity: {
    label: '活动图',
    shortLabel: '活动',
    color: 'green',
    icon: <BranchesOutlined />,
    role: '呈现关键业务流程和处理顺序',
  },
  sequence: {
    label: '顺序图',
    shortLabel: '交互',
    color: 'purple',
    icon: <FileTextOutlined />,
    role: '表达模块、接口与用例之间的时序协同',
  },
  state: {
    label: '运行状态图',
    shortLabel: '状态',
    color: 'orange',
    icon: <ExperimentOutlined />,
    role: '补齐系统待命、运行、降级和恢复等生命周期状态',
  },
};

const filterOrder: FilterKey[] = ['all', 'use_case', 'ibd', 'activity', 'sequence', 'state'];

export default function SystemModelViews() {
  const [catalog, setCatalog] = useState<MagicDrawDiagramCatalog | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all');
  const [activeViewId, setActiveViewId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadCatalog = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await client.magicDrawDiagramCatalog();
      setCatalog(data);
      setActiveViewId((current) => {
        if (current && data.diagram_views.some((view) => view.id === current)) return current;
        return pickInitialView(data.diagram_views)?.id || '';
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取模型图视图失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCatalog();
  }, []);

  const views = catalog?.diagram_views || [];
  const typeCounts = useMemo(() => countByDiagramType(views), [views]);
  const filteredViews = useMemo(
    () => (activeFilter === 'all' ? views : views.filter((view) => view.diagram_type === activeFilter)),
    [activeFilter, views],
  );
  const selectedView = useMemo(
    () => views.find((view) => view.id === activeViewId) || filteredViews[0] || null,
    [activeViewId, filteredViews, views],
  );
  const selectedElementCount = selectedView ? Math.max(selectedView.elements.length, selectedView.layout.nodes?.length || 0) : 0;
  const selectedRelationshipCount = selectedView ? Math.max(selectedView.relationships.length, selectedView.layout.edges?.length || 0) : 0;

  useEffect(() => {
    if (!filteredViews.length) {
      setActiveViewId('');
      return;
    }
    if (!filteredViews.some((view) => view.id === activeViewId)) {
      setActiveViewId(filteredViews[0].id);
    }
  }, [activeFilter, activeViewId, filteredViews]);

  const filterOptions = filterOrder.map((key) => ({
    label: (
      <span className="system-model-filter-label">
        {key === 'all' ? <BranchesOutlined /> : diagramTypeMeta[key].icon}
        <span>{key === 'all' ? '全部' : diagramTypeMeta[key].shortLabel}</span>
        <em>{key === 'all' ? views.length : typeCounts[key] || 0}</em>
      </span>
    ),
    value: key,
    disabled: key !== 'all' && !typeCounts[key],
  }));

  return (
    <div className="page-stack system-model-page">
      <div className="page-heading">
        <div>
          <h1>系统模型视图</h1>
          <p>集中展示 MagicDraw 导出的用例图、内部模块图、活动图、顺序图和运行状态图，用一套图册表达系统边界、结构、行为与运行状态闭环。</p>
        </div>
        <Space size={8} wrap>
          <Badge status={catalog?.available ? 'success' : 'warning'} text={catalog?.available ? '图册已同步' : '等待图册'} />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadCatalog}>
            刷新
          </Button>
        </Space>
      </div>

      {error && <Alert type="error" showIcon message="模型图视图读取失败" description={error} />}

      <section className="system-model-overview">
        <ModelMetric label="模型元素" value={catalog?.element_count || 0} hint="Elements" />
        <ModelMetric label="关系链路" value={catalog?.relationship_count || 0} hint="Relationships" />
        <ModelMetric label="图视图" value={views.length} hint={catalog?.source_directory || 'Diagram views'} />
        <ModelMetric label="运行状态图" value={typeCounts.state || 0} hint={(typeCounts.state || 0) > 0 ? '已覆盖' : '待补充'} tone={(typeCounts.state || 0) > 0 ? 'ok' : 'warn'} />
        <div className="system-model-flow">
          {(['use_case', 'ibd', 'activity', 'sequence', 'state'] as DiagramType[]).map((type) => (
            <button
              className={`system-model-flow-step ${activeFilter === type ? 'active' : ''}`}
              disabled={!typeCounts[type]}
              key={type}
              onClick={() => setActiveFilter(type)}
            >
              {typeCounts[type] ? <CheckCircleOutlined /> : diagramTypeMeta[type].icon}
              <span>{diagramTypeMeta[type].shortLabel}</span>
            </button>
          ))}
        </div>
      </section>

      {loading && !catalog ? (
        <section className="content-band system-model-loading">
          <Spin />
          <span>正在读取最新 MagicDraw 图册...</span>
        </section>
      ) : !catalog?.available ? (
        <section className="content-band">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={catalog?.message || '暂无可展示的模型图视图'} />
        </section>
      ) : (
        <section className="system-model-workspace">
          <aside className="system-model-rail">
            <div className="system-model-panel-title">
              <strong>模型视图目录</strong>
              <span>{formatExportTime(catalog.exported_at)}</span>
            </div>
            <Segmented block value={activeFilter} options={filterOptions} onChange={(value) => setActiveFilter(value as FilterKey)} />
            <div className="system-model-view-list">
              {filteredViews.map((view) => (
                <button
                  className={`system-model-view-item ${view.id === selectedView?.id ? 'active' : ''}`}
                  key={view.id}
                  onClick={() => setActiveViewId(view.id)}
                >
                  <span>{diagramTypeMeta[view.diagram_type].icon}</span>
                  <strong>{view.name}</strong>
                  <em>{diagramTypeMeta[view.diagram_type].label}</em>
                </button>
              ))}
            </div>
          </aside>

          <section className="system-model-stage">
            <div className="system-model-stage-header">
              <div>
                <Typography.Text className="system-model-kicker">{selectedView ? diagramTypeMeta[selectedView.diagram_type].label : '模型视图'}</Typography.Text>
                <strong>{selectedView?.name || '暂无选中图视图'}</strong>
                <span>{selectedView?.description || '选择左侧视图后查看对应的模型画布。'}</span>
              </div>
              {selectedView && <Tag color={diagramTypeMeta[selectedView.diagram_type].color}>{diagramTypeMeta[selectedView.diagram_type].role}</Tag>}
            </div>
            <div className="system-model-canvas">
              <DiagramViewCanvas view={selectedView} emptyTitle="暂无可展示图视图" emptyDescription="请先在 AI 工作台生成并推送 MagicDraw 图册。" />
            </div>
          </section>

          <aside className="system-model-detail">
            <div className="system-model-panel-title">
              <strong>视图说明</strong>
              <span>{selectedView?.variant_name || catalog.project_name}</span>
            </div>
            <div className="system-model-detail-block">
              <span>工程包</span>
              <strong>{catalog.project_name}</strong>
            </div>
            <div className="system-model-detail-grid">
              <MiniMetric label="元素" value={selectedElementCount} />
              <MiniMetric label="关系" value={selectedRelationshipCount} />
              <MiniMetric label="追溯" value={selectedView?.trace_links?.length || 0} />
              <MiniMetric label="画布节点" value={selectedView?.layout.nodes?.length || 0} />
            </div>
            <div className="system-model-detail-block">
              <span>设计意图</span>
              <p>{selectedView?.rationale || selectedView?.description || '当前视图用于补齐系统模型在评审中的可见性。'}</p>
            </div>
            <div className="system-model-detail-block">
              <span>类型覆盖</span>
              <div className="system-model-coverage-list">
                {(['use_case', 'ibd', 'activity', 'sequence', 'state'] as DiagramType[]).map((type) => (
                  <div className={typeCounts[type] ? 'covered' : ''} key={type}>
                    <span>{diagramTypeMeta[type].label}</span>
                    <strong>{typeCounts[type] || 0}</strong>
                  </div>
                ))}
              </div>
            </div>
            {selectedView?.sysml_text && (
              <pre className="system-model-code">
                <code>{selectedView.sysml_text}</code>
              </pre>
            )}
          </aside>
        </section>
      )}
    </div>
  );
}

function pickInitialView(views: SysMLDiagramView[]) {
  const priority: DiagramType[] = ['use_case', 'ibd', 'activity', 'sequence', 'state'];
  return priority.map((type) => views.find((view) => view.diagram_type === type)).find(Boolean) || views[0] || null;
}

function countByDiagramType(views: SysMLDiagramView[]) {
  return views.reduce<Record<DiagramType, number>>(
    (counts, view) => {
      counts[view.diagram_type] += 1;
      return counts;
    },
    { use_case: 0, ibd: 0, activity: 0, sequence: 0, state: 0 },
  );
}

function formatExportTime(value?: string) {
  if (!value) return '暂无导出时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function ModelMetric({ label, value, hint, tone = 'default' }: { label: string; value: number; hint: string; tone?: 'default' | 'ok' | 'warn' }) {
  return (
    <div className={`system-model-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{hint}</em>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="system-model-mini-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
