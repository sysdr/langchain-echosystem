const API_BASE = "/api";

export type HealthStatus = {
  status: string;
  runtime: string;
  runtime_active: string;
  ready: boolean;
  api_key_configured: boolean;
  managed_agent_id_configured: boolean;
  deployment_configured: boolean;
  hitl_enabled: boolean;
  deepagents_base_url?: string;
  model?: string;
  note?: string;
};

export type Conversation = {
  thread_id: string;
  agent_id: string;
};

export type InterruptPayload = {
  tool: string;
  description: string;
  interrupt_id?: string | null;
};

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function createConversation(): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/conversations`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ??
        `Failed to create conversation (${res.status})`,
    );
  }
  return res.json();
}

export async function resolveInterrupt(
  threadId: string,
  approved: boolean,
  agentId?: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/resolve-interrupt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      thread_id: threadId,
      approved,
      agent_id: agentId ?? undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ??
        `Failed to resolve interrupt (${res.status})`,
    );
  }
}

export type StreamHandlers = {
  onToken: (text: string) => void;
  onInterrupt?: (payload: InterruptPayload) => void;
  onMetadata?: (data: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

async function consumeSse(
  res: Response,
  handlers: StreamHandlers,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      if (!block.trim()) continue;

      let event = currentEvent;
      let data = "";

      for (const line of block.split("\n")) {
        const trimmed = line.trim();
        if (trimmed.startsWith("event:")) {
          event = trimmed.slice(6).trim();
          currentEvent = event;
        } else if (trimmed.startsWith("data:")) {
          data += trimmed.slice(5).trim();
        }
      }

      if (event === "token") {
        try {
          const parsed = JSON.parse(data) as { text?: string };
          if (parsed.text) handlers.onToken(parsed.text);
        } catch {
          /* ignore */
        }
      } else if (event === "interrupt" && handlers.onInterrupt) {
        try {
          handlers.onInterrupt(JSON.parse(data) as InterruptPayload);
        } catch {
          handlers.onError?.("Invalid interrupt payload");
        }
      } else if (event === "metadata" && handlers.onMetadata) {
        handlers.onMetadata(data);
      } else if (event === "done" && handlers.onDone) {
        handlers.onDone();
      } else if (event === "error") {
        try {
          const parsed = JSON.parse(data) as { detail?: string };
          handlers.onError?.(parsed.detail ?? data);
        } catch {
          handlers.onError?.(data);
        }
      }
    }
  }

  handlers.onDone?.();
}

export async function resumeStream(
  threadId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/resume-stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      thread_id: threadId,
      user_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ??
        `Resume stream failed (${res.status})`,
    );
  }

  await consumeSse(res, handlers);
}

export async function streamChat(
  threadId: string,
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      thread_id: threadId,
      message,
      user_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Stream failed (${res.status})`,
    );
  }

  await consumeSse(res, handlers);
}
