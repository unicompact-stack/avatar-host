# -*- coding: utf-8 -*-
"""
Состояние мероприятия + очередь речи + шина событий (SSE).

Почему так:
- BroadcastChannel работал только между вкладками одного браузера — теперь
  админка живёт на планшете, экран на проекторе, гости на телефонах.
- Очередь речи серверная: два гостя зашли одновременно — реплики не наложатся.
"""
import time
import queue
import secrets
import threading

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(5))


def new_token() -> str:
    return secrets.token_hex(16)


class EventBus:
    """Простейший pub/sub поверх очередей — под SSE."""

    def __init__(self):
        self._subs = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=200)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: str, payload=None):
        msg = {"event": event, "data": payload or {}, "ts": time.time()}
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._subs)


class Event:
    """Одно мероприятие. In-memory, но со снапшотом для восстановления экрана."""

    PHASES = ("idle", "welcome", "greeting", "quiz", "finale")

    def __init__(self):
        self.lock = threading.RLock()
        self.bus = EventBus()
        self.reset(full=True)

    # --- жизненный цикл ---
    def reset(self, full=False):
        with self.lock:
            self.code = new_code()
            self.guests = {}          # token -> dict
            self.sessions = {}        # session token -> {guest_token}
            self.accepting = True
            self.phase = "idle"
            self.title = "Юбилей Марии Петровны — 50 лет"
            self.subtitle = "Сканируйте QR и представьтесь"
            self.greeting_template = "{name}, добро пожаловать! Рад видеть вас на нашем вечере."
            self.guest_limit = 60
            self.voice = "ru-RU-DmitryNeural"
            self.rate = 0
            self.pitch = 0
            self.speech_queue = []    # список реплик
            self.now_speaking = None
            self.history = []
            self.quiz = None
            self.collect = None      # сбор пожеланий с телефонов
            self.started_at = time.time()
            if not full:
                self.bus.publish("reset", {})

    # --- гости ---
    def add_guest(self, name: str, table: str = ""):
        with self.lock:
            if not self.accepting:
                return None, "Приём гостей закрыт"
            if len(self.guests) >= self.guest_limit:
                return None, "Достигнут лимит гостей"
            low = name.strip().lower()
            if not low:
                return None, "Введите имя"
            for g in self.guests.values():
                if g["name"].lower() == low:
                    return None, "Это имя уже занято — добавьте фамилию или инициал"
            token = new_token()
            self.guests[token] = {
                "token": token,
                "name": name.strip(),
                "table": table.strip(),
                "joined_at": time.time(),
                "greeted": False,
                "score": 0,
                "answers": {},
                "demo": False,
            }
            guest = self.guests[token]
        self.bus.publish("guest_joined", {"guest": public_guest(guest), "count": self.guest_count})
        return guest, None

    @property
    def guest_count(self):
        return len(self.guests)

    def guest_list(self):
        with self.lock:
            items = [public_guest(g) for g in self.guests.values()]
        items.sort(key=lambda g: g["joined_at"])
        return items

    # --- очередь речи ---
    def enqueue(self, item: dict):
        with self.lock:
            item.setdefault("id", new_token()[:8])
            item.setdefault("kind", "say")
            item.setdefault("priority", 5)
            item.setdefault("queued_at", time.time())
            self.speech_queue.append(item)
            # меньший priority — раньше (приветствия важнее болтовни)
            self.speech_queue.sort(key=lambda i: (i["priority"], i["queued_at"]))
        self.bus.publish("queue", self.queue_snapshot())
        return item

    def pop_next(self):
        with self.lock:
            if self.now_speaking or not self.speech_queue:
                return None
            item = self.speech_queue.pop(0)
            self.now_speaking = item
        return item

    def finish_current(self, item_id=None):
        with self.lock:
            cur = self.now_speaking
            if cur and item_id and cur["id"] != item_id:
                return None
            self.now_speaking = None
            if cur:
                self.history.append({"text": cur.get("text", ""), "at": time.time()})
                self.history = self.history[-50:]
        self.bus.publish("queue", self.queue_snapshot())
        return cur

    def queue_snapshot(self):
        with self.lock:
            return {
                "pending": [
                    {"id": i["id"], "text": i.get("text", ""), "kind": i["kind"]}
                    for i in self.speech_queue
                ],
                "speaking": (
                    {"id": self.now_speaking["id"], "text": self.now_speaking.get("text", "")}
                    if self.now_speaking
                    else None
                ),
            }

    def snapshot(self):
        with self.lock:
            return {
                "code": self.code,
                "title": self.title,
                "subtitle": self.subtitle,
                "phase": self.phase,
                "accepting": self.accepting,
                "guest_count": len(self.guests),
                "guest_limit": self.guest_limit,
                "greeting_template": self.greeting_template,
                "voice": self.voice,
                "rate": self.rate,
                "pitch": self.pitch,
                "quiz": self.quiz_public(),
                "collect": self.collect_public(),
                "queue": self.queue_snapshot(),
                "guests": self.guest_list(),
                "uptime": round(time.time() - self.started_at),
            }

    # --- конкурс ---
    def start_quiz(self, question, options, seconds=30):
        with self.lock:
            self.quiz = {
                "id": new_token()[:8],
                "question": question,
                "options": options,
                "seconds": seconds,
                "started_at": time.time(),
                "open": True,
                "answers": {},   # guest_token -> index
                "correct": None,
            }
            self.phase = "quiz"
            snap = self.quiz_public()
        self.bus.publish("quiz_started", snap)
        return snap

    def answer_quiz(self, guest_token, index):
        with self.lock:
            if not self.quiz or not self.quiz["open"]:
                return None, "Приём ответов закрыт"
            if guest_token not in self.guests:
                return None, "Гость не найден"
            if not (0 <= index < len(self.quiz["options"])):
                return None, "Нет такого варианта"
            self.quiz["answers"][guest_token] = index
            snap = self.quiz_public()
        self.bus.publish("quiz_progress", snap)
        return snap, None

    def close_quiz(self, correct=None):
        with self.lock:
            if not self.quiz:
                return None
            self.quiz["open"] = False
            self.quiz["correct"] = correct
            if correct is not None:
                for token, idx in self.quiz["answers"].items():
                    if idx == correct and token in self.guests:
                        self.guests[token]["score"] += 1
            snap = self.quiz_public()
        self.bus.publish("quiz_closed", snap)
        return snap

    def quiz_public(self):
        q = self.quiz
        if not q:
            return None
        tally = [0] * len(q["options"])
        for idx in q["answers"].values():
            tally[idx] += 1
        return {
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
            "seconds": q["seconds"],
            "started_at": q["started_at"],
            "open": q["open"],
            "answered": len(q["answers"]),
            "tally": tally,
            "correct": q["correct"],
        }

    # --- сбор пожеланий ---
    def add_wish(self, guest_token, text):
        with self.lock:
            if not self.collect or not self.collect["open"]:
                return None, "Сбор пожеланий закрыт"
            g = self.guests.get(guest_token)
            if not g:
                return None, "Гость не найден"
            text = (text or "").strip()[:300]
            if not text:
                return None, "Пустое пожелание"
            self.collect["items"] = [i for i in self.collect["items"] if i["token"] != guest_token]
            self.collect["items"].append({"token": guest_token, "name": g["name"], "text": text})
            count = len(self.collect["items"])
        self.bus.publish("collect", {"prompt": self.collect["prompt"], "open": True, "count": count})
        return count, None

    def collect_public(self):
        c = self.collect
        if not c:
            return None
        return {"prompt": c["prompt"], "open": c["open"], "count": len(c["items"])}

    def leaderboard(self, top=10):
        with self.lock:
            rows = [
                {"name": g["name"], "score": g["score"], "demo": g["demo"]}
                for g in self.guests.values()
            ]
        rows.sort(key=lambda r: (-r["score"], r["name"]))
        return rows[:top]


def public_guest(g):
    return {
        "token": g["token"],
        "name": g["name"],
        "table": g.get("table", ""),
        "joined_at": g["joined_at"],
        "greeted": g["greeted"],
        "score": g.get("score", 0),
        "demo": g.get("demo", False),
    }


EVENT = Event()
