export interface HealthStatus {
  status: string;
  backend_session_id?: string;
  llm: { mode: string; available: boolean; message?: string };
  sysml: { mode: string; available: boolean; message?: string };
  magicdraw?: { mode: string; available: boolean; bridge_available?: boolean; message?: string };
  simulation: SimulationStatus;
  database: { available: boolean; message?: string };
}

export interface SimulationToolStatus {
  name: string;
  installed: boolean;
  enabled: boolean;
  available: boolean;
  mode: string;
  message?: string;
  path?: string;
  model_path?: string;
}

export interface SimulationStatus {
  mode: string;
  installed: boolean;
  available: boolean;
  preferred_tool?: string;
  tools?: Record<string, SimulationToolStatus>;
}

export interface DocumentRecord {
  id: number;
  filename: string;
  content: string;
  created_at: string;
}

export interface DocumentExtractResult {
  filename: string;
  content: string;
}

export interface KnowledgeBaseSummary {
  document_count: number;
  chunk_count: number;
  latest_documents: DocumentRecord[];
}

export interface ModelElement {
  id: string;
  name: string;
  type: string;
  description: string;
  package?: string | null;
  source_requirement?: string | null;
  status: string;
  external_id?: string | null;
  attributes?: Array<Record<string, unknown>>;
}

export interface ModelRelationship {
  id: string;
  source: string;
  target: string;
  type: string;
  description?: string;
}

export interface DiagramViewLayoutPoint {
  x: number;
  y: number;
}

export interface DiagramViewLayoutNode {
  id: string;
  element_id?: string | null;
  name?: string;
  label?: string;
  type?: string;
  stereotype_label?: string;
  shape?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export interface DiagramViewLayoutEdge {
  id: string;
  relationship_id?: string | null;
  source: string;
  target: string;
  type?: string;
  label?: string;
  points?: DiagramViewLayoutPoint[];
  label_x?: number;
  label_y?: number;
}

export interface DiagramViewLayout {
  schema?: string;
  diagram_name?: string;
  layout_source?: string;
  width?: number;
  height?: number;
  nodes?: DiagramViewLayoutNode[];
  edges?: DiagramViewLayoutEdge[];
}

export interface SysMLDiagramTraceLink {
  usecase_id: string;
  element_ids: string[];
  relation?: 'realize' | 'allocate' | string;
  description?: string;
}

export interface SysMLDiagramView {
  id: string;
  variant_id: string;
  variant_name: string;
  diagram_type: 'use_case' | 'ibd' | 'activity' | 'sequence' | 'state';
  focus_element_id?: string | null;
  name: string;
  description?: string;
  rationale?: string;
  elements: ModelElement[];
  relationships: ModelRelationship[];
  layout: DiagramViewLayout;
  sysml_text?: string;
  trace_links?: SysMLDiagramTraceLink[];
}

export interface ToolCall {
  tool: string;
  status: string;
  summary: string;
}

export interface ChatResult {
  answer: string;
  tool_calls: ToolCall[];
  artifacts: Record<string, unknown>;
}

export interface ChatMessage {
  role: string;
  content: string;
}

export interface ChatStreamEvent {
  type: 'delta' | 'done' | 'error';
  content?: string;
  answer?: string;
  message?: string;
  tool_calls?: ToolCall[];
  artifacts?: Record<string, unknown>;
}

export interface SysMLIntentResult {
  should_generate: boolean;
  intent: string;
  confidence: number;
  reason: string;
}

export interface SysMLProjectGenerateResult {
  draft_id?: number | null;
  draft_status?: 'preview' | 'revised' | 'accepted' | 'rejected' | string;
  project_name: string;
  summary: string;
  assumptions: string[];
  generation_source?: string;
  elements: ModelElement[];
  relationships: ModelRelationship[];
  diagram_views?: SysMLDiagramView[];
  sysml_text: string;
}

export interface ModelDraftRelationshipUpdate {
  source: string;
  target: string;
  type: string;
  description?: string;
  operator?: string;
  comment?: string;
}

export interface ModelDraftElementUpdate {
  name: string;
  type: string;
  description?: string;
  package?: string | null;
  source_requirement?: string | null;
  status?: string;
  operator?: string;
  comment?: string;
}

export interface ModelDraftRelationshipCreate {
  source: string;
  target: string;
  type: string;
  description?: string;
  operator?: string;
  comment?: string;
}

export interface ModelDraftAcceptResult {
  draft: SysMLProjectGenerateResult;
  commit_result: Record<string, unknown>;
}

export interface DraftValidationIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  rule_id: string;
  object_type: string;
  object_id: string;
  message: string;
  suggestion: string;
  fixable: boolean;
  fix_action?: string | null;
}

export interface DraftValidationReport {
  draft_id: number;
  score: number;
  conclusion: string;
  issues: DraftValidationIssue[];
  statistics: Record<string, number>;
}

export interface DraftValidationFixResult {
  draft: SysMLProjectGenerateResult;
  report: DraftValidationReport;
  fixed_issue_ids: string[];
}

export interface ChangeImpactSandboxRequest {
  project_name?: string;
  target_id?: string | null;
  target_name?: string;
  attribute_name?: string;
  old_value?: string;
  new_value?: string;
  unit?: string;
  change_description?: string;
  task_context?: string;
  depth?: number;
  elements?: ModelElement[];
  relationships?: ModelRelationship[];
}

