# -*- coding: utf-8 -*-
"""
Синтез речи с деградацией.

1. edge-tts (Microsoft Neural) — основной путь, бесплатно, живой голос.
2. offline-фолбэк — если интернета нет / API отвалился, генерируем WAV
   нужной длительности (тихий «речевой» шум), чтобы шоу не встало:
   аватар отработает мимику, субтитры покажутся, тайминги сохранятся.

Наружу отдаём: synth(text, voice, rate, pitch) -> {url, duration, engine}
"""
import os
import re
import math
import time
import wave
import struct
import asyncio
import hashlib
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Сколько секунд живёт сгенерированный файл, потом чистится
AUDIO_TTL = 60 * 60
# Через сколько секунд после неудачи снова пробовать сеть
NETWORK_RETRY_AFTER = 60

_lock = threading.Lock()
_last_network_fail = 0.0
_engine_note = ""

VOICES = [
    {"id": "ru-RU-DmitryNeural", "label": "Дмитрий (мужской)"},
    {"id": "ru-RU-SvetlanaNeural", "label": "Светлана (женский)"},
    {"id": "ru-RU-DariyaNeural", "label": "Дарья (женский)"},
]
VOICE_IDS = [v["id"] for v in VOICES]
DEFAULT_VOICE = "ru-RU-DmitryNeural"


def estimate_duration(text: str, rate_pct: int = 0) -> float:
    """Грубая оценка длительности русской речи: ~14 символов/сек."""
    chars = max(len(text), 1)
    base = chars / 14.0 + 0.45
    factor = 1.0 / (1.0 + rate_pct / 100.0)
    return round(max(0.8, base * factor), 2)


def split_text(text: str, limit: int = 400):
    """Режем длинный текст по предложениям — и для лимитов, и для отзывчивости."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return [text] if text else []
    parts, buf = [], ""
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        if len(buf) + len(sentence) + 1 <= limit:
            buf = f"{buf} {sentence}".strip()
        else:
            if buf:
                parts.append(buf)
            buf = sentence
    if buf:
        parts.append(buf)
    return parts


def _fmt_pct(v: int) -> str:
    return f"{v:+d}%"


def _fmt_hz(v: int) -> str:
    return f"{v:+d}Hz"


async def _edge_synth(text, voice, rate, pitch, out_path):
    import edge_tts

    words = []
    chunks = []
    comm = edge_tts.Communicate(
        text=text, voice=voice, rate=_fmt_pct(rate), pitch=_fmt_hz(pitch)
    )
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append(
                {
                    "offset": chunk["offset"] / 10_000_000,
                    "duration": chunk["duration"] / 10_000_000,
                    "text": chunk["text"],
                }
            )
    if not chunks:
        raise RuntimeError("edge-tts вернул пустой поток")
    with open(out_path, "wb") as f:
        f.write(b"".join(chunks))
    duration = (words[-1]["offset"] + words[-1]["duration"]) if words else 0
    return duration, words


def _offline_synth(text, out_path, duration):
    """Тихий «говорящий» сигнал: слышно, что аватар работает, но не режет ухо."""
    rate = 22050
    n = int(rate * duration)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = 0.5 + 0.5 * math.sin(2 * math.pi * 2.6 * t)  # ритм «слогов»
        fade = min(1.0, t / 0.05, max(0.0, (duration - t) / 0.08))
        val = 0.055 * env * fade * math.sin(2 * math.pi * (115 + 22 * math.sin(2 * math.pi * 0.7 * t)) * t)
        frames += struct.pack("<h", int(val * 32767))
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def cleanup(ttl: int = AUDIO_TTL) -> int:
    """Удаляем старые файлы, чтобы static/audio не рос бесконечно."""
    now = time.time()
    removed = 0
    for name in os.listdir(AUDIO_DIR):
        if not name.startswith("speech_"):
            continue
        path = os.path.join(AUDIO_DIR, name)
        try:
            if now - os.path.getmtime(path) > ttl:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


def engine_note() -> str:
    return _engine_note


def synth(text: str, voice: str = DEFAULT_VOICE, rate: int = 0, pitch: int = 0) -> dict:
    """Возвращает {url, duration, engine, note}. Никогда не кидает исключение."""
    global _last_network_fail, _engine_note

    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой текст")
    if voice not in VOICE_IDS:
        voice = DEFAULT_VOICE
    rate = max(-50, min(50, int(rate)))
    pitch = max(-50, min(50, int(pitch)))

    key = hashlib.md5(f"{text}|{voice}|{rate}|{pitch}".encode()).hexdigest()[:10]
    stamp = int(time.time() * 1000)
    estimated = estimate_duration(text, rate)

    offline_only = (time.time() - _last_network_fail) < NETWORK_RETRY_AFTER

    if not offline_only:
        mp3_name = f"speech_{stamp}_{key}.mp3"
        mp3_path = os.path.join(AUDIO_DIR, mp3_name)
        try:
            duration, words = asyncio.run(_edge_synth(text, voice, rate, pitch, mp3_path))
            with _lock:
                _engine_note = ""
            return {
                "url": f"/static/audio/{mp3_name}",
                "duration": round(duration or estimated, 2),
                "engine": "edge-tts",
                "words": words,
                "note": "",
            }
        except Exception as e:  # сеть, ключи, изменившийся API — всё сюда
            with _lock:
                _last_network_fail = time.time()
                _engine_note = f"edge-tts недоступен ({type(e).__name__}), играем офлайн-дорожку"
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except OSError:
                pass

    wav_name = f"speech_{stamp}_{key}.wav"
    wav_path = os.path.join(AUDIO_DIR, wav_name)
    _offline_synth(text, wav_path, estimated)
    return {
        "url": f"/static/audio/{wav_name}",
        "duration": estimated,
        "engine": "offline",
        "words": [],
        "note": _engine_note or "офлайн-режим синтеза",
    }
