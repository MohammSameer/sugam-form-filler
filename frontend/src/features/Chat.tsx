import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { FileText, Loader2, ShieldCheck, Volume2, VolumeX } from "lucide-react";
import type { Message } from "@/hooks/useAgent";
import { dict, type StringKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The conversation.
 *
 * Agent bubbles carry a Listen button, not as a flourish but because a user who
 * cannot read the question cannot answer it. The blocked-by-policy reply is
 * styled distinctly so a security refusal never reads as the agent being unable
 * to help.
 */
export function Chat({
  langCode,
  messages,
  busy,
  activity,
  speaking,
  preparing,
  onSpeak,
  onStopSpeak,
}: {
  langCode: string;
  messages: Message[];
  busy: boolean;
  activity: string | null;
  speaking: boolean;
  /** Server synthesis in flight — show progress, not silence. */
  preparing: boolean;
  onSpeak: (text: string) => void;
  onStopSpeak: () => void;
}) {
  const t = dict(langCode);
  const end = useRef<HTMLDivElement>(null);

  // Follow the stream. `block: "end"` avoids yanking the whole page on mobile.
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  return (
    <div className="flex flex-col gap-4 px-5 py-6">
      {messages.map((m) => (
        <motion.div
          key={m.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className={cn(
            "flex w-full",
            m.role === "user" ? "justify-end" : "justify-start",
          )}
        >
          <div
            className={cn(
              "max-w-[85%] rounded-xl2 px-5 py-4",
              m.role === "user"
                ? "bg-brand text-white"
                : isBlocked(m.text)
                  ? "border-2 border-danger/30 bg-danger-soft text-danger-ink"
                  : "border border-line bg-surface text-ink",
            )}
          >
            {m.attachment && <AttachmentPreview attachment={m.attachment} />}

            <p className="whitespace-pre-wrap break-words leading-relaxed">
              {m.text}
            </p>

            {m.role === "agent" && m.text && (
              <button
                type="button"
                onClick={() => (speaking ? onStopSpeak() : onSpeak(m.text))}
                className={cn(
                  "mt-3 inline-flex items-center gap-2 rounded-full px-3 py-2",
                  "text-sm font-medium text-ink-soft transition-colors",
                  "hover:bg-surface-sunk hover:text-brand",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                )}
              >
                {preparing && speaking ? (
                  <Loader2 className="size-5 animate-spin" aria-hidden />
                ) : speaking ? (
                  <VolumeX className="size-5" aria-hidden />
                ) : (
                  <Volume2 className="size-5" aria-hidden />
                )}
                {t.listen}
              </button>
            )}
          </div>
        </motion.div>
      ))}

      {busy && <Thinking label={t[(activity ?? "thinking") as StringKey]} />}

      <div ref={end} />
    </div>
  );
}

/** The agent's canned refusal. Recognised so we can style it as a *shield*. */
function isBlocked(text: string) {
  return text.startsWith("Security Policy Violation");
}

function AttachmentPreview({
  attachment,
}: {
  attachment: NonNullable<Message["attachment"]>;
}) {
  const isImage = attachment.mimeType.startsWith("image/");
  return (
    <div className="mb-3 overflow-hidden rounded-xl bg-black/10">
      {isImage ? (
        <img
          src={attachment.url}
          alt={attachment.name}
          className="max-h-56 w-full object-cover"
        />
      ) : (
        <div className="flex items-center gap-3 px-4 py-3">
          <FileText className="size-6 shrink-0" aria-hidden />
          <span className="truncate text-sm">{attachment.name}</span>
        </div>
      )}
    </div>
  );
}

function Thinking({ label }: { label: string }) {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-3 rounded-xl2 border border-line bg-surface px-5 py-4">
        <ShieldCheck className="size-5 animate-shimmer text-brand" aria-hidden />
        <span className="text-ink-soft">{label}</span>
        <span className="flex gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-2 animate-shimmer rounded-full bg-brand"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
