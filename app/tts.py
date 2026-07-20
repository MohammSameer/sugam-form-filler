"""Server-side speech synthesis — the fallback for languages the browser cannot speak.

WHY THIS EXISTS
    The UI speaks replies aloud so a user who cannot read can still use the app.
    The browser's built-in `speechSynthesis` is the right first choice: free,
    instant, offline. But Chrome ships voices for only a handful of the ten
    languages Sugam supports — English and (usually) Hindi are covered; Tamil,
    Telugu, Kannada, Gujarati, Punjabi and Urdu are not. Speaking Tamil text with
    an English voice produces gibberish, which is worse than silence.

    So the client uses an on-device voice whenever a real one exists for the
    language, and calls this only when none does. Gemini TTS covers the rest and
    uses the API key the app already has — no extra service, no extra billing.

COST
    Every call is a model request against the same quota as the agent. Two guards:
      * The client only calls this when it has no local voice — English and Hindi
        users never hit it at all.
      * Results are cached by (text, voice), so pressing Listen twice on the same
        message is free. Replies are short and repeat often ("What is your name?"),
        so the cache hits hard in practice.

FORMAT
    Gemini returns raw little-endian PCM (audio/L16), which no browser will play
    from an <audio> element. We wrap it in a 44-byte WAV header here rather than
    shipping a decoder to the client.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import time
import wave
from collections import OrderedDict
from typing import Optional

from google import genai
from google.genai import types

# The TTS model is separate from the agent's model: the agent's may be set to a
# non-audio model, and TTS is only available on the *-tts variants.
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")

# Gemini prebuilt voice. "Kore" is even-toned and clear — this reads official
# instructions to someone who may be anxious, not an audiobook.
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

# A generated reply is a sentence or two. The cap is a cost guard, not a feature.
MAX_CHARS = 1200

# Bounded LRU. Audio is ~48KB/second, so 64 entries is a few tens of MB at worst.
_CACHE_MAX = 64
_cache: "OrderedDict[str, bytes]" = OrderedDict()

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=os.environ.get("GOOGLE_API_KEY"),
            # The TTS free tier is only 3 requests/minute. Ride out the throttle
            # rather than failing the user's Listen press.
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=4,
                    initialDelay=2.0,
                    maxDelay=25.0,
                    expBase=2.0,
                    httpStatusCodes=[429, 500, 503, 504],
                )
            ),
        )
    return _client


def _pcm_to_wav(pcm: bytes, rate: int, channels: int = 1, width: int = 2) -> bytes:
    """Wrap raw PCM in a WAV container so a browser can play it directly."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)  # L16 = 16-bit = 2 bytes
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _rate_from_mime(mime: str) -> int:
    """Read the sample rate out of e.g. 'audio/L16;codec=pcm;rate=24000'."""
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 24000


def _generate_with_retry(text: str, attempts: int = 2):
    """Ask Gemini for audio, retrying an empty candidate.

    Under throttling the TTS model does not always return a clean 429 — it
    returns a candidate with `finish_reason=OTHER` and no content at all. The
    SDK's HTTP retry cannot see that (the call was a 200), so it must be retried
    here. Observed directly: the same Tamil text that succeeds when the model is
    idle comes back empty when the 3-requests/minute free tier is saturated.
    """
    last = ""
    for attempt in range(attempts):
        resp = _get_client().models.generate_content(
            # The text is passed as-is: Gemini infers the language from the
            # script. Any added instruction ("read this aloud") risks the model
            # narrating the instruction instead of the text.
            model=TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=TTS_VOICE
                        )
                    )
                ),
            ),
        )

        cand = (resp.candidates or [None])[0]
        blob = None
        if cand is not None and cand.content and cand.content.parts:
            blob = cand.content.parts[0].inline_data
        if blob and blob.data:
            return blob

        last = f"finish_reason={getattr(cand, 'finish_reason', None)}"
        if attempt < attempts - 1:
            time.sleep(2.0 * (attempt + 1))  # let the per-minute window drain

    raise RuntimeError(f"TTS returned no audio after {attempts} attempts ({last})")


def synthesize(text: str) -> bytes:
    """Speak `text` and return WAV bytes. Raises on API failure (incl. 429)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to speak")
    text = text[:MAX_CHARS]

    key = hashlib.sha256(f"{TTS_MODEL}|{TTS_VOICE}|{text}".encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)  # LRU touch
        return _cache[key]

    blob = _generate_with_retry(text)
    wav = _pcm_to_wav(blob.data, _rate_from_mime(blob.mime_type))

    _cache[key] = wav
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)  # evict least-recently-used
    return wav
