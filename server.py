# -*- coding: utf-8 -*-
"""
Аватар-хост v4.0.0 — говорящий аватар-ведущий мероприятия.

Что нового против 3.1.0:
- SSE вместо BroadcastChannel: админка на планшете, экран на проекторе, гости на телефонах;
- серверная очередь речи: реплики не накладываются;
- офлайн-фолбэк синтеза (tts.py), автоочистка static/audio;
- фазы вечера, конкурс с ответами и рейтингом;
- демо-гости и сценарий «выдуманного вечера» для репетиции без людей.
"""
import io
import os
import json
import time
import queue
import random
import threading

import secrets
from functools import wraps

import qrcode
from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import tts
import netinfo
import scenario as scenario_mod
from event_state import EVENT, new_token, public_guest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD = "4.2.0"

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)

# PIN пульта: без него любой гость в той же сети откроет /admin и заберёт управление.
ADMIN_PIN = os.environ.get("ADMIN_PIN") or "".join(secrets.choice("0123456789") for _ in range(4))
# Публичный базовый URL (для интернет-режима за туннелем/reverse-proxy)
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or "").rstrip("/")


def admin_ok():
    return session.get("admin") is True


def require_admin(fn):
    """Защита управляющих ручек. Гостевые и экранные ручки остаются открытыми."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not admin_ok():
            return jsonify({"error": "Нужен PIN пульта", "need_pin": True}), 401
        return fn(*a, **kw)
    return wrapper

PRESETS = [
    "Дорогие гости, рассаживайтесь — через пару минут начинаем!",
    "А теперь прошу тишины: слово нашим дорогим родителям.",
    "Объявляется музыкальная пауза. Танцпол ждёт!",
    "Спасибо, что были с нами. Этот вечер удался благодаря вам!",
]

def plural(n, one, few, many):
    """Русские числительные: 1 гость, 2 гостя, 5 гостей."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


DEMO_NAMES = [
    "Анна", "Игорь", "Мария и Сергей", "Пётр Ильич", "Ольга",
    "Тимур", "Лена", "Виктор Степанович", "Даша", "Костя",
]


# ---------------------------------------------------------------- очередь речи

def speech_worker():
    """Единственный поток, который синтезирует и выдаёт команды на экран."""
    while True:
        item = EVENT.pop_next()
        if not item:
            time.sleep(0.15)
            continue
        try:
            result = tts.synth(
                item["text"], item.get("voice") or EVENT.voice,
                item.get("rate", EVENT.rate), item.get("pitch", EVENT.pitch),
            )
        except Exception as e:
            EVENT.bus.publish("error", {"message": f"Синтез не удался: {e}"})
            EVENT.finish_current(item["id"])
            continue

        EVENT.bus.publish("speak", {
            "id": item["id"],
            "text": item["text"],
            "kind": item["kind"],
            "audio_url": result["url"],
            "duration": result["duration"],
            "engine": result["engine"],
            "note": result["note"],
        })
        EVENT.bus.publish("queue", EVENT.queue_snapshot())

        # Страховка: если экран не отчитался (закрыли вкладку) — освобождаем очередь сами.
        deadline = time.time() + result["duration"] + 6
        while time.time() < deadline:
            if EVENT.now_speaking is None or EVENT.now_speaking["id"] != item["id"]:
                break
            time.sleep(0.2)
        else:
            EVENT.finish_current(item["id"])
            EVENT.bus.publish("idle", {})


def cleanup_worker():
    while True:
        tts.cleanup()
        time.sleep(600)


threading.Thread(target=speech_worker, daemon=True).start()
threading.Thread(target=cleanup_worker, daemon=True).start()


def say(text, kind="say", priority=5, guest=None):
    text = (text or "").strip()
    if not text:
        return None
    return EVENT.enqueue({"text": text, "kind": kind, "priority": priority, "guest": guest})


# ---------------------------------------------------------------- страницы

@app.route("/")
def index():
    return render_template("index.html", voices=tts.VOICES, presets=PRESETS, build=BUILD)


