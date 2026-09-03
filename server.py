# -*- coding: utf-8 -*-
"""
Аватар-хост: прототип с lip-sync.
Озвучивает текст нейро-голосами Microsoft (edge-tts).
Видео аватара — фиксированные ролики: speaking.mp4 (губы двигаются) и awaiting.mp4 (молчит).
"""
import os
import time
import asyncio

import edge_tts
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

BUILD = "2.0.0"

app = Flask(__name__, static_folder="static", static_url_path="/static")

VOICES = [
    {"id": "ru-RU-DmitryNeural",   "label": "Дмитрий (мужской)"},
    {"id": "ru-RU-SvetlanaNeural", "label": "Светлана (женский)"},
    {"id": "ru-RU-DariyaNeural",   "label": "Дарья (женский)"},
]

PRESETS = [
    "Привет! Меня зовут Аватар, и я рад с вами познакомиться.",
    "Сегодня отличный день, чтобы попробовать что-то новое.",
    "Обратите внимание: это полностью рабочий прототип с синтезом речи.",
    "Спасибо, что слушаете. До новых встреч!",
]


@app.route("/")
def index():
    return render_template("index.html", voices=VOICES, presets=PRESETS, build=BUILD)


@app.route("/api/voices")
def api_voices():
    return jsonify(VOICES)


@app.route("/api/say", methods=["POST"])
def api_say():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    voice = data.get("voice") or "ru-RU-DmitryNeural"

    if not text:
        return jsonify({"error": "Пустой текст"}), 400
    if voice not in [v["id"] for v in VOICES]:
        voice = "ru-RU-DmitryNeural"

    ts = int(time.time() * 1000)
    audio_name = f"speech_{ts}.mp3"
    audio_path = os.path.join(AUDIO_DIR, audio_name)

    async def synth():
        parts = []
        comm = edge_tts.Communicate(text=text, voice=voice)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                parts.append(chunk["data"])
        with open(audio_path, "wb") as f:
            f.write(b"".join(parts))

    try:
        asyncio.run(synth())
    except Exception as e:
        return jsonify({"error": f"Синтез не удался: {e}"}), 500

    return jsonify({
        "audio_url": f"/static/audio/{audio_name}",
        "video_url": "/static/videos/speaking.mp4?build=2.0.0",
        "build": BUILD,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)