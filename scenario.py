# -*- coding: utf-8 -*-
"""
Движок сценариев: загрузка .json, валидация, подстановки, пошаговое исполнение.

Принцип — автопилот с ручным подтверждением: шаг отрабатывает и ЖДЁТ кнопки
«Далее», потому что вечер живой. Где уместно — auto_next: true.
"""
import json
import re
import threading
import time

FORMAT = "avatar-host-scenario"
STEP_TYPES = {"say", "greet_guests", "quiz", "poll", "collect", "pause", "handoff",
              "settings", "stage"}
STAGE_MODES = ("avatar", "media", "celebration", "black")


class ScenarioError(ValueError):
    pass


def plural(n, one, few, many):
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def validate(data):
    """Проверяем файл и возвращаем нормализованный сценарий."""
    if not isinstance(data, dict):
        raise ScenarioError("Файл должен содержать JSON-объект")
    if data.get("format") != FORMAT:
        raise ScenarioError(f'Поле "format" должно быть "{FORMAT}"')
    if int(data.get("version", 0)) != 1:
        raise ScenarioError('Поддерживается только "version": 1')

    meta = data.get("meta") or {}
    if not isinstance(meta, dict) or not str(meta.get("title", "")).strip():
        raise ScenarioError('В "meta" нужен непустой "title"')

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScenarioError('Нужен непустой список "steps"')

    seen = set()
    norm = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            raise ScenarioError(f"Шаг {i}: должен быть объектом")
        t = s.get("type")
        if t not in STEP_TYPES:
            raise ScenarioError(f"Шаг {i}: неизвестный type «{t}». Доступно: {', '.join(sorted(STEP_TYPES))}")
        sid = str(s.get("id") or f"step{i}")
        if sid in seen:
            raise ScenarioError(f"Шаг {i}: повторяющийся id «{sid}»")
        seen.add(sid)

        if t in ("say", "pause", "handoff") and not str(s.get("text", "")).strip():
            raise ScenarioError(f"Шаг {i} ({sid}): нужен непустой «text»")
        if t == "poll":
            if not str(s.get("question", "")).strip():
                raise ScenarioError(f"Шаг {i} ({sid}): нужен «question»")
            if len(s.get("options") or []) < 2:
                raise ScenarioError(f"Шаг {i} ({sid}): нужно минимум 2 варианта")
        if t == "quiz":
            qs = s.get("questions") or []
            if not qs:
                raise ScenarioError(f"Шаг {i} ({sid}): нужен непустой «questions»")
            for j, q in enumerate(qs, 1):
                if not str(q.get("q", "")).strip():
                    raise ScenarioError(f"Шаг {i} ({sid}), вопрос {j}: пустой текст")
                opts = q.get("options") or []
                if len(opts) < 2:
                    raise ScenarioError(f"Шаг {i} ({sid}), вопрос {j}: нужно минимум 2 варианта")
                c = q.get("correct")
                if c is not None and not (0 <= int(c) < len(opts)):
                    raise ScenarioError(f"Шаг {i} ({sid}), вопрос {j}: «correct» вне диапазона")
        if t == "stage":
            m = s.get("mode", "avatar")
            if m not in STAGE_MODES:
                raise ScenarioError(f"Шаг {i} ({sid}): mode должен быть одним из {', '.join(STAGE_MODES)}")
            if m == "media" and not str(s.get("media", "")).strip():
                raise ScenarioError(f"Шаг {i} ({sid}): для mode=media нужно имя файла в «media»")
        if t == "collect" and not str(s.get("prompt", "")).strip():
            raise ScenarioError(f"Шаг {i} ({sid}): нужен «prompt»")

        s = dict(s)
        s["id"] = sid
        s["title"] = str(s.get("title") or sid)
        s["auto_next"] = bool(s.get("auto_next", False))
        norm.append(s)

    return {
        "format": FORMAT,
        "version": 1,
        "meta": meta,
        "vars": data.get("vars") or {},
        "steps": norm,
    }