@app.route("/host")
def host():
    return render_template("host.html", code=EVENT.code, build=BUILD)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    error = ""
    if request.method == "POST":
        if (request.form.get("pin") or "").strip() == ADMIN_PIN:
            session["admin"] = True
            session.permanent = True
            return redirect(url_for("admin"))
        error = "Неверный PIN"
    if not admin_ok():
        return render_template("admin_login.html", build=BUILD, error=error), (401 if error else 200)
    return render_template("admin.html", code=EVENT.code, build=BUILD,
                           voices=tts.VOICES, presets=PRESETS)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return jsonify({"ok": True})


@app.route("/api/network")
@require_admin
def api_network():
    """Адреса для подключения — показываем в админке и на экране."""
    u = netinfo.urls(PORT)
    u["public_url"] = PUBLIC_URL
    u["base"] = base_url()
    u["admin_pin"] = ADMIN_PIN
    return jsonify(u)


@app.route("/connect")
def connect():
    return render_template("connect.html", code=request.args.get("code", "").upper(), build=BUILD)


def base_url():
    """Адрес, по которому нас видит телефон гостя."""
    if PUBLIC_URL:
        return PUBLIC_URL
    base = request.headers.get("X-Forwarded-Host") or request.host
    scheme = request.headers.get("X-Forwarded-Proto") or request.scheme
    # localhost в QR бесполезен — телефон по нему попадёт сам в себя
    hostname = base.split(":")[0]
    if hostname in ("localhost", "127.0.0.1"):
        port = base.split(":")[1] if ":" in base else str(PORT)
        base = f"{netinfo.primary_ip()}:{port}"
    return f"{scheme}://{base}"


@app.route("/qr")
def qr():
    code = request.args.get("code") or EVENT.code
    url = f"{base_url()}/connect?code={code}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- SSE

@app.route("/api/stream")
def api_stream():
    q = EVENT.bus.subscribe()

    def gen():
        try:
            yield sse("hello", EVENT.snapshot())
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield sse(msg["event"], msg["data"])
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            EVENT.bus.unsubscribe(q)

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- состояние

@app.route("/api/state")
def api_state():
    s = EVENT.snapshot()
    s.update(build=BUILD, engine_note=tts.engine_note(), listeners=EVENT.bus.listeners)
    return jsonify(s)


@app.route("/api/voices")
def api_voices():
    return jsonify(tts.VOICES)


@app.route("/api/settings", methods=["POST"])
@require_admin
def api_settings():
    d = request.get_json(force=True, silent=True) or {}
    with EVENT.lock:
        for field in ("title", "subtitle", "greeting_template", "voice"):
            if field in d and isinstance(d[field], str) and d[field].strip():
                setattr(EVENT, field, d[field].strip())
        for field in ("rate", "pitch", "guest_limit"):
            if field in d:
                try:
                    setattr(EVENT, field, int(d[field]))
                except (TypeError, ValueError):
                    pass
        if "accepting" in d:
            EVENT.accepting = bool(d["accepting"])
        if d.get("phase") in EVENT.PHASES:
            EVENT.phase = d["phase"]
    EVENT.bus.publish("state", EVENT.snapshot())
    return jsonify(EVENT.snapshot())


@app.route("/api/reset", methods=["POST"])
@require_admin
def api_reset():
    EVENT.reset()
    EVENT.bus.publish("state", EVENT.snapshot())
    return jsonify(EVENT.snapshot())


# ---------------------------------------------------------------- речь

