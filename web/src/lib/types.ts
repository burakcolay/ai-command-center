export type TaskStatus =
  | "planning"
  | "waiting_approval"
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type Decision = "approve" | "reject" | "request_changes" | "cancel" | "retry" | "fix_checks" | "rerun_checks" | "undo_last";

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
  mode: ComposerMode;
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
}

export interface Project {
  id: number;
  name: string;
  path: string;
  checks: ChecksConfig | null;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  project_id: number | null;
  created_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: "user" | "assistant" | "task";
  content: string;
  status: "streaming" | "done" | "error" | "cancelled";
  adapter_id: string | null;
  meta: {
    kind?: "research" | "design";
    report_path?: string;
    attachments?: string[];
    variants?: DesignVariant[];
    viewport?: "phone" | "tablet" | "desktop";
  } | null;
  task_id: number | null;
  created_at: string;
}

export interface PlanStep {
  id: string;
  title: string;
  agent: string;
  description: string;
  depends_on: string[];
  writes_files: boolean;
}

export interface Plan {
  title: string;
  summary: string;
  steps: PlanStep[];
  risks: string[];
}

export type TaskStage = "plan" | "execute" | "merge" | "done";

export interface TaskStepState {
  id: number;
  step_id: string;
  seq: number;
  title: string;
  agent: string;
  description: string;
  kind: "plan" | "revision" | "edit";
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
  plan: Plan | null;
  adapter_id: string | null;
  error: string | null;
  stage: TaskStage;
  branch: string | null;
  base_branch: string | null;
  merged_commit: string | null;
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

export interface Agent {
  id: string;
  name: string;
  description: string;
  tools: string[];
  adapters: string[];
  writes_files: boolean;
}

export type ComposerMode = "chat" | "research" | "design" | "edit" | "task";

export interface DesignVariant {
  n: number;
  title: string;
  idea: string;
  image: string | null;
  attachment: string;
}

export type WsMessage =
  | { type: "message"; message: Message }
  | { type: "message_delta"; message_id: number; text: string }
  | { type: "message_activity"; message_id: number; tool: { name: string; input?: unknown } }
  | { type: "task"; task: Task }
  | { type: "event"; event: TaskEvent }
  | { type: "approvals_changed" };
