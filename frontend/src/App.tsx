import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import InterruptPrompt from "./components/InterruptPrompt";
import {
  createConversation,
  fetchHealth,
  resolveInterrupt,
  resumeStream,
  streamChat,
  type HealthStatus,
  type InterruptPayload,
} from "./api";
import "./App.css";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
};

function uid() {
  return crypto.randomUUID();
}

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState<string>("Connecting…");
  const [interrupt, setInterrupt] = useState<InterruptPayload | null>(null);
  const [resolving, setResolving] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pendingMessageRef = useRef<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, interrupt]);

  const startConversation = useCallback(async () => {
    setError(null);
    setInterrupt(null);
    setStatusLine("Creating thread…");
    try {
      const conv = await createConversation();
      setThreadId(conv.thread_id);
      setAgentId(conv.agent_id);
      setMessages([]);
      setStatusLine(`${health?.runtime ?? "agent"} · ${conv.thread_id.slice(0, 8)}…`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start conversation");
      setStatusLine("Error");
    }
  }, [health?.runtime]);

  useEffect(() => {
    startConversation();
  }, [startConversation]);

  const continueStream = async (message: string, assistantId: string) => {
    if (!threadId) return;
    let accumulated = messages.find((m) => m.id === assistantId)?.content ?? "";

    await streamChat(
      threadId,
      message,
      {
        onToken: (token) => {
          accumulated += token;
          setMessages((m) =>
            m.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: accumulated, streaming: true }
                : msg,
            ),
          );
        },
        onInterrupt: (payload) => {
          setInterrupt(payload);
          setStatusLine("Waiting for approval…");
        },
        onMetadata: (data) => {
          try {
            const meta = JSON.parse(data) as { run_id?: string };
            if (meta.run_id) setStatusLine(`Run ${meta.run_id.slice(0, 8)}…`);
          } catch {
            /* ignore */
          }
        },
        onError: (detail) => setError(detail),
      },
      abortRef.current?.signal,
    );

    setMessages((m) =>
      m.map((msg) =>
        msg.id === assistantId ? { ...msg, streaming: false } : msg,
      ),
    );
    setStatusLine("Ready");
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || !threadId || loading || interrupt) return;

    setInput("");
    setError(null);
    setLoading(true);
    pendingMessageRef.current = text;

    const userMsg: Message = { id: uid(), role: "user", content: text };
    const assistantId = uid();
    setMessages((m) => [
      ...m,
      userMsg,
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setStatusLine("Agent working…");

    try {
      await continueStream(text, assistantId);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Stream failed");
      setMessages((m) => m.filter((msg) => msg.id !== assistantId));
      setStatusLine("Error");
    } finally {
      setLoading(false);
      pendingMessageRef.current = null;
    }
  };

  const handleInterruptDecision = async (approved: boolean) => {
    if (!threadId || !interrupt) return;
    setResolving(true);
    setError(null);
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    try {
      await resolveInterrupt(threadId, approved, agentId ?? undefined);
      setInterrupt(null);
      if (!approved) {
        setStatusLine("Tool call rejected");
        return;
      }
      setStatusLine("Resuming run…");
      if (lastAssistant) {
        let accumulated = lastAssistant.content;
        await resumeStream(
          threadId,
          {
            onToken: (token) => {
              accumulated += token;
              setMessages((m) =>
                m.map((msg) =>
                  msg.id === lastAssistant.id
                    ? { ...msg, content: accumulated, streaming: true }
                    : msg,
                ),
              );
            },
            onInterrupt: (payload) => {
              setInterrupt(payload);
              setStatusLine("Waiting for approval…");
            },
            onError: (detail) => setError(detail),
          },
          abortRef.current?.signal,
        );
        setMessages((m) =>
          m.map((msg) =>
            msg.id === lastAssistant.id ? { ...msg, streaming: false } : msg,
          ),
        );
      }
      setStatusLine("Ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resolve interrupt");
    } finally {
      setResolving(false);
    }
  };

  const ready = health?.ready ?? false;
  const runtimeLabel =
    health?.runtime === "managed"
      ? "Managed Deep Agents"
      : health?.runtime === "deployment"
        ? "LangSmith Deployment"
        : "Local Deep Agents";

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo" aria-hidden>
            ◆
          </span>
          <div>
            <h1>Research Assistant</h1>
            <p className="subtitle">{runtimeLabel}</p>
          </div>
        </div>
        <div className="header-meta">
          <span className={`pill ${ready ? "ok" : "warn"}`}>
            {ready ? health?.runtime ?? "ready" : "Setup required"}
          </span>
          <span className="status">{statusLine}</span>
        </div>
      </header>

      {!ready && (
        <aside className="banner">
          {health?.runtime === "managed" && (
            <p>
              Set <code>LANGSMITH_API_KEY</code> and run{" "}
              <code>make provision</code> for <code>MANAGED_AGENT_ID</code>.
            </p>
          )}
          {health?.runtime === "deployment" && (
            <p>
              Set <code>LANGGRAPH_DEPLOYMENT_URL</code> and{" "}
              <code>LANGGRAPH_ASSISTANT_ID</code> (deploy with{" "}
              <code>langgraph up</code>).
            </p>
          )}
          {health?.runtime === "local" && (
            <p>
              Local mode uses open-source <code>deepagents</code>. Set{" "}
              <code>ANTHROPIC_API_KEY</code> or <code>OPENAI_API_KEY</code> for
              the model in <code>DEFAULT_MODEL</code>.
            </p>
          )}
        </aside>
      )}

      {error && (
        <div className="error-bar" role="alert">
          {error}
        </div>
      )}

      <main className="chat">
        {messages.length === 0 && (
          <div className="empty">
            <h2>Ask anything</h2>
            <p>
              Web search may require approval (human-in-the-loop). Managed mode
              uses Fleet MCP tools; local mode uses a stub search tool.
            </p>
            <ul>
              <li>What are the main tradeoffs in agent memory systems?</li>
              <li>Summarize LangGraph durable execution</li>
              <li>Compare RAG vs long-context for enterprise search</li>
            </ul>
          </div>
        )}

        {messages.map((msg) => (
          <article
            key={msg.id}
            className={`bubble ${msg.role}${msg.streaming ? " streaming" : ""}`}
          >
            <span className="role-label">
              {msg.role === "user" ? "You" : "Agent"}
            </span>
            {msg.role === "assistant" ? (
              <ReactMarkdown>{msg.content || "…"}</ReactMarkdown>
            ) : (
              <p>{msg.content}</p>
            )}
          </article>
        ))}
        <div ref={bottomRef} />
      </main>

      {interrupt && (
        <InterruptPrompt
          interrupt={interrupt}
          onApprove={() => handleInterruptDecision(true)}
          onReject={() => handleInterruptDecision(false)}
          busy={resolving}
        />
      )}

      <footer className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
          placeholder="Ask a research question…"
          rows={2}
          disabled={!threadId || loading || !ready || !!interrupt}
        />
        <div className="composer-actions">
          <button
            type="button"
            className="secondary"
            onClick={startConversation}
            disabled={loading || resolving}
          >
            New thread
          </button>
          <button
            type="button"
            className="primary"
            onClick={sendMessage}
            disabled={
              !threadId || loading || !input.trim() || !ready || !!interrupt
            }
          >
            {loading ? "Running…" : "Send"}
          </button>
        </div>
      </footer>
    </div>
  );
}