@app.route("/api/say", methods=["POST"])
@require_admin
def api_say():
    d = request.get_json(force=True, silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Пустой текст"}), 400
    items = []
    for part in tts.split_text(text):
        items.append(say(part, kind=d.get("kind", "say"), priority=int(d.get("priority", 5))))
    return jsonify({"queued": [i["id"] for i in items if i], "queue": EVENT.queue_snapshot()})


@app.route("/api/tts/preview", methods=["POST"])
@require_admin
def api_tts_preview():
    """Прямой синтез в обход очереди — только для тестового режима."""
    d = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(tts.synth(d.get("text", ""), d.get("voice") or EVENT.voice,
                                 int(d.get("rate", 0)), int(d.get("pitch", 0))))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/speech/done", methods=["POST"])
def api_speech_done():
    d = request.get_json(force=True, silent=True) or {}
    EVENT.finish_current(d.get("id"))
    EVENT.bus.publish("idle", {})
    return jsonify({"ok": True, "queue": EVENT.queue_snapshot()})


@app.route("/api/speech/skip", methods=["POST"])
@require_admin
def api_speech_skip():
    EVENT.finish_current()
    EVENT.bus.publish("stop", {})
    return jsonify({"ok": True, "queue": EVENT.queue_snapshot()})


@app.route("/api/speech/clear", methods=["POST"])
@require_admin
def api_speech_clear():
    with EVENT.lock:
        EVENT.speech_queue.clear()
    EVENT.finish_current()
    EVENT.bus.publish("stop", {})
    return jsonify({"ok": True, "queue": EVENT.queue_snapshot()})


# ---------------------------------------------------------------- гости

@app.route("/api/guest/connect", methods=["POST"])
def api_guest_connect():
    d = request.get_json(force=True, silent=True) or {}
    code = (d.get("code") or "").strip().upper()
    if code != EVENT.code:
        return jsonify({"error": "Мероприятие с таким кодом не найдено"}), 404
    if not EVENT.accepting:
        return jsonify({"error": "Приём гостей закрыт"}), 403
    token = new_token()
    EVENT.sessions[token] = {"guest_token": None}
    return jsonify({"accessToken": token, "title": EVENT.title})


@app.route("/api/guest/join", methods=["POST"])
def api_guest_join():
    d = request.get_json(force=True, silent=True) or {}
    token = (d.get("token") or "").strip()
    if token not in EVENT.sessions:
        return jsonify({"error": "Нет активной сессии, отсканируйте QR заново"}), 401
    guest, err = EVENT.add_guest(d.get("name") or "", d.get("table") or "")
    if err:
        return jsonify({"error": err}), 409
    EVENT.sessions[token]["guest_token"] = guest["token"]
    if EVENT.phase in ("idle", "welcome", "greeting"):
        greet_guest(guest)
    return jsonify({"accessToken": guest["token"], "name": guest["name"]})


def greet_guest(guest):
    text = EVENT.greeting_template.replace("{name}", guest["name"])
    if guest.get("table"):
        text += f" Ваше место — {guest['table']}."
    with EVENT.lock:
        guest["greeted"] = True
        EVENT.phase = "greeting" if EVENT.phase == "idle" else EVENT.phase
    EVENT.bus.publish("guest_greeted", {"guest": public_guest(guest)})
    return say(text, kind="greeting", priority=1, guest=guest["token"])


@app.route("/api/guests")
def api_guests():
    return jsonify({"guests": EVENT.guest_list(), "count": EVENT.guest_count})


@app.route("/api/guest/greet", methods=["POST"])
@require_admin
def api_guest_greet():
    d = request.get_json(force=True, silent=True) or {}
    token = (d.get("token") or "").strip()
    guest = EVENT.guests.get(token)
    if not guest:
        return jsonify({"error": "Гость не найден"}), 404
    greet_guest(guest)
    return jsonify({"ok": True})


@app.route("/api/guest/me")
def api_guest_me():
    token = request.args.get("token", "")
    guest = EVENT.guests.get(token)
    if not guest:
        return jsonify({"error": "Гость не найден"}), 404
    return jsonify({
        "guest": public_guest(guest),
        "quiz": EVENT.quiz_public(),
        "collect": EVENT.collect_public(),
        "phase": EVENT.phase,
        "title": EVENT.title,
    })


# ---------------------------------------------------------------- конкурс

@app.route("/api/quiz/start", methods=["POST"])
@require_admin
def api_quiz_start():
    d = request.get_json(force=True, silent=True) or {}
    question = (d.get("question") or "").strip()
    options = [o.strip() for o in (d.get("options") or []) if o.strip()]
    if not question or len(options) < 2:
        return jsonify({"error": "Нужен вопрос и минимум два варианта"}), 400
    snap = EVENT.start_quiz(question, options, int(d.get("seconds", 30)))
    letters = "АБВГД"
    spoken = question + " Варианты: " + "; ".join(
        f"{letters[i]} — {o}" for i, o in enumerate(options)
    ) + ". Отвечайте на телефонах!"
    say(spoken, kind="quiz", priority=2)
    return jsonify(snap)


@app.route("/api/quiz/answer", methods=["POST"])
def api_quiz_answer():
    d = request.get_json(force=True, silent=True) or {}
    snap, err = EVENT.answer_quiz((d.get("token") or "").strip(), int(d.get("index", -1)))
    if err:
        return jsonify({"error": err}), 400
    return jsonify(snap)


@app.route("/api/quiz/close", methods=["POST"])
@require_admin
def api_quiz_close():
    d = request.get_json(force=True, silent=True) or {}
    correct = d.get("correct")
    snap = EVENT.close_quiz(int(correct) if correct is not None else None)
    if not snap:
        return jsonify({"error": "Конкурс не запущен"}), 400
    if snap["correct"] is not None:
        winners = snap["tally"][snap["correct"]]
        say(
            f"Правильный ответ — {snap['options'][snap['correct']]}. "
            f"Угадали {winners} {plural(winners, 'человек', 'человека', 'человек')}. Аплодисменты!",
            kind="quiz", priority=2,
        )
    return jsonify(snap)


@app.route("/api/leaderboard")
def api_leaderboard():
    return jsonify({"rows": EVENT.leaderboard()})


# ---------------------------------------------------------------- демо-режим

@app.route("/api/demo/guests", methods=["POST"])
@require_admin
def api_demo_guests():
    """Наливаем выдуманных гостей — репетиция без живых людей."""
    d = request.get_json(force=True, silent=True) or {}
    count = max(1, min(int(d.get("count", 5)), 40))
    greet = bool(d.get("greet", False))
    added = []
    pool = list(DEMO_NAMES)
    random.shuffle(pool)
    for i in range(count):
        base = pool[i % len(pool)]
        name = base if i < len(pool) else f"{base} {i // len(pool) + 1}"
        guest, err = EVENT.add_guest(name, table=f"стол {i % 6 + 1}")
        if guest:
            guest["demo"] = True
            added.append(guest["name"])
            if greet:
                greet_guest(guest)
    return jsonify({"added": added, "count": EVENT.guest_count})


@app.route("/api/demo/answers", methods=["POST"])
@require_admin
def api_demo_answers():
    """Демо-гости отвечают на текущий вопрос."""
    snap = EVENT.quiz_public()
    if not snap or not snap["open"]:
        return jsonify({"error": "Конкурс не запущен"}), 400
    n = 0
    for token, g in list(EVENT.guests.items()):
        if g.get("demo") and random.random() < 0.85:
            EVENT.answer_quiz(token, random.randrange(len(snap["options"])))
            n += 1
    return jsonify({"answered": n, "quiz": EVENT.quiz_public()})


# ---------------------------------------------------------------- сценарии

RUNNER = scenario_mod.Runner(EVENT, say, greet_guest)
SCENARIO_DIR = os.path.join(BASE_DIR, "scenarios")


@app.route("/api/scenario/list")
@require_admin
def api_scenario_list():
    """Готовые файлы, лежащие в scenarios/."""
    files = []
    if os.path.isdir(SCENARIO_DIR):
        for name in sorted(os.listdir(SCENARIO_DIR)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(SCENARIO_DIR, name), encoding="utf-8") as f:
                    meta = (json.load(f).get("meta") or {})
                files.append({"file": name, "title": meta.get("title", name),
                              "duration_min": meta.get("duration_min")})
            except Exception:
                files.append({"file": name, "title": name + " (ошибка чтения)"})
    return jsonify({"files": files})


@app.route("/api/scenario/load", methods=["POST"])
@require_admin
def api_scenario_load():
    """Загрузка сценария: файлом (multipart), телом JSON или именем из scenarios/."""
    try:
        upload = request.files.get("file")
        if upload:
            text, name = upload.read().decode("utf-8"), upload.filename
        else:
            d = request.get_json(force=True, silent=True) or {}
            if d.get("file"):
                name = os.path.basename(d["file"])
                path = os.path.join(SCENARIO_DIR, name)
                if not os.path.isfile(path):
                    return jsonify({"error": "Файл не найден"}), 404
                text = open(path, encoding="utf-8").read()
            elif d.get("content"):
                text, name = d["content"], d.get("filename", "сценарий.json")
            else:
                return jsonify({"error": "Нужен файл, content или имя file"}), 400
        sc = RUNNER.load(text, name)
    except scenario_mod.ScenarioError as e:
        return jsonify({"error": str(e)}), 400
    except UnicodeDecodeError:
        return jsonify({"error": "Файл должен быть в кодировке UTF-8"}), 400

    meta = sc["meta"]
    with EVENT.lock:
        EVENT.title = meta.get("title", EVENT.title)
        EVENT.subtitle = meta.get("subtitle", EVENT.subtitle)
        if meta.get("voice") in [v["id"] for v in tts.VOICES]:
            EVENT.voice = meta["voice"]
        EVENT.rate = int(meta.get("rate", EVENT.rate))
        EVENT.pitch = int(meta.get("pitch", EVENT.pitch))
    EVENT.bus.publish("state", EVENT.snapshot())
    EVENT.bus.publish("scenario_state", RUNNER.state())
    return jsonify(RUNNER.state())


@app.route("/api/scenario/state")
def api_scenario_state():
    return jsonify(RUNNER.state())


@app.route("/api/scenario/<action>", methods=["POST"])
@require_admin
def api_scenario_action(action):
    d = request.get_json(force=True, silent=True) or {}
    try:
        if action == "next":
            return jsonify(RUNNER.next_step())
        if action == "repeat":
            return jsonify(RUNNER.repeat())
        if action == "skip":
            return jsonify(RUNNER.skip())
        if action == "stop":
            return jsonify(RUNNER.stop())
        if action == "goto":
            return jsonify(RUNNER.goto(int(d.get("index", 0))))
        if action == "unload":
            RUNNER.unload()
            return jsonify(RUNNER.state())
    except scenario_mod.ScenarioError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"error": "Неизвестное действие"}), 404


