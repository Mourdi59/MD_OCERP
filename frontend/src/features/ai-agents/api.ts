// AI Agents — typed client for the /api/v1/ai-agents/* surface.

import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/lib/api';

export interface AgentDescriptor {
  name: string;
  description: string;
  system_prompt?: string;
  max_iterations: number;
  allowed_tools: string[];
  // Presentation metadata (see backend base.Agent).
  display_name?: string;
  category?: string;
  icon?: string;
  tagline?: string;
  example_prompts?: string[];
  // True for the caller's own user-authored agents (editable/deletable).
  is_custom?: boolean;
  custom_id?: string | null;
}

// The friendly guided-builder spec a non-technical user fills in. The backend
// compiles these plain-language fields into a well-formed system prompt.
export interface GuidedAgentSpec {
  role?: string;
  goal: string;
  audience?: string;
  output_format?: string;
  extra_guidance?: string;
}

export interface CustomAgent {
  id: string;
  user_id: string;
  display_name: string;
  tagline: string;
  description: string;
  category: string;
  icon: string;
  example_prompts: string[];
  system_prompt: string;
  guided: GuidedAgentSpec | null;
  created_at: string;
  updated_at: string;
}

export interface CustomAgentInput {
  display_name: string;
  tagline?: string;
  description?: string;
  category: string;
  icon: string;
  example_prompts?: string[];
  guided?: GuidedAgentSpec | null;
  system_prompt?: string;
}

export type AgentStepRole =
  | 'thought'
  | 'tool_call'
  | 'observation'
  | 'answer'
  | 'error';

export interface AgentStep {
  id: string;
  step_idx: number;
  role: AgentStepRole;
  content: unknown;
  token_count: number;
  created_at: string;
}

export interface AgentRun {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  // How the run was initiated: 'manual' | 'schedule' | 'event:<name>'.
  trigger_source: string;
  failure_reason: string | null;
  user_input: string;
  final_output: string | null;
  iterations: number;
  total_tokens: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  steps: AgentStep[];
}