export interface ChangeImpactTopologyNode {
  id: string;
  label: string;
  type: string;
  level: number;
  category: string;
  risk: 'low' | 'medium' | 'high';
  source: string;
}

export interface ChangeImpactTopologyEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
  directness: 'direct' | 'indirect';
  severity: 'low' | 'medium' | 'high';
}

export interface ChangeImpactMatrixRow {
  id: string;
  affected_object: string;
  object_type: string;
  impact_type: string;
  directness: 'direct' | 'indirect';
  path: string;
  severity: 'low' | 'medium' | 'high';
  reason: string;
  recommendation: string;
  evidence: string;
}

export interface ChangeImpactSandboxResponse {
  scenario_id?: number | null;
  report_id?: number | null;
  summary: string;
  risk_level: 'low' | 'medium' | 'high';
  task_profile: string;
  change: Record<string, unknown>;
  topology: {
    nodes: ChangeImpactTopologyNode[];
    edges: ChangeImpactTopologyEdge[];
  };
  direct_impacts: ChangeImpactMatrixRow[];
  indirect_impacts: ChangeImpactMatrixRow[];
  impact_matrix: ChangeImpactMatrixRow[];
  paths: string[][];
  suggestions: string[];
  assumptions: string[];
}

export interface MergeAuditLogRecord {
  id: number;
  action: string;
  operator: string;
  role: string;
  message: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface MergeConflictRecord {
  id: string;
  type: string;
  object_type: string;
  object_id: string;
  field: string;
  release_value: unknown;
  candidate_value: unknown;
  message: string;
  severity: 'warning' | 'high' | string;
  resolved?: boolean;
  resolution?: {
    resolution: 'use_candidate' | 'keep_release';
    operator: string;
    comment?: string;
    resolved_at?: string;
  } | null;
}

export interface MergeRequestRecord {
  id: number;
  draft_id: number;
  project_name: string;
  source_branch: string;
  target_branch: string;
  title: string;
  description: string;
  submitter: string;
  reviewer: string;
  status: 'pending' | 'conflict' | 'merged' | 'rejected' | string;
  change_set: Record<string, unknown>;
  conflicts: MergeConflictRecord[];
  resolutions: Record<string, unknown>;
  audit_logs: MergeAuditLogRecord[];
  created_at: string;
  updated_at: string;
  merged_at?: string | null;
}

export interface MergeRequestSubmitPayload {
  draft_id: number;
  title?: string;
  description?: string;
  source_branch?: string;
  target_branch?: string;
  submitter?: string;
}

export interface MergeRequestMergeResult {
  merge_request: MergeRequestRecord;
  commit_result: Record<string, unknown>;
}

export interface MagicDrawPublishResult {
  mode: string;
  available: boolean;
  message: string;
  package_name: string;
  exchange_payload: MagicDrawExchangePayload;
  files: Record<string, string>;
  bridge_response?: Record<string, unknown> | null;
}

export interface MagicDrawDiagramCatalog {
  available: boolean;
  message: string;
  project_name: string;
  source_directory: string;
  exported_at: string;
  element_count: number;
  relationship_count: number;
  diagram_count: number;
  diagram_views: SysMLDiagramView[];
}

export interface MagicDrawBridgeOperationResult {
  mode: string;
  available: boolean;
  message: string;
  saved?: boolean;
  bridge_response?: Record<string, unknown> | null;
}

export interface MagicDrawStatus {
  mode: string;
  available: boolean;
  bridge_available?: boolean;
  project_open?: boolean | null;
  project_name?: string;
  project_path_configured?: boolean;
  last_import?: Record<string, unknown>;
  bridge_response?: Record<string, unknown> | null;
  message?: string;
}

export interface MagicDrawExchangeElement {
  local_id?: string;
  name?: string;
  type?: string;
  package?: string;
  metaclass?: string;
  stereotype?: string;
  documentation?: string;
  source_requirement?: string | null;
  status?: string;
  tags?: Record<string, unknown>;
}

export interface MagicDrawExchangeRelationship {
  local_id?: string;
  name?: string;
  type?: string;
  package?: string;
  metaclass?: string;
  stereotype?: string;
  source?: string;
  source_name?: string;
  target?: string;
  target_name?: string;
  documentation?: string;
}

export interface MagicDrawLayoutPoint {
  x: number;
  y: number;
}

export interface MagicDrawLayoutNode {
  id: string;
  element_id?: string;
  name?: string;
  label?: string;
  type?: string;
  stereotype_label?: string;
  shape?: 'rect' | 'soft' | 'ellipse' | string;
  column?: number;
  row?: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MagicDrawLayoutEdge {
  id: string;
  relationship_id?: string;
  source: string;
  target: string;
  type?: string;
  label?: string;
  points?: MagicDrawLayoutPoint[];
  label_x?: number;
  label_y?: number;
}

export interface MagicDrawDiagramLayout {
  schema?: string;
  diagram_name?: string;
  layout_source?: string;
  width?: number;
  height?: number;
  nodes?: MagicDrawLayoutNode[];
  edges?: MagicDrawLayoutEdge[];
}

export interface MagicDrawExchangePayload {
  schema?: string;
  generated_at?: string;
  project_path?: string;
  root_package?: string;
  diagram_name?: string;
  instructions?: string[];
  elements?: MagicDrawExchangeElement[];
  relationships?: MagicDrawExchangeRelationship[];
  diagram_layout?: MagicDrawDiagramLayout;
}
