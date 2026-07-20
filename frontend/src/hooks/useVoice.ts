import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * Voice input and output.
 *
 * A user who cannot read the agent's question cannot answer it, so `speak()`
 * reads replies aloud and `listen()` lets them answer by talking.
 *
 * SPEECH OUTPUT IS A HYBRID, AND IT HAS TO BE.
 *
 * The browser's `speechSynthesis` is the right first choice — free, instant,
 * offline. But Chrome ships voices for only a few of our ten languages: English
 * and usually Hindi, essentially never Tamil, Telugu, Kannada, Gujarati, Punjabi
 * or Urdu. Handing Tamil text to an English voice does not "mostly work"; it
 * produces gibberish, which is worse than silence.
 *
 * So: use an on-device voice when one genuinely matches the language, and fall
 * back to the server (`/api/tts`, Gemini TTS) only when none does. English and
 * Hindi users never touch the network; the other six get real speech instead of
 * nonsense.
 *
 * Two traps this code exists to avoid:
 *   1. `getVoices()` is ASYNC in Chrome and returns [] on first call. Reading it
 *      synchronously inside speak() silently yields no voice, so the utterance
 *      falls back to the default (English) voice — which is exactly the bug where
 *      "English works and nothing else does". We wait for `voiceschanged`.
 *   2. Voice `lang` tags are inconsistent across platforms ("hi-IN", "hi_IN",
 *      "hi"). We normalise before comparing.
 */

// The Web Speech API is not in TypeScript's DOM lib, so we declare the slice we use.
interface SpeechRecognitionAlternative {
  transcript: string;
}
interface SpeechRecognitionResult {
  0: SpeechRecognitionAlternative;
  isFinal: boolean;
  length: number;
}
interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: Event) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getRecognition(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** "hi_IN" / "hi-IN" / "HI" -> "hi-in". Platforms disagree on the separator. */
const norm = (tag: string) => tag.replace("_", "-").toLowerCase();

export function useVoice(speechLang: string) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  /** Server synthesis is in flight — audible silence otherwise, which reads as broken. */
  const [preparing, setPreparing] = useState(false);
  /** True briefly after a failed Listen, so the UI can say "try again" not stay silent. */
  const [speakError, setSpeakError] = useState(false);
  const [interim, setInterim] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  const recognition = useRef<SpeechRecognitionLike | null>(null);
  // Held in a ref, not state: the recognition callbacks are registered once but
  // must always call the *latest* handler the component passed.
  const onFinal = useRef<(text: string) => void>(() => {});
  // Playback for the server-TTS path, and a cache so a second Listen press on
  // the same message costs nothing.
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioCache = useRef<Map<string, string>>(new Map());

  const canListen = getRecognition() !== null;
  const hasSynth = typeof window !== "undefined" && "speechSynthesis" in window;

  // Voices arrive asynchronously in Chrome — the list is empty on first read and
  // is populated later, announced by `voiceschanged`. Reading it synchronously
  // inside speak() is the root cause of "only English speaks".
  useEffect(() => {
    if (!hasSynth) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load(); // already populated on Firefox/Safari, and on a warm Chrome tab
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () =>
      window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, [hasSynth]);

  /** A real on-device voice for this language, or null. Never a wrong-language one. */
  const localVoice = useMemo(() => {
    if (!voices.length) return null;
    const want = norm(speechLang); // e.g. "hi-in"
    const base = want.split("-")[0]; // e.g. "hi"
    return (
      voices.find((v) => norm(v.lang) === want) ??
      voices.find((v) => norm(v.lang).split("-")[0] === base) ??
      null
    );
  }, [voices, speechLang]);

  const urls = audioCache;
  useEffect(() => {
    const cache = urls;
    return () => {
      recognition.current?.abort();
      if (hasSynth) window.speechSynthesis.cancel();
      audio.current?.pause();
      cache.current.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [hasSynth, urls]);

  const listen = useCallback(
    (onResult: (text: string) => void) => {
      const Ctor = getRecognition();
      if (!Ctor) return;

      onFinal.current = onResult;
      recognition.current?.abort();

      const rec = new Ctor();
      rec.lang = speechLang;
      rec.continuous = false;
      rec.interimResults = true; // show words as they land, so it feels alive

      rec.onresult = (e) => {
        let final = "";
        let partial = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) final += r[0].transcript;
          else partial += r[0].transcript;
        }
        setInterim(partial);
        if (final) {
          setInterim("");
          onFinal.current(final.trim());
        }
      };
      rec.onerror = () => {
        setListening(false);
        setInterim("");
      };
      rec.onend = () => {
        setListening(false);
        setInterim("");
      };

      recognition.current = rec;
      setListening(true);
      rec.start();
    },
    [speechLang],
  );

  const stopListening = useCallback(() => {
    recognition.current?.stop();
    setListening(false);
    setInterim("");
  }, []);

  const stopSpeaking = useCallback(() => {
    if (hasSynth) window.speechSynthesis.cancel();
    if (audio.current) {
      audio.current.pause();
      audio.current = null;
    }
    setSpeaking(false);
    setPreparing(false);
  }, [hasSynth]);

  /** Play WAV from /api/tts. Used only for languages with no on-device voice. */
  const speakViaServer = useCallback(async (text: string) => {
    let url = audioCache.current.get(text);

    if (!url) {
      // Synthesis takes a couple of seconds. Say so, or the button looks broken.
      setPreparing(true);
      try {
        const res = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (!res.ok) throw new Error(`TTS failed: ${res.status}`);
        url = URL.createObjectURL(await res.blob());
        audioCache.current.set(text, url); // a second press replays for free
      } finally {
        setPreparing(false);
      }
    }

    const el = new Audio(url);
    audio.current = el;
    el.onended = () => setSpeaking(false);
    el.onerror = () => setSpeaking(false);
    await el.play();
  }, []);

  const speak = useCallback(
    async (text: string) => {
      if (!text) return;
      stopSpeaking(); // never let two utterances overlap

      setSpeakError(false);
      setSpeaking(true);

      // Free, instant, offline — but only when a voice for THIS language exists.
      if (localVoice && hasSynth) {
        const u = new SpeechSynthesisUtterance(text);
        u.voice = localVoice;
        u.lang = localVoice.lang;
        u.rate = 0.95; // a touch slower: these are instructions, not prose
        u.onend = () => setSpeaking(false);
        u.onerror = () => setSpeaking(false);
        window.speechSynthesis.speak(u);
        return;
      }

      // No local voice for this language. Speaking it with a wrong-language voice
      // would produce gibberish, so go to the server instead.
      try {
        await speakViaServer(text);
      } catch {
        // The text is still on screen, so this is not fatal — but a user who
        // pressed Listen expecting audio deserves to know it didn't play, not
        // silence. The UI shows a brief "try again" and clears it.
        setSpeaking(false);
        setSpeakError(true);
      }
    },
    [localVoice, hasSynth, speakViaServer, stopSpeaking],
  );

  // Auto-clear the failure notice so it never lingers as a stuck error.
  useEffect(() => {
    if (!speakError) return;
    const id = window.setTimeout(() => setSpeakError(false), 5000);
    return () => window.clearTimeout(id);
  }, [speakError]);

  return {
    canListen,
    /** Always true now: a language with no on-device voice falls back to the server. */
    canSpeak: true,
    /** True when the audio comes from Gemini rather than the device (slower to start). */
    usesServerVoice: !localVoice,
    listening,
    speaking,
    preparing,
    speakError,
    interim,
    listen,
    stopListening,
    speak,
    stopSpeaking,
  };
}