# ---------------------------------------------------------------- пожелания

@app.route("/api/collect/add", methods=["POST"])
def api_collect_add():
    d = request.get_json(force=True, silent=True) or {}
    count, err = EVENT.add_wish((d.get("token") or "").strip(), d.get("text", ""))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "count": count})


@app.route("/api/collect/close", methods=["POST"])
@require_admin
def api_collect_close():
    """Закрыть сбор и зачитать несколько пожеланий вслух."""
    with EVENT.lock:
        c = EVENT.collect
        if not c:
            return jsonify({"error": "Сбор не запущен"}), 400
        c["open"] = False
        items = list(c["items"])
        n = c.get("read_aloud", 0)
    EVENT.bus.publish("collect", EVENT.collect_public())
    if n and items:
        for it in random.sample(items, min(n, len(items))):
            say(f"{it['name']} желает: {it['text']}", kind="say", priority=3)
    return jsonify({"ok": True, "total": len(items)})


@app.route("/api/collect/items")
@require_admin
def api_collect_items():
    with EVENT.lock:
        c = EVENT.collect
        items = [{"name": i["name"], "text": i["text"]} for i in c["items"]] if c else []
    return jsonify({"items": items})


SCENARIO_STATE = {"running": False, "step": "", "log": []}


def scenario_log(step):
    SCENARIO_STATE["step"] = step
    SCENARIO_STATE["log"].append({"at": time.time(), "step": step})
    EVENT.bus.publish("scenario", {"step": step, "running": SCENARIO_STATE["running"]})


