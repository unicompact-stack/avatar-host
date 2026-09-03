# -*- coding: utf-8 -*-
"""
Аватар-хост: говорящий аватар с приёмом гостей по QR-коду.
Озвучивает текст нейро-голосами Microsoft (edge-tts).
Гости сканируют QR, вводят имя, аватар здоровается по имени.
"""
import os
import io
import time
import asyncio
import secrets
import string

import edge_tts
import qrcode
from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

BUILD = "3.0.0"

app = Flask(__name__, static_folder="static", static_url_path="/static")

# --- Голоса ---
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

# --- Хранилище гостей (in-memory) ---
# Коды доступа: code -> {created_at}
access_codes = {}
# Гости: token -> {name, joined_at, greeted}
guests = {}
# Сессии: session_id -> {role, guest_token}
sessions = {}
# Заголовок экрана
screen_title = "Добро пожаловать на вечер"


def generate_access_code():
    """5-значный код без неоднозначных символов (аналог kviz-live)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(5))


def generate_token():
    """Токен для авторизации."""
    return secrets.token_hex(16)


def get_or_create_code():
    """Получить текущий код или создать новый (если нет или истёк)."""
    now = time.time()
    # Удаляем старые коды (> 1 часа)
    expired = [c for c, v in access_codes.items() if now - v["created_at"] > 3600]
    for c in expired:
        del access_codes[c]
    # Возвращаем существующий или создаём новый
    if access_codes:
        return list(access_codes.keys())[0]
    code = generate_access_code()
    access_codes[code] = {"created_at": now}
    return code


# --- Маршруты ---

@app.route("/")
def index():
    return render_template("index.html", voices=VOICES, presets=PRESETS, build=BUILD)


@app.route("/host")
def host():
    code = get_or_create_code()
    return render_template("host.html", code=code, build=BUILD)


@app.route("/admin")
def admin():
    code = get_or_create_code()
    return render_template("admin.html", code=code, build=BUILD)


@app.route("/connect")
def connect():
    code = request.args.get("code", "").upper()
    return render_template("connect.html", code=code, build=BUILD)


@app.route("/qr")
def qr():
    """Генерирует QR-код PNG со ссылкой на /connect?code=XXXXX."""
    code = request.args.get("code", "")
    if not code:
        return "нужен ?code=", 400
    # Формируем URL для подключения
    host = request.host
    url = f"http://{host}/connect?code={code}"
    # Генерируем QR
    qr_img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# --- API для синтеза речи (оставляем как было) ---

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
        "video_url": "/static/videos/speaking.mp4?build=" + BUILD,
        "build": BUILD,
    })


# --- API для приёма гостей ---

@app.route("/api/guest/connect", methods=["POST"])
def api_guest_connect():
    """Обмен 5-значного кода на токен (аналог playerConnect в kviz-live)."""
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()

    if not code:
        return jsonify({"error": "Введите код"}), 400
    if code not in access_codes:
        return jsonify({"error": "Игра с таким кодом не найдена"}), 404

    token = generate_token()
    sessions[token] = {"role": "guest", "guest_token": None}
    return jsonify({"accessToken": token})


@app.route("/api/guest/join", methods=["POST"])
def api_guest_join():
    """Регистрация имени по токену (аналог playerJoin в kviz-live)."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()
    name = (data.get("name") or "").strip()

    if not token or token not in sessions:
        return jsonify({"error": "Нет активной сессии"}), 401
    if not name:
        return jsonify({"error": "Введите имя"}), 400

    # Проверяем, не занято ли имя
    name_lower = name.lower()
    for g in guests.values():
        if g["name"].lower() == name_lower:
            return jsonify({"error": "Это имя уже занято"}), 409

    # Создаём гостя
    guest_token = generate_token()
    guests[guest_token] = {
        "name": name,
        "joined_at": time.time(),
        "greeted": False,
    }

    # Обновляем сессию
    sessions[token]["guest_token"] = guest_token

    return jsonify({
        "accessToken": guest_token,
        "playerId": guest_token,
        "name": name,
    })


@app.route("/api/guests")
def api_guests():
    """Список гостей (для экрана ведущего)."""
    guest_list = [
        {"token": t, "name": g["name"], "joined_at": g["joined_at"], "greeted": g["greeted"]}
        for t, g in guests.items()
    ]
    guest_list.sort(key=lambda x: x["joined_at"])
    return jsonify({
        "guests": guest_list,
        "count": len(guest_list),
    })


@app.route("/api/guest/greet", methods=["POST"])
def api_guest_greet():
    """Отметить гостя как приветствованного."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()

    if token in guests:
        guests[token]["greeted"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Гость не найден"}), 404


# --- Запуск ---

PORT = int(os.environ.get("PORT", 8000))

if __name__ == "__main__":
    print(f"\n=== Аватар-хост v{BUILD} ===")
    print(f"\n  Экран (публичный):  http://localhost:{PORT}/host")
    print(f"  Панель управления:   http://localhost:{PORT}/admin")
    print(f"  Вход для гостя:     http://localhost:{PORT}/connect?code=XXXXX")
    print(f"  Тестовый режим:     http://localhost:{PORT}/\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
