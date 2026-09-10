from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthSection(BaseModel):
    mode: str
    available: bool = True


class HealthResponse(BaseModel):
    status: str
    llm: HealthSection
    sysml: HealthSection
    magicdraw: dict[str, Any] | None = None
    simulation: dict[str, Any]
    database: dict[str, Any]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content: str
    created_at: datetime


class DocumentExtractResponse(BaseModel):
    filename: str
    content: str


class KnowledgeBaseSummary(BaseModel):
    document_count: int
    chunk_count: int
    latest_documents: list[DocumentOut] = Field(default_factory=list)


class RequirementBase(BaseModel):
    id: str
    name: str
    description: str
    type: str
    priority: str
    source: str
    score: int
    suggestion: str
    status: str = "pending"


class RequirementOut(RequirementBase):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime | None = None
    updated_at: datetime | None = None


class RequirementAnalyzeRequest(BaseModel):
    source_text: str
    scenario: str = "宽带通信"


class RequirementAnalyzeResponse(BaseModel):
    requirements: list[RequirementBase]


class RequirementReviewRequest(BaseModel):
    action: Literal["confirm", "reject", "update"]
    name: str | None = None
    description: str | None = None
    type: str | None = None
    priority: str | None = None
    score: int | None = None
    suggestion: str | None = None
    operator: str = "demo-user"


class ToolCall(BaseModel):
    tool: str
    status: str
    summary: str


class DialogueMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str = "demo-session"
    message: str
    task_type: str = "chat"
    conversation: list[DialogueMessageIn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall]
    artifacts: dict[str, Any] = Field(default_factory=dict)


class ModelElement(BaseModel):
    id: str
    name: str
    type: str
    description: str
    package: str | None = None
    source_requirement: str | None = None
    status: str = "candidate"
    external_id: str | None = None
    attributes: list[dict[str, Any]] = Field(default_factory=list)


class ModelRelationship(BaseModel):
    id: str
    source: str
    target: str
    type: str
    description: str = ""


class DiagramLayoutPoint(BaseModel):
    x: float
    y: float


class DiagramLayoutNode(BaseModel):
    id: str
    element_id: str | None = None
    name: str = ""
    label: str = ""
    type: str = "Block"
    stereotype_label: str = ""
    shape: str = "rect"
    x: float = 0
    y: float = 0
    width: float = 180
    height: float = 72


class DiagramLayoutEdge(BaseModel):
    id: str
    relationship_id: str | None = None
    source: str
    target: str
    type: str = "trace"
    label: str = ""
    points: list[DiagramLayoutPoint] = Field(default_factory=list)
    label_x: float = 0
    label_y: float = 0


class DiagramLayout(BaseModel):
    schema: str = "ai-mbse.diagram-view-layout.v1"
    diagram_name: str = ""
    layout_source: str = "backend"
    width: float = 980
    height: float = 520
    nodes: list[DiagramLayoutNode] = Field(default_factory=list)
    edges: list[DiagramLayoutEdge] = Field(default_factory=list)


class DiagramView(BaseModel):
    id: str
    variant_id: str
    variant_name: str
    diagram_type: Literal["use_case", "ibd", "activity", "sequence", "state"]
    focus_element_id: str | None = None
    name: str
    description: str = ""
    rationale: str = ""
    elements: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    layout: DiagramLayout
    sysml_text: str = ""
    trace_links: list[dict[str, Any]] = Field(default_factory=list)


class SysMLGenerateRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)


class SysMLGenerateResponse(BaseModel):
    elements: list[ModelElement]
    relationships: list[ModelRelationship]


class SysMLProjectGenerateRequest(BaseModel):
    project_name: str = "AI_LEO_Satellite_MBSE_Project"
    prompt: str = ""
    conversation: list[DialogueMessageIn] = Field(default_factory=list)


class InternalBlockDiagramGenerateRequest(BaseModel):
    project_name: str = "AI_MBSE_Project"
    prompt: str = ""
    focus_element: ModelElement
    elements: list[ModelElement] = Field(default_factory=list)
    relationships: list[ModelRelationship] = Field(default_factory=list)


class SysMLProjectGenerateResponse(BaseModel):
    draft_id: int | None = None
    draft_status: str = "preview"
    project_name: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    generation_source: str = "unknown"
    elements: list[ModelElement]
    relationships: list[ModelRelationship]
    sysml_text: str
    diagram_views: list[DiagramView] = Field(default_factory=list)


class ModelDraftRelationshipUpdateRequest(BaseModel):
    source: str
    target: str
    type: str
    description: str = ""
    operator: str = "demo-user"
    comment: str = ""


class ModelDraftElementUpdateRequest(BaseModel):
    name: str
    type: str
    description: str = ""
    package: str | None = None
    source_requirement: str | None = None
    status: str = "candidate"
    operator: str = "demo-user"
    comment: str = ""


class ModelDraftRelationshipCreateRequest(BaseModel):
    source: str
    target: str
    type: str = "trace"
    description: str = ""
    operator: str = "demo-user"
    comment: str = ""


class ModelDraftFeedbackRequest(BaseModel):
    operator: str = "demo-user"
    comment: str = ""


class ModelDraftAcceptResponse(BaseModel):
    draft: SysMLProjectGenerateResponse
    commit_result: dict[str, Any]


class MergeRequestSubmitRequest(BaseModel):
    draft_id: int
    title: str = ""
    description: str = ""
    source_branch: str = "dev/designer"
    target_branch: str = "release/main"
    submitter: str = "designer"


class MergeConflictResolutionRequest(BaseModel):
    conflict_id: str
    resolution: Literal["use_candidate", "keep_release"]
    operator: str = "admin"
    role: Literal["admin", "designer"] = "admin"
    comment: str = ""


