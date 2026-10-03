import { useState } from "react";
import { Mic, Paperclip, Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { dict } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The input bar: attach, type or speak, send.
 *
 * The mic is a peer of the text box, not an afterthought behind a menu. A spoken
 * answer is transcribed into the box rather than sent straight off, so the user
 * can see and correct it before committing — speech recognition on Indian
 * languages is good, not perfect, and a silently mis-sent name ends up on a
 * government form.
 */
export function Composer({
  langCode,
  disabled,
  listening,
  interim,
  canListen,
  onSend,
  onListen,
  onStopListen,
  onAttach,
}: {
  langCode: string;
  disabled: boolean;
  listening: boolean;
  interim: string;
  canListen: boolean;
  onSend: (text: string) => void;
  /** Starts recognition; the final transcript comes back through the callback. */
  onListen: (onResult: (transcript: string) => void) => void;
  onStopListen: () => void;
  onAttach: (file: File) => void;
}) {
  const t = dict(langCode);
  const [text, setText] = useState("");

  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    setText("");
    onSend(value);
  };

  // The transcript lands in the textarea; the user still presses send. Speech
  // recognition on Indian languages is good but not perfect, and a silently
  // mis-sent name ends up on a government form.
  const startListening = () =>
    onListen((transcript) =>
      setText((prev) => (prev ? `${prev} ${transcript}` : transcript)),
    );

  // While the mic is open, show the live transcript in the box so the user can
  // watch their words land.
  const shown = listening && interim ? interim : text;

  return (
    <div className="sticky bottom-0 border-t border-line bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-3">
        <label
          className={cn(
            "tap flex w-14 shrink-0 cursor-pointer items-center justify-center",
            "rounded-2xl border-2 border-line bg-surface text-ink-soft",
            "transition-colors hover:border-brand hover:text-brand",
            disabled && "pointer-events-none opacity-50",
          )}
        >
          <Paperclip className="size-6" aria-hidden />
          <span className="sr-only">{t.uploadTitle}</span>
          <input
            type="file"
            accept="application/pdf,image/*"
            className="sr-only"
            disabled={disabled}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onAttach(f);
              e.target.value = "";
            }}
          />
        </label>

        <textarea
          value={shown}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter makes a new line.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          disabled={disabled}
          placeholder={listening ? t.listening : t.placeholder}
          className={cn(
            // min-w-0 is load-bearing: a textarea has an intrinsic column width
            // and will not shrink below it, which pushes the send button off a
            // 390px screen. flex-1 alone is not enough.
            "tap max-h-40 min-w-0 flex-1 resize-none rounded-2xl border-2 bg-surface",
            "px-4 py-4 leading-snug placeholder:text-ink-soft/70",
            "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
            listening ? "border-accent" : "border-line",
            disabled && "opacity-50",
          )}
        />

        {canListen && (
          <Button
            variant={listening ? "danger" : "outline"}
            size="icon"
            disabled={disabled}
            onClick={listening ? onStopListen : startListening}
            aria-label={listening ? t.listening : t.tapToSpeak}
            className={cn("shrink-0", listening && "animate-shimmer")}
          >
            {listening ? (
              <Square className="size-5" aria-hidden />
            ) : (
              <Mic className="size-6" aria-hidden />
            )}
          </Button>
        )}

        <Button
          variant="accent"
          size="icon"
          disabled={disabled || !text.trim()}
          onClick={submit}
          aria-label={t.send}
          className="shrink-0"
        >
          <Send className="size-6" aria-hidden />
        </Button>
      </div>
    </div>
  );
}
