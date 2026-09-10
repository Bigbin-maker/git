import { ApartmentOutlined } from '@ant-design/icons';
import { useMemo } from 'react';
import type { SysMLDiagramView } from '../types';

interface Props {
  view: SysMLDiagramView | null;
  emptyTitle?: string;
  emptyDescription?: string;
}

interface DiagramViewDrawingNode {
  id: string;
  elementId: string;
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

export default function DiagramViewCanvas({
  view,
  emptyTitle = '暂无模型视图',
  emptyDescription = '生成或推送模型后，这里会展示对应的 SysML 图视图。',
}: Props) {
  const drawing = useMemo(() => (view ? buildDiagramViewDrawing(view) : null), [view]);
  const markerId = `diagram-view-arrow-${safeDomId(view?.id || 'empty')}`;

  if (!view || !drawing?.nodes.length) {
    return (
      <div className="agent-diagram-alt-canvas">
        <div className="agent-diagram-empty-state">
          <ApartmentOutlined />
          <strong>{emptyTitle}</strong>
          <span>{emptyDescription}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-diagram-alt-canvas">
      <svg
        className="diagram-view-svg"
        width={drawing.width}
        height={drawing.height}
        viewBox={`0 0 ${drawing.width} ${drawing.height}`}
        role="img"
        aria-label={view.name}
      >
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

function buildDiagramViewDrawing(view: SysMLDiagramView) {
  const layout = view.layout || {};
  const nodes = (layout.nodes || []).map<DiagramViewDrawingNode>((node) => {
    const type = String(node.type || 'Block');
    const stereotype = node.stereotype_label || layoutStereotype(type, view.diagram_type);
    return {
      id: String(node.id || node.element_id || node.label || ''),
      elementId: String(node.element_id || node.id || ''),
      cssType: diagramViewCssType(type, stereotype),
      stereotype,
      shape: diagramViewShape(String(node.shape || type), stereotype),
      lines: splitLayoutLabel(node.label || node.name || node.id || 'UnnamedElement', 14, 2),
      x: Number(node.x || 0),
      y: Number(node.y || 0),
      width: Number(node.width || 190),
      height: Number(node.height || 72),
    };
  });
  const nodeLookup = new Map<string, DiagramViewDrawingNode>();
  nodes.forEach((node) => {
    nodeLookup.set(node.id, node);
    if (node.elementId) nodeLookup.set(node.elementId, node);
  });
  const edges = (layout.edges || []).map<DiagramViewDrawingEdge>((edge) => {
    const points = edge.points?.length ? edge.points : fallbackEdgePoints(String(edge.source), String(edge.target), nodeLookup);
    const firstPoint = points[0] || { x: 0, y: 0 };
    const labelPoint = midpoint(points) || firstPoint;
    return {
      id: String(edge.id || edge.relationship_id || `${edge.source}-${edge.target}`),
      label: truncateLayoutText(String(edge.label || edge.type || 'connector'), 18),
      path: diagramViewPathFromPoints(points),
      labelX: Number(edge.label_x || labelPoint.x),
      labelY: Number(edge.label_y || labelPoint.y),
    };
  });
  const width = Math.max(Number(layout.width || 0), ...nodes.map((node) => node.x + node.width + 80), 980);
  const height = Math.max(Number(layout.height || 0), ...nodes.map((node) => node.y + node.height + 80), 520);
  return { nodes, edges, width, height };
}

function fallbackEdgePoints(sourceId: string, targetId: string, nodeLookup: Map<string, DiagramViewDrawingNode>) {
  const source = nodeLookup.get(sourceId);
  const target = nodeLookup.get(targetId);
  if (!source || !target) return [];
  return [
    { x: source.x + source.width / 2, y: source.y + source.height / 2 },
    { x: target.x + target.width / 2, y: target.y + target.height / 2 },
  ];
}

function midpoint(points: Array<{ x: number; y: number }>) {
  if (!points.length) return null;
  const middle = Math.floor(points.length / 2);
  if (points.length % 2) return points[middle];
  return {
    x: (points[middle - 1].x + points[middle].x) / 2,
    y: (points[middle - 1].y + points[middle].y) / 2,
  };
}

function diagramViewPathFromPoints(points?: Array<{ x: number; y: number }>) {
  if (!points?.length) return '';
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
}

function layoutStereotype(type: string, diagramType: SysMLDiagramView['diagram_type']) {
  if (diagramType === 'state') return '«state»';
  if (type === 'Activity') return '«activity»';
  if (type === 'Block') return '«block»';
  if (type === 'Requirement') return '«requirement»';
  if (type === 'UseCase') return '«use case»';
  if (type === 'Interface') return '«interface»';
  if (type === 'Actor') return '«actor»';
  if (type === 'ConstraintBlock') return '«constraint»';
  return '«element»';
}

function diagramViewShape(value: string, stereotype: string): DiagramViewDrawingNode['shape'] {
  if (value === 'actor' || value === 'Actor') return 'actor';
  if (value === 'ellipse' || value === 'UseCase') return 'ellipse';
  if (value === 'soft' || value === 'Interface' || stereotype === '«state»') return 'soft';
  return 'rect';
}

function diagramViewCssType(value: string, stereotype: string) {
  if (stereotype === '«state»') return 'state';
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