class MergeRequestActionRequest(BaseModel):
    operator: str = "admin"
    role: Literal["admin", "designer"] = "admin"
    comment: str = ""


class MergeAuditLogOut(BaseModel):
    id: int
    action: str
    operator: str
    role: str
    message: str
    detail: dict[str, Any]
    created_at: datetime


class MergeRequestOut(BaseModel):
    id: int
    draft_id: int
    project_name: str
    source_branch: str
    target_branch: str
    title: str
    description: str
    submitter: str
    reviewer: str
    status: str
    change_set: dict[str, Any]
    conflicts: list[dict[str, Any]]
    resolutions: dict[str, Any]
    audit_logs: list[MergeAuditLogOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None


class MergeRequestListResponse(BaseModel):
    items: list[MergeRequestOut]


class MergeRequestMergeResponse(BaseModel):
    merge_request: MergeRequestOut
    commit_result: dict[str, Any]


class DraftValidationIssue(BaseModel):
    id: str
    severity: Literal["error", "warning", "info"]
    rule_id: str
    object_type: str
    object_id: str
    message: str
    suggestion: str
    fixable: bool = False
    fix_action: str | None = None


class DraftValidationReport(BaseModel):
    draft_id: int
    score: int
    conclusion: str
    issues: list[DraftValidationIssue]
    statistics: dict[str, int]


class DraftValidationFixRequest(BaseModel):
    issue_ids: list[str] = Field(default_factory=list)
    operator: str = "demo-user"


class DraftValidationFixResponse(BaseModel):
    draft: SysMLProjectGenerateResponse
    report: DraftValidationReport
    fixed_issue_ids: list[str]


class SysMLIntentRequest(BaseModel):
    message: str
    conversation: list[DialogueMessageIn] = Field(default_factory=list)


class SysMLIntentResponse(BaseModel):
    should_generate: bool
    intent: str
    confidence: float
    reason: str


class SysMLCommitRequest(BaseModel):
    elements: list[ModelElement]
    relationships: list[ModelRelationship]


class SysMLCommitResponse(BaseModel):
    mode: str
    message: str
    elements: list[dict[str, Any]]
    relationships: list[dict[str, Any]]


class MagicDrawPublishRequest(BaseModel):
    elements: list[ModelElement]
    relationships: list[ModelRelationship]
    package_name: str | None = None
    diagram_views: list[dict[str, Any]] = Field(default_factory=list)


class MagicDrawPublishResponse(BaseModel):
    mode: str
    available: bool
    message: str
    package_name: str
    exchange_payload: dict[str, Any]
    files: dict[str, str] = Field(default_factory=dict)
    bridge_response: dict[str, Any] | None = None


class MagicDrawDiagramCatalogResponse(BaseModel):
    available: bool
    message: str
    project_name: str = ""
    source_directory: str = ""
    exported_at: str = ""
    element_count: int = 0
    relationship_count: int = 0
    diagram_count: int = 0
    diagram_views: list[DiagramView] = Field(default_factory=list)


class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ImpactAnalysisRequest(BaseModel):
    element_id: str
    change_description: str
    depth: int = 3


class ImpactAnalysisResponse(BaseModel):
    summary: str
    risk_level: str
    direct_impacts: list[dict[str, Any]]
    indirect_impacts: list[dict[str, Any]]
    paths: list[list[str]]
    suggestions: list[str]


class ChangeImpactSandboxRequest(BaseModel):
    project_name: str = ""
    target_id: str | None = None
    target_name: str = ""
    attribute_name: str = ""
    old_value: str = ""
    new_value: str = ""
    unit: str = ""
    change_description: str = ""
    task_context: str = ""
    depth: int = 3
    elements: list[ModelElement] = Field(default_factory=list)
    relationships: list[ModelRelationship] = Field(default_factory=list)


class ChangeImpactTopologyNode(BaseModel):
    id: str
    label: str
    type: str
    level: int
    category: str
    risk: Literal["low", "medium", "high"]
    source: str = "graph"


class ChangeImpactTopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    type: str
    directness: Literal["direct", "indirect"]
    severity: Literal["low", "medium", "high"]


class ChangeImpactTopology(BaseModel):
    nodes: list[ChangeImpactTopologyNode]
    edges: list[ChangeImpactTopologyEdge]


class ChangeImpactMatrixRow(BaseModel):
    id: str
    affected_object: str
    object_type: str
    impact_type: str
    directness: Literal["direct", "indirect"]
    path: str
    severity: Literal["low", "medium", "high"]
    reason: str
    recommendation: str
    evidence: str = ""


class ChangeImpactSandboxResponse(BaseModel):
    scenario_id: int | None = None
    report_id: int | None = None
    summary: str
    risk_level: Literal["low", "medium", "high"]
    task_profile: str
    change: dict[str, Any]
    topology: ChangeImpactTopology
    direct_impacts: list[ChangeImpactMatrixRow]
    indirect_impacts: list[ChangeImpactMatrixRow]
    impact_matrix: list[ChangeImpactMatrixRow]
    paths: list[list[str]]
    suggestions: list[str]
    assumptions: list[str]


class ValidationIssue(BaseModel):
    level: str
    type: str
    element_id: str
    message: str
    suggestion: str


class ValidationReportOut(BaseModel):
    id: int | None = None
    score: int
    conclusion: str
    issues: list[ValidationIssue]
    statistics: dict[str, int]
    created_at: datetime | None = None


class SimulationRunRequest(BaseModel):
    model_id: str
    tool: str | None = None


class SimulationRunResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]
