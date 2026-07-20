import { AnimatePresence, motion } from "motion/react";
import { EyeOff, FileCheck2, ShieldAlert, ShieldCheck } from "lucide-react";
import type { SecurityEvent } from "@/lib/adk";
import { dict } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * Makes the security checkpoint visible.
 *
 * This is the panel the ADK dev UI structurally cannot render: PII masking
 * happens in a `before_model_callback`, *before* the model is called, and a
 * blocked prompt short-circuits the call entirely — so neither ever appears in
 * the agent's event stream. They only exist in the audit log, which a browser
 * cannot read. `app/security_events.py` mirrors them onto a bus so they can be
 * shown here, in the moment, to the person they protected.
 *
 * Every row corresponds to something that actually happened. Nothing is implied
 * or simulated: if no PII was masked, no masking row appears.
 */

interface Row {
  icon: typeof ShieldCheck;
  tone: "safe" | "danger" | "brand";
  title: string;
  detail?: string;
}

export function TrustPanel({
  langCode,
  events,
  checksPassed,
  className,
}: {
  langCode: string;
  events: SecurityEvent[];
  checksPassed: number;
  className?: string;
}) {
  const t = dict(langCode);
  // Pair each row with its source event: filtering would otherwise desync the
  // row index from `events`, and the React key would point at the wrong event.
  const rows = events
    .map((e) => ({ event: e, row: toRow(e, t) }))
    .filter((x): x is { event: SecurityEvent; row: Row } => x.row !== null);

  return (
    <aside className={cn("flex flex-col gap-4", className)}>
      <div className="rounded-xl2 border-2 border-safe/30 bg-safe-soft p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 size-6 shrink-0 text-safe-ink" aria-hidden />
          <div>
            <h3 className="font-bold text-safe-ink">{t.protectedTitle}</h3>
            <p className="mt-1 text-sm leading-snug text-safe-ink/80">
              {t.protectedBody}
            </p>
          </div>
        </div>

        {checksPassed > 0 && (
          <p className="mt-4 border-t border-safe/20 pt-3 text-sm font-medium text-safe-ink">
            <span className="tabular-nums">{checksPassed}</span> {t.checksPassed}
          </p>
        )}
      </div>

      <AnimatePresence initial={false}>
        {rows.map(({ event, row }) => (
          <motion.div
            key={event.id}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className={cn(
              "flex items-start gap-3 rounded-2xl border p-4",
              row.tone === "danger" && "border-danger/30 bg-danger-soft",
              row.tone === "safe" && "border-safe/30 bg-safe-soft",
              row.tone === "brand" && "border-line bg-surface",
            )}
          >
            <row.icon
              className={cn(
                "mt-0.5 size-5 shrink-0",
                row.tone === "danger" && "text-danger-ink",
                row.tone === "safe" && "text-safe-ink",
                row.tone === "brand" && "text-brand",
              )}
              aria-hidden
            />
            <div className="min-w-0">
              <p
                className={cn(
                  "text-sm font-semibold leading-snug",
                  row.tone === "danger" && "text-danger-ink",
                  row.tone === "safe" && "text-safe-ink",
                  row.tone === "brand" && "text-ink",
                )}
              >
                {row.title}
              </p>
              {row.detail && (
                <p className="mt-0.5 truncate text-xs text-ink-soft">
                  {row.detail}
                </p>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </aside>
  );
}

/** Map a raw checkpoint event to a row, or null to keep it out of the panel. */
function toRow(e: SecurityEvent, t: ReturnType<typeof dict>): Row | null {
  switch (e.event) {
    case "input_cleared": {
      // Only ever reaches here when something was actually masked — the server
      // counts clean passes instead of emitting them.
      const masked = (e.details.masked as string[] | undefined) ?? [];
      if (!masked.length) return null;
      return {
        icon: EyeOff,
        tone: "safe",
        title: t.maskedNotice,
        detail: masked.join(" · "),
      };
    }
    case "prompt_injection_detected":
    case "consent_refused":
      return { icon: ShieldAlert, tone: "danger", title: t.blockedNotice };

    case "form_uploaded":
      return { icon: FileCheck2, tone: "brand", title: t.yourForm };

    case "pdf_delivered":
    case "uploaded_pdf_filled":
      return { icon: FileCheck2, tone: "safe", title: t.pdfReady };

    default:
      // Research/persistence events are real but not the user's concern.
      return null;
  }
}
