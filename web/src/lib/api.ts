import type {
  Agent,
  Approval,
  Chat,
  Decision,
  Message,
  ChecksConfig,
  ChecksInfo,
  ComposerMode,
  ModelInfo,
  Project,
  SystemInfo,
  Task,
  TaskDiff,
  TaskEvent,
  Template,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Hata ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = <T>(path: string, body: unknown) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  projects: () => req<Project[]>("/projects"),
  createProject: (name: string, path?: string) =>
    post<Project>("/projects", { name, path: path || null }),
  removeProject: (id: number) => req<void>(`/projects/${id}`, { method: "DELETE" }),
  memory: (id: number) => req<{ path: string; content: string }>(`/projects/${id}/memory`),
  saveMemory: (id: number, content: string) =>
    req<{ path: string; content: string }>(`/projects/${id}/memory`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  checks: (id: number) => req<ChecksInfo>(`/projects/${id}/checks`),
  saveChecks: (id: number, config: ChecksConfig | null) =>
    req<ChecksInfo>(`/projects/${id}/checks`, { method: "PUT", body: JSON.stringify({ config }) }),
  templates: () => req<Template[]>("/templates"),
  createTemplate: (title: string, body: string, mode: ComposerMode) =>
    post<{ id: string }>("/templates", { title, body, mode }),
  deleteTemplate: (id: string) => req<void>(`/templates/${id}`, { method: "DELETE" }),
  testNotification: () => post<{ sent: boolean }>("/notify/test", {}),
  setPreference: (key: string, value: string | boolean) =>
    req<unknown>(`/preferences/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),

  chats: () => req<Chat[]>("/chats"),
  createChat: (project_id: number | null) => post<Chat>("/chats", { project_id }),
  chat: (id: number) => req<{ chat: Chat; messages: Message[]; tasks: Task[] }>(`/chats/${id}`),
  removeChat: (id: number) => req<void>(`/chats/${id}`, { method: "DELETE" }),
  send: (
    chatId: number,
    content: string,
    project_id: number | null,
    mode: ComposerMode,
    model: string | null,
  ) =>
    post<{ chat: Chat; messages: Message[]; task: Task | null }>(`/chats/${chatId}/messages`, {
      content,
      project_id,
      mode,
      model: mode === "chat" ? model : null,
    }),
  cancelMessage: (id: number) => post<Message>(`/messages/${id}/cancel`, {}),

  diff: (taskId: number) => req<TaskDiff>(`/tasks/${taskId}/diff`),
  events: (taskId: number) => req<TaskEvent[]>(`/tasks/${taskId}/events`),
  decide: (taskId: number, decision: Decision, note?: string) =>
    post<Task>(`/tasks/${taskId}/decision`, { decision, note: note || null }),
  approvals: () => req<Approval[]>("/approvals"),

  models: (fresh = false) => req<ModelInfo[]>(`/models${fresh ? "?fresh=true" : ""}`),
  agents: () => req<Agent[]>("/agents"),
  system: () => req<SystemInfo>("/system"),
};
