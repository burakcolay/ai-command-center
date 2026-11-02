export type TaskStatus =
  | "planning"
  | "waiting_approval"
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type Decision = "approve" | "reject" | "undo_last" | "rerun_checks" | "open_pr";

export interface CheckCommand {
  name: string;
  command: string;
}

export interface ChecksConfig {
  setup: string | null;
  commands: CheckCommand[];
}

export interface ChecksInfo {
  configured: ChecksConfig | null;
  detected: ChecksConfig;
  effective: ChecksConfig;
  sandbox: boolean;
}

export interface CheckResult extends CheckCommand {
  status: "passed" | "failed" | "skipped";
  exit_code?: number | null;
  timed_out?: boolean;
  duration_ms?: number;
  output?: string;
}

export interface Template {
  id: string;
  title: string;
  body: string;
  description: string;
  custom: boolean;
}

export interface SystemInfo {
  demo_mode: boolean;
  paid_api_allowed: boolean;
  notifications: boolean;
  notifications_supported: boolean;
  sandbox_for_checks: boolean;
  memory_dir: string;
  quality: "economy" | "balanced" | "best";
  claude_model: "default" | "sonnet" | "opus" | "fable";
  /** quality -> role -> tier, effort and the Claude / Codex model it maps to. */
  plan: Record<
    string,
    Record<string, { tier: string; effort: string; claude: string; codex: string }>
  >;
}

export interface Project {
  id: number;
  name: string;
  path: string;
  checks: ChecksConfig | null;
  created_at: string;
}

/** "auto" or "<provider>/<model id>", e.g. "codex/gpt-6.1-sol". */
export type ModelChoice = string;

export interface CatalogModel {
  id: string;
  label: string;
  efforts: string[];
  effort: string;
  note: string;
}

export interface CatalogProvider {
  id: string;
  name: string;
  available: boolean;
  reason: string;
  note: string;
  models: CatalogModel[];
}

export interface Chat {
  id: number;
  title: string;
  project_id: number | null;
  model_choice: ModelChoice;
  effort_choice: string | null;
  created_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  /** "task" only appears in chats from before Orbit had a single assistant. */
  role: "user" | "assistant" | "task";
  content: string;
  status: "streaming" | "done" | "error" | "cancelled" | "waiting";
  adapter_id: string | null;
  meta: {
    attachments?: string[];
    /** What each attachment is (image, text file such as a spec, or a picked design). */
    files?: { id: string; kind: "image" | "text" | "design"; name: string }[];
    /** Designs the assistant drew in this turn. */
    variants?: DesignVariant[];
    /** Reports it wrote, saved as markdown next to project memory. */
    reports?: string[];
    /** This turn changed the project: the session (task) holding the change. */
    task_id?: number;
    /** Waiting for the quota reset (unix seconds). */
    resume_at?: number;
    /** The team that worked on this turn (lead, subagents, Codex, reviewer). */
    team?: TeamPicture;
    /** Independent review of this turn's change by another model (or a separate session). */
    review?: {
      by: string;
      summary: string;
      issues: { onem: string; dosya: string; sorun: string; oneri: string }[];
      fixed: boolean;
    };
  } | null;
  task_id: number | null;
  created_at: string;
}

export type TaskStage = "plan" | "execute" | "merge" | "done";

export interface TaskStepState {
  id: number;
  step_id: string;
  seq: number;
  title: string;
  agent: string;
  description: string;
  kind: string;
  status: "pending" | "running" | "done" | "failed" | "reverted";
  summary: string | null;
  commit: string | null;
  adapter_id: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DiffFile {
  path: string;
  added: number;
  removed: number;
  binary: boolean;
}

export interface TaskDiff {
  files: DiffFile[];
  patch: string;
  truncated: boolean;
  branch: string;
}

export interface Task {
  id: number;
  chat_id: number;
  project_id: number | null;
  title: string;
  request: string;
  status: TaskStatus;
  kind: "plan" | "session";
  adapter_id: string | null;
  error: string | null;
  stage: TaskStage;
  branch: string | null;
  base_branch: string | null;
  merged_commit: string | null;
  pr_url: string | null;
  checks: CheckResult[] | null;
  resume_at: string | null;
  steps: TaskStepState[];
  created_at: string;
  updated_at: string;
}

export interface TaskEvent {
  id: number;
  task_id: number;
  kind: "text" | "tool" | "log" | "usage" | "error";
  data: Record<string, unknown>;
  created_at: string;
}

export interface ProjectCard {
  content: string | null;
  state: "pending" | "merged" | null;
  team: { name: string; tech: string; folder: string; builder: "claude" | "codex" }[];
}

export type TeamStatus = "running" | "done" | "failed";

export interface TeamMember {
  id: string;
  agent: string;
  label: string;
  vendor: string;
  model: string;
  actual: string;
  effort: string;
  status: TeamStatus;
  task: string;
  activity: string;
  tokens: number;
  tools: number;
  parent?: string;
}

/** Who worked on a turn, on which model and effort, and the tokens it took. */
export interface TeamPicture {
  lead: {
    label: string;
    vendor: string;
    model: string;
    actual: string;
    effort: string;
    status: TeamStatus;
    activity: string;
  };
  members: TeamMember[];
  usage: Record<string, { input: number; output: number; cached: number }>;
}

export interface GitHubStatus {
  repo: string | null;
  ready: boolean;
  reason: string;
}

export interface Approval {
  id: number;
  task_id: number;
  kind: string;
  status: string;
  note: string | null;
  created_at: string;
  decided_at: string | null;
  task: Task;
}

export interface UsageWindow {
  name: string;
  utilization: number | null;
  resets_at: number | null;
  status: string | null;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  billing: "subscription" | "local_free" | "free_tier" | "paid_api";
  auth_method: string;
  requires_membership: boolean;
  requires_api_key: boolean;
  notes: string;
  capabilities: Record<string, boolean>;
  state: string;
  detail: string;
  data: {
    models?: { name: string; size_gb: number; params: string | null; quant: string | null }[];
    selected?: string;
  };
  usage: {
    source: "verified" | "estimated" | "user" | "unknown";
    detail: string;
    observed_at: number | null;
    windows: UsageWindow[];
  };
}

export interface WorkRoute {
  id: string;
  label: string;
  description: string;
  order: string[];
  override: string;
  candidates: { id: string; name: string; eligible: boolean }[];
  current: string | null;
  current_name: string | null;
  reason: string;
}

export interface DesignVariant {
  n: number;
  title: string;
  idea: string;
  viewport: "phone" | "tablet" | "desktop";
  image: string | null;
  attachment: string;
}

export type WsMessage =
  | { type: "message"; message: Message }
  | { type: "message_delta"; message_id: number; text: string }
  | {
      type: "message_activity";
      message_id: number;
      tool: { name: string; input?: unknown; agent?: string };
    }
  | { type: "team"; message_id: number; team: TeamPicture }
  | { type: "task"; task: Task }
  | { type: "event"; event: TaskEvent }
  | { type: "approvals_changed" };