def wait_quiet(timeout=90):
    """Ждём, пока аватар договорит всю очередь."""
    end = time.time() + timeout
    while time.time() < end:
        snap = EVENT.queue_snapshot()
        if not snap["pending"] and not snap["speaking"]:
            return True
        time.sleep(0.3)
    return False


def run_scenario(fast=False):
    """Сценарий выдуманного вечера — юбилей. Прогон целиком, без людей."""
    pause = (lambda s: time.sleep(0.2 if fast else s))
    try:
        SCENARIO_STATE["running"] = True
        SCENARIO_STATE["log"] = []
        EVENT.reset()

        with EVENT.lock:
            EVENT.title = "Юбилей Марии Петровны — 50 лет"
            EVENT.subtitle = "Сканируйте QR и представьтесь"
            EVENT.greeting_template = "{name}, добро пожаловать! Мария Петровна вас уже ждёт."
            EVENT.phase = "welcome"
        EVENT.bus.publish("state", EVENT.snapshot())

        scenario_log("1. Сбор гостей")
        say("Добрый вечер! Я ваш электронный ведущий. Отсканируйте QR-код на экране "
            "и представьтесь — я поздороваюсь с каждым лично.", kind="say", priority=3)
        wait_quiet()

        scenario_log("2. Гости заходят и получают приветствие")
        pool = list(DEMO_NAMES)
        random.shuffle(pool)
        for i, name in enumerate(pool[:6]):
            guest, err = EVENT.add_guest(name, table=f"стол {i % 3 + 1}")
            if guest:
                guest["demo"] = True
                greet_guest(guest)
            pause(1.2)   # гости заходят внахлёст — проверяем очередь
        wait_quiet()

        scenario_log("3. Официальное открытие")
        with EVENT.lock:
            EVENT.phase = "welcome"
            EVENT.accepting = False
        EVENT.bus.publish("state", EVENT.snapshot())
        n = EVENT.guest_count
        say(f"Все в сборе: сегодня с нами {n} {plural(n, 'гость', 'гостя', 'гостей')}. "
            "Прошу поднять бокалы за нашу именинницу!", priority=3)
        wait_quiet()

        scenario_log("4. Конкурс: вопрос про именинницу")
        EVENT.start_quiz(
            "В каком городе Мария Петровна встретила своего мужа?",
            ["Казань", "Йошкар-Ола", "Сочи"], seconds=20,
        )
        say("Внимание, конкурс! В каком городе Мария Петровна встретила своего мужа? "
            "Варианты: А — Казань, Б — Йошкар-Ола, В — Сочи.", kind="quiz", priority=2)
        wait_quiet()
        for token, g in list(EVENT.guests.items()):
            if g.get("demo"):
                EVENT.answer_quiz(token, random.choice([0, 1, 1, 1, 2]))
                pause(0.4)
        snap = EVENT.close_quiz(correct=1)
        w = snap['tally'][1]
        say(f"Правильный ответ — Йошкар-Ола! Угадали {w} {plural(w, 'человек', 'человека', 'человек')}.",
            kind="quiz", priority=2)
        wait_quiet()

        scenario_log("5. Итоги и финал")
        with EVENT.lock:
            EVENT.phase = "finale"
        top = EVENT.leaderboard(3)
        if top:
            say("Лидеры нашего вечера: " + ", ".join(
                f"{r['name']} — {r['score']}" for r in top) + ".", priority=3)
        say("Спасибо, что были сегодня с нами! Танцпол открыт, а я остаюсь на связи.",
            priority=3)
        wait_quiet()
        scenario_log("Готово")
    except Exception as e:
        scenario_log(f"Ошибка сценария: {e}")
    finally:
        SCENARIO_STATE["running"] = False
        EVENT.bus.publish("scenario", {"step": SCENARIO_STATE["step"], "running": False})


@app.route("/api/demo/scenario", methods=["POST"])
@require_admin
def api_demo_scenario():
    if SCENARIO_STATE["running"]:
        return jsonify({"error": "Сценарий уже идёт"}), 409
    fast = bool((request.get_json(force=True, silent=True) or {}).get("fast"))
    threading.Thread(target=run_scenario, args=(fast,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/demo/scenario/state")
def api_demo_scenario_state():
    return jsonify(SCENARIO_STATE)


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True, "build": BUILD, "listeners": EVENT.bus.listeners,
        "engine_note": tts.engine_note(), "guests": EVENT.guest_count,
        "queue": EVENT.queue_snapshot(),
    })


PORT = int(os.environ.get("PORT", 8000))

if __name__ == "__main__":
    print(netinfo.banner(PORT, BUILD, EVENT.code, ADMIN_PIN))
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