def load_json(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ScenarioError(f"Файл не является корректным JSON: строка {e.lineno}, {e.msg}")
    return validate(data)


class Runner:
    """Исполнитель сценария поверх EVENT. Ничего не знает про Flask."""

    def __init__(self, event, say, greet_guest):
        self.event = event
        self._say = say
        self._greet = greet_guest
        self.lock = threading.RLock()
        self.scenario = None
        self.filename = ""
        self.index = -1          # текущий шаг, -1 = не начат
        self.status = "empty"    # empty | ready | running | waiting | done
        self.quiz_pos = 0        # номер вопроса внутри quiz-шага
        self.log = []

    # ---------- загрузка ----------
    def load(self, text, filename=""):
        sc = load_json(text)
        with self.lock:
            self.scenario = sc
            self.filename = filename
            self.index = -1
            self.quiz_pos = 0
            self.status = "ready"
            self.log = []
        return sc

    def unload(self):
        with self.lock:
            self.scenario = None
            self.filename = ""
            self.index = -1
            self.status = "empty"

    # ---------- подстановки ----------
    def fill(self, text, extra=None):
        if not text:
            return ""
        vals = {}
        meta = (self.scenario or {}).get("meta", {})
        vals.update((self.scenario or {}).get("vars", {}))
        vals["hero"] = meta.get("hero", "")
        n = self.event.guest_count
        vals["count"] = f"{n} {plural(n, 'гость', 'гостя', 'гостей')}"
        top = self.event.leaderboard(3)
        vals["leaders"] = ", ".join(f"{r['name']} — {r['score']}" for r in top) or "пока никого"
        vals["title"] = meta.get("title", "")
        if extra:
            vals.update(extra)
        return re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), str(text))

    # ---------- навигация ----------
    def steps(self):
        return (self.scenario or {}).get("steps", [])

    def current(self):
        st = self.steps()
        return st[self.index] if 0 <= self.index < len(st) else None

    def state(self):
        with self.lock:
            st = self.steps()
            cur = self.current()
            return {
                "loaded": self.scenario is not None,
                "filename": self.filename,
                "meta": (self.scenario or {}).get("meta", {}),
                "status": self.status,
                "index": self.index,
                "total": len(st),
                "current": {"id": cur["id"], "title": cur["title"], "type": cur["type"]} if cur else None,
                "quiz_pos": self.quiz_pos,
                "steps": [
                    {"id": s["id"], "title": s["title"], "type": s["type"],
                     "auto_next": s["auto_next"],
                     "state": "done" if i < self.index else ("current" if i == self.index else "pending")}
                    for i, s in enumerate(st)
                ],
                "log": self.log[-20:],
            }

    def _publish(self):
        self.event.bus.publish("scenario_state", self.state())

    def next_step(self):
        """Перейти к следующему шагу и выполнить его."""
        with self.lock:
            if not self.scenario:
                raise ScenarioError("Сценарий не загружен")
            cur = self.current()
            # внутри quiz-шага идём по вопросам
            if cur and cur["type"] == "quiz" and self.quiz_pos < len(cur["questions"]):
                return self._run_quiz_question(cur)
            if self.index + 1 >= len(self.steps()):
                self.status = "done"
                self._publish()
                return self.state()
            self.index += 1
            self.quiz_pos = 0
        return self._execute(self.current())

    def goto(self, index):
        with self.lock:
            if not self.scenario:
                raise ScenarioError("Сценарий не загружен")
            if not (0 <= index < len(self.steps())):
                raise ScenarioError("Нет такого шага")
            self.index = index
            self.quiz_pos = 0
        return self._execute(self.current())

    def repeat(self):
        cur = self.current()
        if not cur:
            raise ScenarioError("Нет текущего шага")
        with self.lock:
            self.quiz_pos = max(0, self.quiz_pos - 1) if cur["type"] == "quiz" else 0
        return self._execute(cur)

    def skip(self):
        with self.lock:
            if not self.scenario:
                raise ScenarioError("Сценарий не загружен")
            if self.index + 1 >= len(self.steps()):
                self.status = "done"
                self._publish()
                return self.state()
            self.index += 1
            self.quiz_pos = 0
            self.status = "waiting"
            self._publish()
            return self.state()

    def stop(self):
        with self.lock:
            self.status = "ready"
            self.index = -1
            self.quiz_pos = 0
            self._publish()
            return self.state()

    # ---------- исполнение ----------
    def _note(self, msg):
        self.log.append({"at": time.time(), "text": msg})

    def _execute(self, step):
        t = step["type"]
        ev = self.event
        self.status = "running"

        if t == "settings" or "phase" in step or "accepting" in step:
            with ev.lock:
                if step.get("phase") in ev.PHASES:
                    ev.phase = step["phase"]
                if "accepting" in step:
                    ev.accepting = bool(step["accepting"])
                if step.get("voice"):
                    ev.voice = step["voice"]
            ev.bus.publish("state", ev.snapshot())

        # любой шаг может попутно переключить экран
        if t == "stage" or "stage" in step:
            sp = step.get("stage") if isinstance(step.get("stage"), dict) else step
            item = None
            name = sp.get("media")
            if name:
                import media as media_mod
                item = media_mod.info(media_mod.safe_name(name))
                if not item:
                    self._note(f"Файл «{name}» не найден в медиатеке")
            ev.set_stage(mode=sp.get("mode"), media=item if name else None,
                         page=sp.get("page"), celebration=sp.get("celebration"),
                         caption=sp.get("caption"))

        if t == "stage":
            if step.get("text"):
                self._say(self.fill(step["text"]), kind="say", priority=3)
            self._note(f"Экран: {step.get('mode', 'avatar')}")

        elif t == "say":
            self._say(self.fill(step["text"]), kind="say", priority=3)
            self._note(f"Реплика: {step['title']}")

        elif t == "greet_guests":
            # {name} подставит greet_guest, остальное раскрываем здесь
            tpl = self.fill(step.get("template") or ev.greeting_template, {"name": "{name}"})
            with ev.lock:
                ev.greeting_template = tpl
            pending = [g for g in ev.guests.values() if not g["greeted"]]
            for g in pending:
                self._greet(g)
            self._note(f"Приветствий: {len(pending)}")

        elif t == "pause":
            self._say(self.fill(step["text"]), kind="say", priority=3)
            self._note(f"Пауза {step.get('minutes', '')} мин")

        elif t == "handoff":
            self._say(self.fill(step["text"]), kind="say", priority=3)
            self._note("Слово живому человеку")

        elif t == "poll":
            ev.start_quiz(self.fill(step["question"]),
                          [self.fill(o) for o in step["options"]],
                          int(step.get("seconds", 30)))
            intro = step.get("intro") or step["question"]
            letters = "АБВГДЕ"
            spoken = self.fill(intro) + " Варианты: " + "; ".join(
                f"{letters[i]} — {self.fill(o)}" for i, o in enumerate(step["options"])
            ) + ". Отвечайте на телефонах!"
            self._say(spoken, kind="quiz", priority=2)
            self._note(f"Опрос: {step['title']}")

        elif t == "quiz":
            if step.get("intro") and self.quiz_pos == 0:
                self._say(self.fill(step["intro"]), kind="quiz", priority=2)
            return self._run_quiz_question(step)

        elif t == "collect":
            with ev.lock:
                ev.collect = {"prompt": self.fill(step["prompt"]),
                              "read_aloud": int(step.get("read_aloud", 0)),
                              "open": True, "items": []}
            ev.bus.publish("collect", {"prompt": ev.collect["prompt"], "open": True, "count": 0})
            self._say(self.fill(step.get("intro") or step["prompt"]), kind="say", priority=3)
            self._note("Сбор пожеланий открыт")

        self.status = "waiting"
        self._publish()
        result = self.state()
        if step["auto_next"] and t != "quiz":
            threading.Thread(target=self._auto_advance, daemon=True).start()
        return result

    def _run_quiz_question(self, step):
        """Один вопрос викторины: предыдущий закрываем, следующий открываем."""
        ev = self.event
        qs = step["questions"]

        # закрыть предыдущий вопрос и объявить итог
        if self.quiz_pos > 0 and ev.quiz and ev.quiz["open"]:
            prev = qs[self.quiz_pos - 1]
            snap = ev.close_quiz(prev.get("correct"))
            if snap and snap["correct"] is not None:
                w = snap["tally"][snap["correct"]]
                outro = step.get("outro") or "Правильный ответ — {correct}. Угадали {winners}!"
                self._say(self.fill(outro, {
                    "correct": snap["options"][snap["correct"]],
                    "winners": f"{w} {plural(w, 'человек', 'человека', 'человек')}",
                }), kind="quiz", priority=2)

        if self.quiz_pos >= len(qs):
            self.status = "waiting"
            self._publish()
            return self.state()

        q = qs[self.quiz_pos]
        options = [self.fill(o) for o in q["options"]]
        ev.start_quiz(self.fill(q["q"]), options, int(q.get("seconds", step.get("seconds", 30))))
        letters = "АБВГДЕ"
        self._say(self.fill(q["q"]) + " Варианты: " + "; ".join(
            f"{letters[i]} — {o}" for i, o in enumerate(options)) + ".",
            kind="quiz", priority=2)
        self.quiz_pos += 1
        self._note(f"Вопрос {self.quiz_pos} из {len(qs)}")
        self.status = "waiting"
        self._publish()
        return self.state()

    def _auto_advance(self):
        """Ждём тишины и сами идём дальше — для шагов с auto_next."""
        end = time.time() + 180
        while time.time() < end:
            q = self.event.queue_snapshot()
            if not q["pending"] and not q["speaking"]:
                break
            time.sleep(0.3)
        try:
            if self.status == "waiting":
                self.next_step()
        except ScenarioError:
            pass