export interface AgentRunListItem {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  // How the run was initiated: 'manual' | 'schedule' | 'event:<name>'.
  trigger_source: string;
  failure_reason: string | null;
  iterations: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRunRequest {
  agent_name: string;
  project_id?: string | null;
  user_input: string;
}

export interface AgentHealth {
  llm_configured: boolean;
  provider: string | null;
  model: string | null;
  settings_url: string;
}

// ── Automation: schedule + tools + triggers (Item 29) ────────────────────────

/** The automation envelope of a custom agent (schedule + tools + triggers). */
export interface AgentMetadata {
  cron: string | null;
  schedule_enabled: boolean;
  next_run_at: string | null;
  schedule_input: string;
  triggers: string[];
  allowed_tools: string[];
}

export interface SetScheduleRequest {
  cron_expr: string;
  enabled?: boolean;
  schedule_input?: string;
  triggers?: string[];
}

/** A runner tool plus the permission an operator needs to grant it. */
export interface ToolWithPermission {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  required_permission: string;
}

/** Tool-picker payload: full catalogue + the agent's current grant. */
export interface AgentTools {
  available: ToolWithPermission[];
  selected: string[];
}

export interface SetToolsRequest {
  allowed_tools: string[];
}

export interface SetTriggersRequest {
  triggers: string[];
}

/** One subscribable platform event for the trigger picker. */
export interface EventTriggerDescriptor {
  name: string;
  label: string;
  description: string;
  available: boolean;
}

// ── BOQ proposals: extract + apply (human-confirmed) ──────────────────────────

/** One structured BOQ-position proposal a run produced (money as strings). */
export interface PositionProposalDto {
  description: string;
  unit: string;
  qty: number;
  unit_rate: string;
  currency: string;
  total: string;
}

/** The applyable proposals a run produced (GET /runs/{id}/proposals). */
export interface RunProposals {
  run_id: string;
  project_id: string | null;
  count: number;
  currencies: string[];
  mixed_currency: boolean;
  proposals: PositionProposalDto[];
}

export interface ApplyProposalsRequest {
  boq_id: string;
}

/** Outcome of applying a run's proposals to a BOQ (POST /runs/{id}/apply). */
export interface ApplyProposalsResult {
  run_id: string;
  boq_id: string;
  created: number;
  skipped: number;
  currency: string | null;
  created_ordinals: string[];
  skipped_reasons: string[];
}

/** A BOQ a run's proposals can be applied to (subset of the BOQ list item). */
export interface BoqOption {
  id: string;
  name: string;
}

export const aiAgentsApi = {
  listAgents: () => apiGet<AgentDescriptor[]>('/v1/ai-agents/agents/'),
  listRuns: (projectId?: string) =>
    apiGet<AgentRunListItem[]>(
      `/v1/ai-agents/runs/${projectId ? `?project_id=${projectId}` : ''}`,
    ),
  // Monitoring: automated (scheduler / event-fired) runs across all projects.
  listAutomatedRuns: () =>
    apiGet<AgentRunListItem[]>('/v1/ai-agents/runs/automated'),
  getRun: (runId: string) => apiGet<AgentRun>(`/v1/ai-agents/runs/${runId}`),
  startRun: (body: CreateAgentRunRequest) =>
    apiPost<AgentRun, CreateAgentRunRequest>('/v1/ai-agents/runs/', body),
  health: () => apiGet<AgentHealth>('/v1/ai-agents/health/'),

  // Custom (user-authored) agents.
  listCustomAgents: () => apiGet<CustomAgent[]>('/v1/ai-agents/custom/'),
  createCustomAgent: (body: CustomAgentInput) =>
    apiPost<CustomAgent, CustomAgentInput>('/v1/ai-agents/custom/', body),
  updateCustomAgent: (id: string, body: CustomAgentInput) =>
    apiPut<CustomAgent, CustomAgentInput>(`/v1/ai-agents/custom/${id}`, body),
  deleteCustomAgent: (id: string) => apiDelete(`/v1/ai-agents/custom/${id}`),

  // Automation: schedule + tools + triggers (Item 29).
  getAgentSchedule: (id: string) =>
    apiGet<AgentMetadata>(`/v1/ai-agents/custom/${id}/schedule`),
  setAgentSchedule: (id: string, body: SetScheduleRequest) =>
    apiPost<AgentMetadata, SetScheduleRequest>(`/v1/ai-agents/custom/${id}/schedule`, body),
  deleteAgentSchedule: (id: string) => apiDelete(`/v1/ai-agents/custom/${id}/schedule`),
  getAgentTools: (id: string) => apiGet<AgentTools>(`/v1/ai-agents/custom/${id}/tools`),
  listGrantableTools: () =>
    apiGet<ToolWithPermission[]>('/v1/ai-agents/grantable-tools/'),
  setAgentTools: (id: string, body: SetToolsRequest) =>
    apiPost<AgentMetadata, SetToolsRequest>(`/v1/ai-agents/custom/${id}/tools`, body),
  listEventTriggers: () =>
    apiGet<EventTriggerDescriptor[]>('/v1/ai-agents/triggers/'),
  setAgentTriggers: (id: string, body: SetTriggersRequest) =>
    apiPost<AgentMetadata, SetTriggersRequest>(`/v1/ai-agents/custom/${id}/triggers`, body),

  // BOQ proposals: extract from a run + apply to a BOQ (human-confirmed).
  getRunProposals: (runId: string) =>
    apiGet<RunProposals>(`/v1/ai-agents/runs/${runId}/proposals`),
  applyRunProposals: (runId: string, body: ApplyProposalsRequest) =>
    apiPost<ApplyProposalsResult, ApplyProposalsRequest>(
      `/v1/ai-agents/runs/${runId}/apply`,
      body,
    ),
  // BOQs the proposals can be applied to (the cross-module target list).
  listProjectBoqs: (projectId: string) =>
    apiGet<BoqOption[]>(`/v1/boq/?project_id=${projectId}`),
};
