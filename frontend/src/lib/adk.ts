/**
 * Typed client for the ADK server (google-adk 2.x).
 *
 * ADK's Pydantic models use `alias_generator=to_camel` with `populate_by_name`,
 * so requests and responses are both camelCase — no snake_case mapping needed.
 *
 * The one sharp edge: `/run_sse` is a **POST** that returns `text/event-stream`.
 * The browser's `EventSource` can only issue GETs, so we stream it by hand with
 * fetch + a ReadableStream reader. That is also why there is no SSE library
 * here — the parser below is the whole thing.
 */

/** A single part of a message: text, a file, or a tool call/result. */
export interface Part {
  text?: string;
  inlineData?: { mimeType: string; data: string }; // data is base64
  functionCall?: { name: string; args?: Record<string, unknown> };
  functionResponse?: { name: string; response?: Record<string, unknown> };
}

export interface Content {
  role: "user" | "model";
  parts: Part[];
}

/** What `/run_sse` streams back. Only the fields the UI actually reads. */
export interface AdkEvent {
  id?: string;
  author?: string; // "orchestrator" | "form_reader" | "data_collector"
  content?: Content;
  /** True for incremental text chunks; the final event for a turn omits it. */
  partial?: boolean;
  turnComplete?: boolean;
  errorMessage?: string;
  actions?: {
    /** filename -> version. How a generated PDF announces itself. */
    artifactDelta?: Record<string, number>;
    transferToAgent?: string;
  };
}

export interface UiConfig {
  appName: string;
  model: string;
  piiRedaction: boolean;
}

export interface SecurityEvent {
  id: number;
  event: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  ts: string;
  details: Record<string, unknown>;
}

export interface SecuritySnapshot {
  events: SecurityEvent[];
  cursor: number;
  checksPassed: number;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function getConfig(): Promise<UiConfig> {
  return json(await fetch("/api/config"));
}

export async function getSecurity(cursor: number): Promise<SecuritySnapshot> {
  return json(await fetch(`/api/security?cursor=${cursor}`));
}

/** Create a session. ADK generates the id when we don't supply one. */
export async function createSession(
  appName: string,
  userId: string,
): Promise<{ id: string }> {
  return json(
    await fetch(`/apps/${appName}/users/${userId}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }),
  );
}

/**
 * Fetch a generated artifact (the filled PDF) and return it as a blob URL.
 *
 * ADK returns the artifact as a `types.Part` — i.e. base64 inside `inlineData`,
 * not raw bytes — so we decode it here. Browsers render PDFs natively, which is
 * why this app ships no pdf.js: a blob URL in an <iframe> is the whole viewer,
 * and it saves ~1MB of JavaScript.
 */
export async function loadArtifact(
  appName: string,
  userId: string,
  sessionId: string,
  filename: string,
): Promise<{ url: string; mimeType: string }> {
  const part = await json<Part>(
    await fetch(
      `/apps/${appName}/users/${userId}/sessions/${sessionId}/artifacts/${encodeURIComponent(filename)}`,
    ),
  );
  const inline = part.inlineData;
  if (!inline?.data) throw new Error(`Artifact ${filename} has no data`);

  const bytes = base64ToBytes(inline.data);
  const blob = new Blob([bytes], { type: inline.mimeType });
  return { url: URL.createObjectURL(blob), mimeType: inline.mimeType };
}

/**
 * Decode the artifact payload to bytes.
 *
 * ADK/genai serialises the artifact bytes as **base64url** — the URL-safe variant
 * that uses `-` and `_` in place of `+` and `/`. The browser's `atob` only accepts
 * STANDARD base64 and throws `InvalidCharacterError` on the first `-`/`_`, so the
 * raw string must be normalised first. This was the reason the download card never
 * appeared: the decode threw and the artifact was silently dropped.
 */
function base64ToBytes(data: string) {
  let s = data.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4;
  if (pad) s += "=".repeat(4 - pad); // restore padding if it was stripped
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

/** Read a File as the bare base64 payload ADK's inlineData expects. */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    // result is a data: URL — strip the "data:<mime>;base64," prefix.
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/**
 * POST to /run_sse and yield each ADK event as it arrives.
 *
 * Buffers across chunk boundaries: a network chunk can split an SSE frame in
 * half, so we only parse up to the last complete `\n\n` and keep the remainder.
 */
export async function* runSSE(
  body: {
    appName: string;
    userId: string;
    sessionId: string;
    newMessage: Content;
  },
  signal?: AbortSignal,
): AsyncGenerator<AdkEvent> {
  const res = await fetch("/run_sse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, streaming: true }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Agent request failed: ${res.status} ${await res.text()}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;

      // SSE frames are separated by a blank line. Anything after the last one
      // is a partial frame — leave it in the buffer for the next chunk.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          try {
            yield JSON.parse(payload) as AdkEvent;
          } catch {
            // A malformed frame must not kill the stream; skip it.
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
