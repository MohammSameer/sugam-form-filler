import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  fileToBase64,
  getConfig,
  loadArtifact,
  runSSE,
  type AdkEvent,
  type Content,
  type Part,
} from "@/lib/adk";
import { dict, languageDirective } from "@/lib/i18n";
import { userId } from "@/lib/utils";

export interface Attachment {
  name: string;
  mimeType: string;
  /** Object URL for a local preview of what the user uploaded. */
  url: string;
}

export interface Message {
  id: string;
  role: "user" | "agent";
  /** Which sub-agent spoke: orchestrator | form_reader | data_collector. */
  author?: string;
  text: string;
  attachment?: Attachment;
}

export interface Artifact {
  filename: string;
  url: string;
  mimeType: string;
}

/**
 * The user's progress, derived only from events the agent actually emits.
 *
 * There is deliberately no "field 3 of 9" counter: the agent collects details
 * conversationally and never exposes a structured tally, so such a number would
 * be invented. Each stage below is backed by a real signal.
 */
export type Stage = "start" | "reading" | "collecting" | "ready";

/** Tool name -> what the user should understand is happening right now. */
const TOOL_LABELS: Record<string, string> = {
  parse_form_fields: "readingForm",
  research_form_fields: "readingForm",
  lookup_govt_scheme: "readingForm",
  research_govt_scheme: "readingForm",
  generate_filled_pdf: "thinking",
  fill_uploaded_pdf: "thinking",
  deliver_pdf_for_download: "thinking",
};

interface Ids {
  appName: string;
  sessionId: string;
}

/** `quota` is worth its own state: it is transient and the fix is "wait", not "retry now". */
export type ErrorKind = "quota" | "generic";

export interface AgentError {
  kind: ErrorKind;
  /** The raw message, for a details disclosure — never the primary text. */
  detail: string;
}

/** Gemini returns 429 RESOURCE_EXHAUSTED when the free-tier quota is spent. */
function classify(message: string): ErrorKind {
  return /429|RESOURCE_EXHAUSTED|quota|rate limit/i.test(message)
    ? "quota"
    : "generic";
}

