import axios from 'axios';
import type {
  ChangeImpactSandboxRequest,
  ChangeImpactSandboxResponse,
  ChatMessage,
  ChatResult,
  ChatStreamEvent,
  DocumentExtractResult,
  DocumentRecord,
  DraftValidationFixResult,
  DraftValidationReport,
  HealthStatus,
  KnowledgeBaseSummary,
  MagicDrawDiagramCatalog,
  ModelDraftAcceptResult,
  ModelDraftElementUpdate,
  ModelDraftRelationshipCreate,
  ModelDraftRelationshipUpdate,
  MagicDrawBridgeOperationResult,
  MagicDrawPublishResult,
  MagicDrawStatus,
  MergeRequestMergeResult,
  MergeRequestRecord,
  MergeRequestSubmitPayload,
  ModelElement,
  ModelRelationship,
  SimulationStatus,
  SysMLDiagramView,
  SysMLIntentResult,
  SysMLProjectGenerateResult,
  ToolCall,
} from '../types';

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: apiBaseURL,
  timeout: 240000,
});

interface ChatStreamHandlers {
  onDelta?: (content: string) => void;
  onDone?: (result: { answer: string; tool_calls: ToolCall[]; artifacts: Record<string, unknown> }) => void;
  onError?: (message: string) => void;
}

