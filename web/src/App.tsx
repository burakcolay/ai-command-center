import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { OrbitMark } from "./components/DotMatrix";
import { Sidebar } from "./components/Sidebar";
import { useSocket } from "./hooks/useSocket";
import { api } from "./lib/api";
import { NAV_ITEMS, type ViewId } from "./lib/nav";
import type {
  Agent,
  Approval,
  Chat,
  ComposerMode,
  Message,
  ModelInfo,
  Project,
  Task,
  TaskEvent,
  WsMessage,
} from "./lib/types";
import { ChatView, activityText } from "./views/ChatView";
import { ModelsView } from "./views/ModelsView";
import { AgentsView, ApprovalsView, ComingSoon, SettingsView } from "./views/OtherViews";
import { ProjectsView } from "./views/ProjectsView";

export default function App() {
  const [view, setView] = useState<ViewId>("chat");
  const [chatId, setChatId] = useState<number | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Record<number, Task>>({});
  const [events, setEvents] = useState<Record<number, TaskEvent[]>>({});
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [demoMode, setDemoMode] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [mode, setMode] = useState<ComposerMode>("chat");
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [activity, setActivity] = useState<Record<number, string>>({});
  const chatIdRef = useRef(chatId);
  chatIdRef.current = chatId;

  const showError = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 5000);
  }, []);

  const loadChats = useCallback(() => api.chats().then(setChats).catch(() => {}), []);
  const loadProjects = useCallback(() => api.projects().then(setProjects).catch(() => {}), []);
  const loadApprovals = useCallback(() => api.approvals().then(setApprovals).catch(() => {}), []);
  const loadModels = useCallback(
    (fresh = false) => api.models(fresh).then(setModels).catch(() => {}),
    [],
  );

  const openChat = useCallback(async (id: number) => {
    const data = await api.chat(id);
    setChatId(id);
    setMessages(data.messages);
    setTasks((prev) => ({ ...prev, ...Object.fromEntries(data.tasks.map((t) => [t.id, t])) }));
    setProjectId(data.chat.project_id);
    setView("chat");
    setMenuOpen(false);
  }, []);

  const loadAll = useCallback(() => {
    void loadChats();
    void loadProjects();
    void loadApprovals();
    void loadModels();
    if (chatIdRef.current) void openChat(chatIdRef.current).catch(() => {});
  }, [loadChats, loadProjects, loadApprovals, loadModels, openChat]);

  useEffect(() => {
    loadAll();
    api.agents().then(setAgents).catch(() => {});
    api.system().then((s) => setDemoMode(s.demo_mode)).catch(() => {});
  }, [loadAll]);

  const connected = useSocket((m: WsMessage) => {
    if (m.type === "message") {
      const msg = m.message;
      if (msg.chat_id !== chatIdRef.current) return;
      setMessages((prev) =>
        prev.some((x) => x.id === msg.id) ? prev.map((x) => (x.id === msg.id ? msg : x)) : [...prev, msg],
      );
      setActivity(({ [msg.id]: _, ...rest }) => rest);
    } else if (m.type === "message_delta") {
      setMessages((prev) =>
        prev.map((x) =>
          x.id === m.message_id && x.status === "streaming" ? { ...x, content: x.content + m.text } : x,
        ),
      );
      setActivity(({ [m.message_id]: _, ...rest }) => rest);
    } else if (m.type === "message_activity") {
      setActivity((prev) => ({ ...prev, [m.message_id]: activityText(m.tool) }));
    } else if (m.type === "task") {
      setTasks((prev) => ({ ...prev, [m.task.id]: m.task }));
    } else if (m.type === "event") {
      const e = m.event;
      setEvents((prev) => (prev[e.task_id] ? { ...prev, [e.task_id]: [...prev[e.task_id], e] } : prev));
      if (e.kind === "usage") void loadModels();
    } else if (m.type === "approvals_changed") {
      void loadApprovals();
    }
  }, loadAll);

  const loadEvents = useCallback((taskId: number) => {
    setEvents((prev) => (prev[taskId] ? prev : { ...prev, [taskId]: [] }));
    api
      .events(taskId)
      .then((list) => setEvents((prev) => ({ ...prev, [taskId]: list })))
      .catch(() => {});
  }, []);

  const send = async (text: string) => {
    try {
      let id = chatId;
      if (id === null) {
        id = (await api.createChat(projectId)).id;
        setChatId(id);
        setMessages([]);
      }
      const r = await api.send(id, text, projectId, mode, chatModel);
      setMessages((prev) => [...prev, ...r.messages.filter((x) => !prev.some((y) => y.id === x.id))]);
      const task = r.task;
      if (task) setTasks((prev) => ({ ...prev, [task.id]: task }));
      void loadChats();
    } catch (e) {
      showError((e as Error).message);
      throw e;
    }
  };

  const stop = (messageId: number) => {
    api.cancelMessage(messageId).catch((e) => showError(e.message));
  };

  const newChat = () => {
    setChatId(null);
    setMessages([]);
    setView("chat");
    setMenuOpen(false);
  };

  const deleteChat = async (id: number) => {
    await api.removeChat(id).catch((e) => showError(e.message));
    if (id === chatId) newChat();
    void loadChats();
  };

  const navigate = (v: ViewId) => {
    setView(v);
    setMenuOpen(false);
    if (v === "approvals") void loadApprovals();
    if (v === "models") void loadModels();
  };

  const navItem = NAV_ITEMS.find((n) => n.id === view);
  const ollama = models.find((m) => m.id === "ollama" && m.state === "available");
  const chatModels = [
    { id: null, label: "Claude" },
    ...(ollama ? [{ id: "ollama", label: `Yerel · ${ollama.data.selected}` }] : []),
  ];

  return (
    <div className="flex h-full">
      <Sidebar
        view={view}
        chatId={chatId}
        chats={chats}
        models={models}
        pendingApprovals={approvals.length}
        connected={connected}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onNavigate={navigate}
        onOpenChat={(id) => void openChat(id).catch((e) => showError(e.message))}
        onNewChat={newChat}
        onDeleteChat={(id) => void deleteChat(id)}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-3 border-b border-line px-4 md:hidden">
          <button onClick={() => setMenuOpen(true)} aria-label="Menü" className="text-dim">
            <Menu size={18} />
          </button>
          <OrbitMark size={16} />
          <span className="font-mono text-[12px] tracking-[0.32em]">ORBIT</span>
        </div>

        <div className="min-h-0 flex-1">
          {view === "chat" && (
            <ChatView
              messages={messages}
              tasks={tasks}
              events={events}
              projects={projects}
              projectId={projectId}
              mode={mode}
              chatModels={chatModels}
              chatModel={ollama ? chatModel : null}
              onChatModelChange={setChatModel}
              activity={activity}
              demoMode={demoMode}
              onModeChange={setMode}
              onProjectChange={setProjectId}
              onSend={send}
              onStop={stop}
              onLoadEvents={loadEvents}
              onError={showError}
            />
          )}
          {view === "projects" && (
            <ProjectsView
              projects={projects}
              onChanged={loadProjects}
              onError={showError}
              onOpen={(p) => {
                newChat();
                setProjectId(p.id);
              }}
            />
          )}
          {view === "approvals" && (
            <ApprovalsView
              approvals={approvals}
              onOpenTask={(id) => void openChat(id).catch((e) => showError(e.message))}
            />
          )}
          {view === "agents" && <AgentsView agents={agents} />}
          {view === "models" && (
            <ModelsView models={models} onRefresh={() => loadModels(true)} onError={showError} />
          )}
          {view === "settings" && <SettingsView demoMode={demoMode} />}
          {navItem?.phase && <ComingSoon item={navItem} />}
        </div>

        {toast && (
          <div
            role="alert"
            className="absolute bottom-24 left-1/2 z-50 max-w-[90%] -translate-x-1/2 animate-rise rounded-lg border border-danger/40 bg-panel px-4 py-2 text-[13px] text-danger shadow-2xl"
          >
            {toast}
          </div>
        )}
      </main>
    </div>
  );
}
