import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Hourglass,
  Languages,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
  VolumeX,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Chat } from "@/features/Chat";
import { Composer } from "@/features/Composer";
import { LanguagePicker } from "@/features/LanguagePicker";
import { PdfCard } from "@/features/PdfCard";
import { TrustPanel } from "@/features/TrustPanel";
import { Uploader } from "@/features/Uploader";
import { useAgent } from "@/hooks/useAgent";
import { useSecurity } from "@/hooks/useSecurity";
import { useVoice } from "@/hooks/useVoice";
import { dict, lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LANG_KEY = "sugam.lang";

export default function App() {
  // Remembered across visits: re-picking your language every time is a tax on
  // exactly the user this product is for.
  const [langCode, setLangCode] = useState<string | null>(() =>
    localStorage.getItem(LANG_KEY),
  );

  if (!langCode) {
    return (
      <LanguagePicker
        onPick={(code) => {
          localStorage.setItem(LANG_KEY, code);
          setLangCode(code);
        }}
      />
    );
  }

  // Remounting on language change resets the agent session, so the whole
  // conversation is genuinely in the new language rather than half-translated.
  return (
    <Workspace
      key={langCode}
      langCode={langCode}
      onChangeLanguage={() => {
        localStorage.removeItem(LANG_KEY);
        setLangCode(null);
      }}
    />
  );
}

function Workspace({
  langCode,
  onChangeLanguage,
}: {
  langCode: string;
  onChangeLanguage: () => void;
}) {
  const t = dict(langCode);
  const l = lang(langCode);

  const agent = useAgent(langCode);
  const voice = useVoice(l.speech);
  const security = useSecurity(agent.busy);

  // Open the conversation exactly once. A ref, not state: `agent` is a fresh
  // object each render, so a dependency-based guard would re-fire the greeting.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void agent.start();
  }, [agent]);

  // Mirror the language onto the document so Urdu renders right-to-left and the
  // browser picks the right font and hyphenation rules.
  useEffect(() => {
    document.documentElement.lang = langCode;
    document.documentElement.dir = l.rtl ? "rtl" : "ltr";
  }, [langCode, l.rtl]);

  const handleFile = useCallback(
    (file: File) => {
      void agent.sendFile(file, t.uploadTitle);
    },
    [agent, t.uploadTitle],
  );

  const showUploader = agent.stage === "start" && !agent.uploaded;

  // The finished form. Pair each PDF with its preview PNG; the previews are not
  // cards of their own. Match on the filename extension, not the exact mimeType —
  // a stricter mimeType check silently rendered nothing if the value ever differed.
  const pdfs = agent.artifacts.filter(
    (a) => /\.pdf$/i.test(a.filename) || a.mimeType === "application/pdf",
  );
  const previewFor = (pdf: (typeof pdfs)[number]) =>
    agent.artifacts.find(
      (a) => a.filename === pdf.filename.replace(/\.pdf$/i, "_preview.png"),
    );

  // The download card renders below a long final message, past the chat's own
  // scroll anchor — so when it appears, actively bring it into view. Without this
  // the card is off-screen and users think no download exists.
  const resultRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (pdfs.length === 0) return;
    const id = window.setTimeout(
      () => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }),
      200,
    );
    return () => window.clearTimeout(id);
  }, [pdfs.length]);

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand text-xl font-bold text-white">
            स
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-bold leading-tight">Sugam</h1>
            {/* Hidden on phones: the badge and controls leave too little room,
                and a tagline clipped to "सरकारी …" is worse than none. */}
            <p className="hidden truncate text-sm text-ink-soft sm:block">
              {t.tagline}
            </p>
          </div>

          {/* On mobile the trust panel is offscreen, so its state collapses into
              this always-visible badge. */}
          <div className="flex items-center gap-1.5 rounded-full border border-safe/30 bg-safe-soft px-3 py-1.5 lg:hidden">
            <ShieldCheck className="size-4 text-safe-ink" aria-hidden />
            <span className="text-sm font-semibold tabular-nums text-safe-ink">
              {security.checksPassed}
            </span>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={onChangeLanguage}
            aria-label={t.changeLanguage}
            className="shrink-0"
          >
            <Languages className="size-5" aria-hidden />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => void agent.reset()}
            aria-label={t.startOver}
            className="shrink-0"
          >
            <RotateCcw className="size-5" aria-hidden />
          </Button>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-6 px-0 lg:grid-cols-[1fr_320px] lg:px-6 lg:py-6">
        {/* Conversation column */}
        {/* min-w-0: a grid item defaults to min-width:auto, so a wide descendant
            (the uploader card) stretches this column past the viewport and pushes
            the composer's send button off-screen on a phone. */}
        <main className="flex min-h-[calc(100dvh-5rem)] min-w-0 flex-col lg:min-h-0 lg:rounded-xl2 lg:border lg:border-line lg:bg-surface/50">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl">
              <Chat
                langCode={langCode}
                messages={agent.messages}
                busy={agent.busy}
                activity={agent.activity}
                speaking={voice.speaking}
                preparing={voice.preparing}
                onSpeak={voice.speak}
                onStopSpeak={voice.stopSpeaking}
              />

              {/* Voice playback failed (typically the TTS per-minute cap). Said
                  plainly in the user's language, not left as silence. */}
              {voice.speakError && (
                <div className="mx-5 -mt-2 mb-2 flex items-center gap-2 rounded-xl bg-surface-sunk px-4 py-2 text-sm text-ink-soft">
                  <VolumeX className="size-4 shrink-0" aria-hidden />
                  <span>{t.voiceFailed}</span>
                </div>
              )}

              <AnimatePresence>
                {showUploader && !agent.busy && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <Uploader
                      langCode={langCode}
                      onFile={handleFile}
                      onAsk={(q) => void agent.send(q)}
                    />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* The fill produces a PDF plus a '<stem>_preview.png' image; one
                  card per PDF, paired with its preview. */}
              {pdfs.length > 0 && (
                <div ref={resultRef} className="flex flex-col gap-3 px-5 pb-6">
                  {pdfs.map((pdf) => (
                    <PdfCard
                      key={pdf.filename}
                      langCode={langCode}
                      artifact={pdf}
                      preview={previewFor(pdf)}
                    />
                  ))}
                </div>
              )}

              {agent.error && (
                <div className="mx-5 mb-6 rounded-2xl border-2 border-danger/30 bg-danger-soft p-4">
                  <div className="flex items-start gap-3">
                    {agent.error.kind === "quota" ? (
                      <Hourglass
                        className="mt-0.5 size-5 shrink-0 text-danger-ink"
                        aria-hidden
                      />
                    ) : (
                      <TriangleAlert
                        className="mt-0.5 size-5 shrink-0 text-danger-ink"
                        aria-hidden
                      />
                    )}
                    <p className="min-w-0 flex-1 font-semibold text-danger-ink">
                      {agent.error.kind === "quota"
                        ? t.rateLimited
                        : t.errorGeneric}
                    </p>
                  </div>

                  <Button
                    variant="outline"
                    onClick={() => void agent.retry()}
                    disabled={agent.busy}
                    className="mt-4 w-full"
                  >
                    <RotateCcw className="size-5" aria-hidden />
                    {t.retry}
                  </Button>

                  {/* The raw provider error is for whoever is debugging, not for
                      the user — collapsed, never the headline. */}
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-danger-ink/70">
                      Details
                    </summary>
                    <p className="mt-1 break-words text-xs text-danger-ink/70">
                      {agent.error.detail}
                    </p>
                  </details>
                </div>
              )}
            </div>
          </div>

          <Composer
            langCode={langCode}
            disabled={agent.busy || !agent.ready}
            listening={voice.listening}
            interim={voice.interim}
            canListen={voice.canListen}
            onSend={(text) => void agent.send(text)}
            onListen={voice.listen}
            onStopListen={voice.stopListening}
            onAttach={handleFile}
          />
        </main>

        {/* Trust column — desktop only; the header badge stands in on mobile. */}
        <TrustPanel
          langCode={langCode}
          events={security.events}
          checksPassed={security.checksPassed}
          className={cn("hidden lg:flex")}
        />
      </div>
    </div>
  );
}