export const client = {
  health: async () => (await api.get<HealthStatus>('/health')).data,
  chat: async (message: string, taskType: string, conversation: ChatMessage[] = []) =>
    (await api.post<ChatResult>('/chat', { session_id: 'demo-session', message, task_type: taskType, conversation })).data,
  uploadDocument: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return (await api.post<DocumentRecord>('/documents/upload', form)).data;
  },
  extractDocument: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return (await api.post<DocumentExtractResult>('/documents/extract', form)).data;
  },
  listDocuments: async () => (await api.get<DocumentRecord[]>('/documents')).data,
  knowledgeSummary: async () => (await api.get<KnowledgeBaseSummary>('/documents/knowledge-summary')).data,
  resetKnowledgeBase: async () => (await api.delete<{ deleted_documents: number; deleted_chunks: number }>('/documents/knowledge')).data,
  streamChat: async (message: string, taskType: string, conversation: ChatMessage[] = [], handlers: ChatStreamHandlers = {}) => {
    const response = await fetch(`${apiBaseURL.replace(/\/$/, '')}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: 'demo-session', message, task_type: taskType, conversation }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`Chat stream failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const handleLine = (line: string) => {
      if (!line.trim()) return;
      const event = JSON.parse(line) as ChatStreamEvent;
      if (event.type === 'delta') {
        handlers.onDelta?.(event.content || '');
      } else if (event.type === 'done') {
        handlers.onDone?.({
          answer: event.answer || '',
          tool_calls: event.tool_calls || [],
          artifacts: event.artifacts || {},
        });
      } else if (event.type === 'error') {
        handlers.onError?.(event.message || 'AI stream error');
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      lines.forEach(handleLine);
    }
    buffer += decoder.decode();
    handleLine(buffer);
  },
  generateSysmlProject: async (
    projectName: string,
    prompt: string,
    conversation: Array<{ role: string; content: string }>,
  ) =>
    (
      await api.post<SysMLProjectGenerateResult>('/sysml/generate-project', {
        project_name: projectName,
        prompt,
        conversation,
      })
    ).data,
  generateInternalBlockDiagram: async (payload: {
    project_name: string;
    prompt: string;
    focus_element: ModelElement;
    elements: ModelElement[];
    relationships: ModelRelationship[];
  }) => (await api.post<SysMLDiagramView>('/sysml/internal-block-diagram', payload)).data,
  classifySysmlIntent: async (message: string, conversation: ChatMessage[] = []) =>
    (await api.post<SysMLIntentResult>('/sysml/classify-intent', { message, conversation })).data,
  getModelDraft: async (draftId: number) =>
    (await api.get<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}`)).data,
  updateDraftElement: async (draftId: number, elementId: string, payload: ModelDraftElementUpdate) =>
    (await api.patch<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}/elements/${elementId}`, payload)).data,
  updateDraftRelationship: async (draftId: number, relationshipId: string, payload: ModelDraftRelationshipUpdate) =>
    (await api.patch<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}/relationships/${relationshipId}`, payload)).data,
  createDraftRelationship: async (draftId: number, payload: ModelDraftRelationshipCreate) =>
    (await api.post<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}/relationships`, payload)).data,
  deleteDraftRelationship: async (draftId: number, relationshipId: string) =>
    (await api.delete<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}/relationships/${relationshipId}`)).data,
  validateModelDraft: async (draftId: number) =>
    (await api.post<DraftValidationReport>(`/sysml/drafts/${draftId}/validate`)).data,
  fixModelDraftIssues: async (draftId: number, issueIds: string[]) =>
    (await api.post<DraftValidationFixResult>(`/sysml/drafts/${draftId}/fix`, { issue_ids: issueIds, operator: 'demo-user' })).data,
  acceptModelDraft: async (draftId: number, comment = '') =>
    (await api.post<ModelDraftAcceptResult>(`/sysml/drafts/${draftId}/accept`, { operator: 'demo-user', comment })).data,
  rejectModelDraft: async (draftId: number, comment = '') =>
    (await api.post<SysMLProjectGenerateResult>(`/sysml/drafts/${draftId}/reject`, { operator: 'demo-user', comment })).data,
  submitMergeRequest: async (payload: MergeRequestSubmitPayload) =>
    (await api.post<MergeRequestRecord>('/merge/requests', payload)).data,
  listMergeRequests: async (role = 'admin', operator = '') =>
    (await api.get<{ items: MergeRequestRecord[] }>('/merge/requests', { params: { role, operator } })).data.items,
  resolveMergeConflict: async (mergeRequestId: number, conflictId: string, resolution: 'use_candidate' | 'keep_release', comment = '') =>
    (
      await api.post<MergeRequestRecord>(`/merge/requests/${mergeRequestId}/resolve`, {
        conflict_id: conflictId,
        resolution,
        operator: 'admin',
        role: 'admin',
        comment,
      })
    ).data,
  mergeIntoRelease: async (mergeRequestId: number, comment = '') =>
    (await api.post<MergeRequestMergeResult>(`/merge/requests/${mergeRequestId}/merge`, { operator: 'admin', role: 'admin', comment })).data,
  rejectMergeRequest: async (mergeRequestId: number, comment = '') =>
    (await api.post<MergeRequestRecord>(`/merge/requests/${mergeRequestId}/reject`, { operator: 'admin', role: 'admin', comment })).data,
  runChangeImpactAnalysis: async (payload: ChangeImpactSandboxRequest) =>
    (await api.post<ChangeImpactSandboxResponse>('/impact/sandbox', payload)).data,
  magicDrawStatus: async () => (await api.get<MagicDrawStatus>('/magicdraw/status')).data,
  magicDrawDiagramCatalog: async () => (await api.get<MagicDrawDiagramCatalog>('/magicdraw/diagram-catalog')).data,
  publishMagicDraw: async (elements: ModelElement[], relationships: ModelRelationship[], packageName?: string, diagramViews: SysMLDiagramView[] = []) =>
    (
      await api.post<MagicDrawPublishResult>('/magicdraw/publish', {
        elements,
        relationships,
        package_name: packageName,
        diagram_views: diagramViews,
      })
    ).data,
  saveMagicDrawProject: async () => (await api.post<MagicDrawBridgeOperationResult>('/magicdraw/save')).data,
  readMagicDrawCurrentModel: async () => (await api.get<MagicDrawBridgeOperationResult>('/magicdraw/current-model')).data,
  listElements: async () => (await api.get<ModelElement[]>('/sysml/elements')).data,
  simulationStatus: async () => (await api.get<SimulationStatus>('/simulation/status')).data,
  runSimulation: async (modelId: string, tool?: string) =>
    (await api.post('/simulation/run', { model_id: modelId, tool })).data,
};
