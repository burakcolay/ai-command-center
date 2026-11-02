import type {
  Approval,
  Chat,
  Decision,
  Message,
  ChecksConfig,
  ChecksInfo,
  ModelInfo,
  Project,
  SystemInfo,
  Task,
  TaskDiff,
  TaskEvent,
  Template,
  WorkRoute,
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
  createTemplate: (title: string, body: string) =>
    post<{ id: string }>("/templates", { title, body }),
  deleteTemplate: (id: string) => req<void>(`/templates/${id}`, { method: "DELETE" }),
  testNotification: () => post<{ sent: boolean }>("/notify/test", {}),
  setPreference: (key: string, value: string | boolean) =>
    req<unknown>(`/preferences/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),

  chats: () => req<Chat[]>("/chats"),
  createChat: (project_id: number | null) => post<Chat>("/chats", { project_id }),
  chat: (id: number) => req<{ chat: Chat; messages: Message[]; tasks: Task[] }>(`/chats/${id}`),
  removeChat: (id: number) => req<void>(`/chats/${id}`, { method: "DELETE" }),
  send: (chatId: number, content: string, project_id: number | null, attachments: string[]) =>
    post<{ chat: Chat; messages: Message[] }>(`/chats/${chatId}/messages`, {
      content,
      project_id,
      attachments,
    }),
  upload: (name: string, data: string) =>
    post<{ id: string; name: string; mime: string }>("/uploads", { name, data }),
  cancelMessage: (id: number) => post<Message>(`/messages/${id}/cancel`, {}),
  resumeMessage: (id: number) => post<{ ok: boolean }>(`/messages/${id}/resume`, {}),

  diff: (taskId: number) => req<TaskDiff>(`/tasks/${taskId}/diff`),
  events: (taskId: number) => req<TaskEvent[]>(`/tasks/${taskId}/events`),
  decide: (taskId: number, decision: Decision) =>
    post<Task>(`/tasks/${taskId}/decision`, { decision }),
  approvals: () => req<Approval[]>("/approvals"),

  models: (fresh = false) => req<ModelInfo[]>(`/models${fresh ? "?fresh=true" : ""}`),
  routing: () => req<WorkRoute[]>("/routing"),
  setRoute: (kind: string, adapter: string) =>
    req<WorkRoute[]>(`/routing/${kind}`, { method: "PUT", body: JSON.stringify({ adapter }) }),
  system: () => req<SystemInfo>("/system"),
};