export function useAgent(langCode: string) {
  const [appName, setAppName] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [uploaded, setUploaded] = useState<Attachment | null>(null);
  const [stage, setStage] = useState<Stage>("start");
  const [error, setError] = useState<AgentError | null>(null);

  const uid = useRef(userId());
  const abort = useRef<AbortController | null>(null);
  // The last turn we sent, so a failed one (a 429, a dropped connection) can be
  // replayed without the user retyping it.
  const lastParts = useRef<Part[] | null>(null);
  // The language directive rides along on the first real turn only.
  const langSent = useRef(false);
  // Every object URL we mint is revoked on unmount; otherwise each upload and
  // each generated PDF leaks a blob for the lifetime of the tab.
  const objectUrls = useRef<string[]>([]);

  useEffect(() => {
    const urls = objectUrls;
    const controller = abort;
    return () => {
      controller.current?.abort();
      urls.current.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  /** Pull the non-text signals out of an event: transfers, tool calls, artifacts. */
  const applySideEffects = useCallback((ev: AdkEvent, ids: Ids) => {
    if (ev.author) setActiveAgent(ev.author);
    if (ev.author === "form_reader") setStage("reading");
    if (ev.author === "data_collector") setStage("collecting");

    const transfer = ev.actions?.transferToAgent;
    if (transfer === "form_reader") setStage("reading");
    if (transfer === "data_collector") setStage("collecting");

    for (const p of ev.content?.parts ?? []) {
      const call = p.functionCall?.name;
      if (call) setActivity(TOOL_LABELS[call] ?? "thinking");
    }

    // A generated PDF announces itself here, not in the message text.
    const delta = ev.actions?.artifactDelta;
    if (!delta) return;

    for (const filename of Object.keys(delta)) {
      loadArtifact(ids.appName, uid.current, ids.sessionId, filename)
        .then(({ url, mimeType }) => {
          objectUrls.current.push(url);
          setArtifacts((a) =>
            a.some((x) => x.filename === filename)
              ? a
              : [...a, { filename, url, mimeType }],
          );
          setStage("ready");
        })
        .catch((err) => {
          // The agent's own message still tells the user the PDF is ready —
          // a failed preview must not break the turn — but do not swallow the
          // reason silently: a genuine load failure here means no download card,
          // and that must be diagnosable rather than invisible.
          console.error(`Artifact "${filename}" failed to load:`, err);
        });
    }
  }, []);

  /** Drive one turn: send `parts`, stream the reply into `messages`. */
  const stream = useCallback(
    async (ids: Ids, parts: Part[], showUser?: Message) => {
      if (showUser) setMessages((m) => [...m, showUser]);

      lastParts.current = parts; // so retry() can replay this exact turn
      setBusy(true);
      setError(null);
      setActivity("thinking");

      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;

      const newMessage: Content = { role: "user", parts };

      // The agent message currently being streamed into. `sealed` marks one the
      // agent finished, so a later utterance from the same author opens a fresh
      // bubble instead of overwriting the finished one.
      let open: { id: string; author?: string; sealed: boolean } | null = null;

      try {
        for await (const ev of runSSE(
          {
            appName: ids.appName,
            userId: uid.current,
            sessionId: ids.sessionId,
            newMessage,
          },
          controller.signal,
        )) {
          if (ev.errorMessage) throw new Error(ev.errorMessage);
          applySideEffects(ev, ids);

          const text = (ev.content?.parts ?? []).map((p) => p.text ?? "").join("");
          if (!text) continue;

          if (!open || open.author !== ev.author || open.sealed) {
            open = { id: crypto.randomUUID(), author: ev.author, sealed: false };
            const msg: Message = {
              id: open.id,
              role: "agent",
              author: ev.author,
              text,
            };
            setMessages((m) => [...m, msg]);
          } else {
            const id = open.id;
            // A partial event carries a delta; a final event carries the whole
            // text and is authoritative, so it replaces rather than appends.
            const isPartial = ev.partial === true;
            setMessages((m) =>
              m.map((x) =>
                x.id === id ? { ...x, text: isPartial ? x.text + text : text } : x,
              ),
            );
          }

          if (ev.partial !== true) open.sealed = true;
        }
      } catch (e) {
        const err = e as Error;
        if (err.name !== "AbortError") {
          setError({ kind: classify(err.message), detail: err.message });
        }
      } finally {
        setBusy(false);
        setActivity(null);
      }
    },
    [applySideEffects],
  );

  /** Read config, open a session. Returns the ids so callers can proceed at once. */
  const boot = useCallback(async (): Promise<Ids> => {
    const cfg = await getConfig();
    const session = await createSession(cfg.appName, uid.current);
    setAppName(cfg.appName);
    setSessionId(session.id);
    return { appName: cfg.appName, sessionId: session.id };
  }, []);

  /**
   * Open the session and greet — with NO model call.
   *
   * The greeting is a local string. Routing it through Gemini would spend an API
   * request on every page load: slow, and on the free tier (20/day) it would
   * exhaust the quota before anyone finished a form. The language preference
   * instead rides along on the first real turn, via `withDirective`.
   */
  const start = useCallback(async () => {
    langSent.current = false;
    setMessages([
      {
        id: crypto.randomUUID(),
        role: "agent",
        author: "orchestrator",
        text: dict(langCode).greeting,
      },
    ]);
    try {
      await boot();
    } catch (e) {
      const msg = (e as Error).message;
      setError({ kind: classify(msg), detail: msg });
    }
  }, [boot, langCode]);

  /** Prepend the one-time language instruction as a separate, invisible Part. */
  const withDirective = useCallback(
    (parts: Part[]): Part[] => {
      if (langSent.current) return parts;
      langSent.current = true;
      return [{ text: languageDirective(langCode) }, ...parts];
    },
    [langCode],
  );

  const send = useCallback(
    async (text: string) => {
      if (!appName || !sessionId || !text.trim()) return;
      await stream({ appName, sessionId }, withDirective([{ text }]), {
        id: crypto.randomUUID(),
        role: "user",
        text,
      });
    },
    [appName, sessionId, stream, withDirective],
  );

  /** Replay the last turn. For a 429 the user should just wait, then press this. */
  const retry = useCallback(async () => {
    if (!appName || !sessionId || !lastParts.current) return;
    await stream({ appName, sessionId }, lastParts.current);
  }, [appName, sessionId, stream]);

  /** Upload a form. The agent's checkpoint persists it; we keep a local preview. */
  const sendFile = useCallback(
    async (file: File, note: string) => {
      if (!appName || !sessionId) return;

      const base64 = await fileToBase64(file);
      const url = URL.createObjectURL(file);
      objectUrls.current.push(url);

      const attachment: Attachment = { name: file.name, mimeType: file.type, url };
      setUploaded(attachment);
      setStage("reading");

      await stream(
        { appName, sessionId },
        withDirective([
          { inlineData: { mimeType: file.type, data: base64 } },
          { text: note },
        ]),
        { id: crypto.randomUUID(), role: "user", text: note, attachment },
      );
    },
    [appName, sessionId, stream, withDirective],
  );

  const reset = useCallback(async () => {
    abort.current?.abort();
    objectUrls.current.forEach((u) => URL.revokeObjectURL(u));
    objectUrls.current = [];
    setArtifacts([]);
    setUploaded(null);
    setStage("start");
    setError(null);
    setActiveAgent(null);
    lastParts.current = null;
    await start(); // reseeds the greeting and opens a fresh session
  }, [start]);

  return {
    messages,
    busy,
    activity,
    activeAgent,
    artifacts,
    uploaded,
    stage,
    error,
    ready: Boolean(appName && sessionId),
    start,
    send,
    sendFile,
    retry,
    reset,
  };
}
