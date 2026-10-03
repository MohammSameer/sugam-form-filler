import { useRef } from "react";
import { useDropzone } from "react-dropzone";
import { Camera, FileUp, MessageCircleQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { dict } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The home screen: one dominant action (send us your form), one secondary
 * (just ask a question).
 *
 * "Take photo" gets its own input with `capture="environment"` rather than
 * relying on the dropzone. On a phone, a plain file input opens a file browser —
 * but the form is a piece of paper in the user's hand, not a file on their
 * device, so the camera has to be the shortest path.
 */

// Mirrors _UPLOAD_MIME_EXT in app/agent.py — the formats the fill pipeline can
// actually reopen and write onto. Accepting more here would only fail later.
const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
  "image/tiff": [".tif", ".tiff"],
  "image/bmp": [".bmp"],
  "image/gif": [".gif"],
};

export function Uploader({
  langCode,
  onFile,
  onAsk,
}: {
  langCode: string;
  onFile: (file: File) => void;
  onAsk: (question: string) => void;
}) {
  const t = dict(langCode);
  const camera = useRef<HTMLInputElement>(null);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept: ACCEPT,
    multiple: false,
    noClick: true, // the buttons below drive selection; the zone is drag-only
    noKeyboard: true,
    onDrop: (files) => files[0] && onFile(files[0]),
  });

  return (
    <div className="mx-auto w-full max-w-xl px-5 py-8">
      <div
        {...getRootProps()}
        className={cn(
          "rounded-xl2 border-2 border-dashed p-8 text-center transition-colors",
          isDragActive
            ? "border-accent bg-accent-soft"
            : "border-line bg-surface",
        )}
      >
        <input {...getInputProps()} />

        <div className="mx-auto mb-5 flex size-20 items-center justify-center rounded-2xl bg-brand-soft">
          <FileUp className="size-10 text-brand" aria-hidden />
        </div>

        <h2 className="text-2xl font-bold">
          {isDragActive ? t.dropNow : t.uploadTitle}
        </h2>
        <p className="mt-2 text-ink-soft">{t.uploadHint}</p>

        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          <Button
            variant="accent"
            size="lg"
            onClick={() => camera.current?.click()}
          >
            <Camera className="size-6" aria-hidden />
            <span>{t.takePhoto}</span>
          </Button>

          <Button variant="outline" size="lg" onClick={open}>
            <FileUp className="size-6" aria-hidden />
            <span>{t.choosePdf}</span>
          </Button>
        </div>

        {/* Opens the camera directly on a phone; falls back to a file picker on
            desktop, where `capture` is simply ignored. */}
        <input
          ref={camera}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = ""; // let the same file be picked twice
          }}
        />
      </div>

      <div className="mt-8">
        <p className="mb-3 text-center text-ink-soft">{t.orAsk}</p>
        <button
          type="button"
          onClick={() => onAsk(t.askExample)}
          className={cn(
            "tap flex w-full items-center gap-3 rounded-2xl border-2 border-line",
            "bg-surface px-5 text-start transition-colors",
            "hover:border-brand hover:bg-brand-soft",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
        >
          <MessageCircleQuestion
            className="size-6 shrink-0 text-brand"
            aria-hidden
          />
          <span className="py-3 leading-snug">{t.askExample}</span>
        </button>
      </div>
    </div>
  );
}
