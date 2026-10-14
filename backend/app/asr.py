"""Speech-to-text with mlx-whisper (Apple Silicon GPU via MLX).

The browser does voice-activity detection and sends each speech segment as
raw 16 kHz mono float32 PCM, so no audio decoding/ffmpeg is needed here.
"""

import asyncio
import logging
import re
import time

import numpy as np

from . import config

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000

# Biases decoding toward Simplified Chinese with punctuation.
_PROMPTS = {"zh": "以下是普通话的面试回答，使用简体中文和标点符号。", "en": "The following is an answer in a job interview."}

# Whisper hallucinates these on silence / noise (subtitle credits in its training data).
_HALLUCINATIONS = re.compile(
    r"^(谢谢观看|谢谢大家|请不吝点赞|订阅|字幕由.*|明镜.*|thank you( for watching)?|thanks for watching|you|bye)[。.!！\s]*$",
    re.IGNORECASE,
)

_lock = asyncio.Lock()  # MLX inference is not meant to run concurrently
status = {"state": "loading", "model": config.ASR_MODEL, "error": ""}


def _transcribe_sync(audio: np.ndarray, language: str) -> str:
    import mlx_whisper  # heavy import, keep lazy so tests/startup stay fast

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=config.ASR_MODEL,
        language=language,
        initial_prompt=_PROMPTS.get(language),
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        temperature=0.0,
    )
    kept = [
        s["text"].strip()
        for s in result.get("segments", [])
        if s.get("no_speech_prob", 0) < 0.6 and not _HALLUCINATIONS.match(s["text"].strip())
    ]
    sep = "" if language == "zh" else " "
    return sep.join(t for t in kept if t)


async def transcribe_pcm(pcm: bytes, language: str) -> tuple[str, float]:
    audio = np.frombuffer(pcm, dtype=np.float32)
    if audio.size < SAMPLE_RATE * 0.3:  # under 300 ms: not an answer
        return "", 0.0
    t0 = time.perf_counter()
    async with _lock:
        text = await asyncio.to_thread(_transcribe_sync, audio, language)
    dt = time.perf_counter() - t0
    log.info("asr %.1fs audio -> %.2fs: %s", audio.size / SAMPLE_RATE, dt, text[:80])
    return text, dt


async def warmup() -> None:
    """Load weights once so the first real answer is not slow."""
    try:
        await transcribe_pcm(np.zeros(SAMPLE_RATE, dtype=np.float32).tobytes(), "en")
        status.update(state="ready", error="")
        log.info("ASR ready (%s)", config.ASR_MODEL)
    except Exception as e:  # noqa: BLE001 - voice is optional, text mode still works
        status.update(state="unavailable", error=str(e)[:200])
        log.warning("ASR warmup failed: %s", e)
