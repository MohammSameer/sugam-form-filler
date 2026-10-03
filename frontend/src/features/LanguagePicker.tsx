import { motion } from "motion/react";
import { LANGUAGES } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The first screen. It is intentionally the *only* thing on it.
 *
 * Every label is an endonym rendered in its own script — a picker that says
 * "Hindi" in Latin letters is useless to someone who reads only Devanagari, and
 * that person is precisely who this product exists for. No flags either: scripts
 * map to languages, flags map to nations, and the two are not the same.
 */
export function LanguagePicker({
  onPick,
}: {
  onPick: (code: string) => void;
}) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center px-5 py-12">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="mb-10 text-center">
          <div className="mb-5 inline-flex size-16 items-center justify-center rounded-2xl bg-brand text-3xl font-bold text-white">
            स
          </div>
          <h1 className="text-4xl font-bold tracking-tight">Sugam</h1>
          {/* Shown in several scripts at once, because at this point we do not
              yet know which one the user reads. */}
          <p className="mt-3 text-lg text-ink-soft">
            अपनी भाषा चुनें · Choose your language
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {LANGUAGES.map((l, i) => (
            <motion.button
              key={l.code}
              type="button"
              lang={l.code}
              dir={l.rtl ? "rtl" : "ltr"}
              onClick={() => onPick(l.code)}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.04 * i, duration: 0.3 }}
              className={cn(
                "tap flex flex-col items-center justify-center gap-1 rounded-2xl",
                "border-2 border-line bg-surface px-4 py-5",
                "transition-colors hover:border-brand hover:bg-brand-soft",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                "active:scale-[0.98]",
              )}
            >
              <span className="text-xl font-semibold leading-tight">
                {l.native}
              </span>
              <span className="text-sm text-ink-soft">{l.english}</span>
            </motion.button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
