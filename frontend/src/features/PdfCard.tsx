import { motion } from "motion/react";
import { CheckCircle2, Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Artifact } from "@/hooks/useAgent";
import { dict } from "@/lib/i18n";

/**
 * The payoff: the filled form, shown so the user can actually see it.
 *
 * The preview is a server-rendered PNG (`<img>`), NOT a PDF blob in an <iframe>.
 * A blob PDF in an iframe renders blank in many Chromium builds — which is why a
 * user ends up opening the file from disk instead. An <img> renders everywhere,
 * so the filled form is visible in the conversation with no extra click. The PDF
 * itself is one tap away to download or open full-size in the browser's own
 * viewer (a real anchor, so long-press "save as" and assistive tech both work).
 */
export function PdfCard({
  langCode,
  artifact,
  preview,
}: {
  langCode: string;
  artifact: Artifact;
  preview?: Artifact;
}) {
  const t = dict(langCode);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 22 }}
      className="rounded-xl2 border-2 border-safe/40 bg-safe-soft p-5"
    >
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 size-7 shrink-0 text-safe-ink" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-bold text-safe-ink">{t.pdfReady}</h3>
          <p className="mt-0.5 truncate text-sm text-safe-ink/75">
            {artifact.filename}
          </p>
        </div>
      </div>

      {/* Inline preview of the filled form — always visible, always renders.
          Tapping it opens the real PDF full-size in the browser's own viewer. */}
      {preview && (
        <a
          href={artifact.url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 block max-h-[28rem] overflow-y-auto rounded-xl border border-line bg-surface"
          aria-label={t.yourForm}
        >
          <img
            src={preview.url}
            alt={t.yourForm}
            className="w-full"
            loading="lazy"
          />
        </a>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {/* `download` makes the browser save the file instead of navigating. */}
        <Button asChild variant="accent" size="lg">
          <a href={artifact.url} download={artifact.filename}>
            <Download className="size-6" aria-hidden />
            {t.download}
          </a>
        </Button>

        {/* Open the PDF full-size in a new tab — the browser's native viewer,
            which is exactly what a user reaches for to inspect the whole form. */}
        <Button asChild variant="outline" size="lg">
          <a href={artifact.url} target="_blank" rel="noreferrer">
            <ExternalLink className="size-6" aria-hidden />
            {t.yourForm}
          </a>
        </Button>
      </div>
    </motion.div>
  );
}
