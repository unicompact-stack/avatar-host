# -*- coding: utf-8 -*-
"""
Движок конкурсов.

Идея: один активный конкурс на мероприятие. Конкурс — это словарь с типом,
настройками, приёмом ответов от гостей и «публичной» проекцией для экрана
и телефонов. Логика каждого типа живёт в трёх функциях: start / submit / action.

Почему так, а не отдельный класс на игру: конкурсы очень разные по механике,
но одинаковые по жизненному циклу (запустили → собрали → показали итог).
Словарь + диспетчер дают меньше кода, чем иерархия классов.

Команды — это столы. Счёт вечера накапливается между конкурсами.
"""
import random
import secrets
import time

NO_TABLE = "Без стола"


def new_id():
    return secrets.token_hex(4)


# --------------------------------------------------------------------------
# Каталог: что видит ведущий в пульте
# --------------------------------------------------------------------------
CATALOG = [
    {
        "type": "wordcloud",
        "title": "Облако слов",
        "desc": "Один вопрос — одно слово от каждого. Чем чаще слово, тем крупнее.",
        "phone": True,
        "minutes": "3–5",
        "tags": ["Разогрев", "Весь зал"],
    },
    {
        "type": "taprace",
        "title": "Гонка столов",
        "desc": "Гости жмут кнопку на телефонах, дорожки команд едут к финишу.",
        "phone": True,
        "minutes": "2–3",
        "tags": ["Командный", "Динамика"],
    },
    {
        "type": "bets",
        "title": "Ставки вечера",
        "desc": "Зал спорит на фишки, что случится дальше. Банк делится между угадавшими.",
        "phone": True,
        "minutes": "5–10",
        "tags": ["Весь зал", "Несколько кругов"],
    },
    {
        "type": "bingo",
        "title": "Бинго вечера",
        "desc": "У каждого карточка с предсказаниями. Событие случилось — ведущий отмечает.",
        "phone": True,
        "minutes": "весь вечер",
        "tags": ["Фоновый", "Весь зал"],
    },
    {
        "type": "numbers",
        "title": "Цифры вечера",
        "desc": "Закрытые карточки с числами из жизни героя. Зал гадает, что они значат.",
        "phone": False,
        "minutes": "5–8",
        "tags": ["Ведёте вы", "Трогательный"],
    },
    {
        "type": "toast",
        "title": "Тост-конструктор",
        "desc": "Гостю выпадает, за кого говорить, в каком стиле и что упомянуть.",
        "phone": False,
        "minutes": "5–10",
        "tags": ["Ведёте вы", "Вместо скучных тостов"],
    },
    {
        "type": "dancewheel",
        "title": "Колесо танцев",
        "desc": "Колесо выбирает танец: ламбада, твист, «Макарена». Дальше — музыка.",
        "phone": False,
        "minutes": "3–5",
        "tags": ["Ведёте вы", "Разгон танцпола"],
    },
    {
        "type": "noise",
        "title": "Шумомер",
        "desc": "Столы по очереди заряжают шкалу криком. Микрофон ноутбука у экрана.",
        "phone": False,
        "minutes": "3–5",
        "tags": ["Командный", "Нужен микрофон"],
    },
]

CATALOG_BY_TYPE = {g["type"]: g for g in CATALOG}


# --------------------------------------------------------------------------
# Заготовки содержания — чтобы конкурс запускался одной кнопкой
# --------------------------------------------------------------------------
WORDCLOUD_PROMPTS = [
    "Опишите героя вечера одним словом",
    "Какое слово у вас ассоциируется с сегодняшним вечером?",
    "Одно слово-пожелание имениннику",
    "Каким было это лето одним словом?",
]

BINGO_POOL = [
    "Кто-то сказал тост длиннее трёх минут",
    "Именинника назвали не по имени",
    "Кто-то уронил вилку",
    "Заиграла песня, которую знают все",
    "Кто-то полез обниматься",
    "Прозвучало слово «коллектив»",
    "Кто-то сфотографировал стол",
    "Именинник сказал «ну не надо было»",
    "Кто-то вспомнил, как всё начиналось",
    "Гость ушёл курить посреди тоста",
    "Кто-то запел вместе с музыкой",
    "Прозвучал тост «за родителей»",
    "Кто-то попросил сделать музыку тише",
    "Кто-то станцевал первым",
    "Кто-то сказал «я коротко»",
    "На столе закончился салат",
    "Кто-то произнёс «горько» не на свадьбе",
    "Гость перепутал имя другого гостя",
    "Кто-то показал фото в телефоне всему столу",
    "Прозвучала шутка про возраст",
]

BETS_QUESTIONS = [
    {
        "question": "Сколько минут продлится следующий тост?",
        "options": ["Меньше минуты", "1–3 минуты", "Больше трёх минут"],
    },
    {
        "question": "Кто первым выйдет танцевать?",
        "options": ["Мужчина", "Женщина", "Сразу компания"],
    },
    {
        "question": "Что скажет именинник в ответном слове?",
        "options": ["«Спасибо, что пришли»", "«Я не готовился»", "Расскажет историю"],
    },
]

TOAST_PARTS = {
    "who": [
        "за героя вечера",
        "за родителей героя вечера",
        "за тех, кто приехал издалека",
        "за друзей, которые рядом много лет",
        "за тех, кто сегодня не смог прийти",
        "за хозяев стола",
        "за случайности, которые нас свели",
    ],
    "tone": [
        "как диктор советского телевидения",
        "шёпотом, как страшную тайну",
        "как спортивный комментатор",
        "с невероятным пафосом",
        "как будто вы очень спешите",
        "как тост из старого кино",
        "совершенно серьёзно, без улыбки",
    ],
    "detail": [
        "упомяните картошку",
        "вставьте слово «алгоритм»",
        "обязательно скажите про понедельник",
        "упомяните школьный звонок",
        "используйте слово «километр»",
        "вставьте название любого города",
        "скажите про чай с сахаром",
    ],
    "finish": [
        "закончите словами «и пусть так будет всегда»",
        "закончите вопросом к залу",
        "закончите на три тона выше, чем начали",
        "закончите словами «а теперь пьём»",
        "закончите пожеланием здоровья",
    ],
}

DANCES = [
    {"name": "Ламбада", "hint": "Встаём паровозиком"},
    {"name": "Макарена", "hint": "Руки вперёд, все знают"},
    {"name": "Твист", "hint": "Носком по полу, как в 60-е"},
    {"name": "Медленный танец", "hint": "Приглашаем соседа по столу"},
    {"name": "Цыганочка", "hint": "Плечи работают"},
    {"name": "Робот", "hint": "Двигаемся по кадрам"},
    {"name": "Летка-енка", "hint": "Прыжки в цепочке"},
    {"name": "Танец маленьких утят", "hint": "Да, придётся"},
    {"name": "Рок-н-ролл", "hint": "Кто помнит — показывает"},
    {"name": "Свободный стиль", "hint": "Что угодно, 20 секунд славы"},
]

NUMBERS_EXAMPLE = [
    {"n": "38", "text": "столько лет сегодня герою вечера"},
    {"n": "7", "text": "столько лет он работает в школе"},
    {"n": "1 200", "text": "примерно столько тетрадей он проверяет за год"},
    {"n": "4", "text": "столько раз он забывал телефон дома в этом месяце"},
    {"n": "2", "text": "столько чашек кофе нужно ему до первого урока"},
]


# --------------------------------------------------------------------------
# Команды (столы)
# --------------------------------------------------------------------------
def team_of(guest):
    """Команда гостя = его стол.

    Регистр приводим к единому виду: гости пишут «стол 1», «Стол 1» и «СТОЛ 1»,
    а это должен быть один и тот же стол, иначе счёт вечера разъезжается.
    """
    t = " ".join((guest.get("table") or "").split())
    if not t:
        return NO_TABLE
    return t[:1].upper() + t[1:].lower()


def teams_from_guests(guests):
    """Список команд по столам, в порядке появления."""
    out = []
    for g in guests:
        t = team_of(g)
        if t not in out:
            out.append(t)
    return out


# --------------------------------------------------------------------------
# Запуск
# --------------------------------------------------------------------------
def start(gtype, config=None, guests=None):
    if gtype not in CATALOG_BY_TYPE:
        raise ValueError(f"Неизвестный конкурс «{gtype}»")
    cfg = dict(config or {})
    guests = list(guests or [])
    g = {
        "id": new_id(),
        "type": gtype,
        "title": cfg.get("title") or CATALOG_BY_TYPE[gtype]["title"],
        "open": True,
        "started_at": time.time(),
        "config": cfg,
        "data": {},
        "subs": {},       # token -> ответ гостя
        "result": None,
    }
    _STARTERS[gtype](g, cfg, guests)
    return g


def _start_wordcloud(g, cfg, guests):
    g["config"]["prompt"] = cfg.get("prompt") or random.choice(WORDCLOUD_PROMPTS)
    g["config"]["max_words"] = int(cfg.get("max_words") or 2)


def _start_taprace(g, cfg, guests):
    g["config"]["seconds"] = max(10, min(120, int(cfg.get("seconds") or 25)))
    g["config"]["goal"] = int(cfg.get("goal") or 300)
    g["data"]["taps"] = {}          # команда -> число нажатий
    g["data"]["ends_at"] = time.time() + g["config"]["seconds"]
    for t in teams_from_guests(guests):
        g["data"]["taps"][t] = 0


def _start_bets(g, cfg, guests):
    q = cfg.get("question")
    opts = cfg.get("options")
    if not q or not opts:
        pick = random.choice(BETS_QUESTIONS)
        q, opts = pick["question"], list(pick["options"])
    g["config"]["question"] = q
    g["config"]["options"] = list(opts)
    g["config"]["stakes"] = cfg.get("stakes") or [10, 25, 50]
    g["data"]["balance"] = dict(cfg.get("balance") or {})   # token -> фишки
    g["data"]["start_balance"] = int(cfg.get("start_balance") or 100)
    g["data"]["round"] = int(cfg.get("round") or 1)


def _start_bingo(g, cfg, guests):
    pool = [str(x).strip() for x in (cfg.get("pool") or BINGO_POOL) if str(x).strip()]
    if len(pool) < 9:
        raise ValueError("Для бинго нужно минимум 9 событий")
    g["config"]["pool"] = pool
    g["data"]["marked"] = []        # индексы отмеченных событий
    g["data"]["winners"] = []


def _start_numbers(g, cfg, guests):
    cards = cfg.get("cards") or NUMBERS_EXAMPLE
    clean = []
    for c in cards:
        n = str(c.get("n", "")).strip()
        t = str(c.get("text", "")).strip()
        if n and t:
            clean.append({"n": n, "text": t})
    if not clean:
        raise ValueError("Нужна хотя бы одна карточка с числом")
    g["config"]["cards"] = clean
    g["data"]["revealed"] = []


def _start_toast(g, cfg, guests):
    g["config"]["parts"] = cfg.get("parts") or TOAST_PARTS
    g["data"]["current"] = None
    g["data"]["shown"] = 0


def _start_dancewheel(g, cfg, guests):
    dances = cfg.get("dances") or DANCES
    g["config"]["dances"] = dances
    g["data"]["current"] = None
    g["data"]["used"] = []


def _start_noise(g, cfg, guests):
    teams = cfg.get("teams") or teams_from_guests(guests) or ["Левая сторона", "Правая сторона"]
    g["config"]["teams"] = teams
    g["data"]["scores"] = {}        # команда -> пик громкости 0..100
    g["data"]["active"] = None      # чья сейчас очередь кричать
    g["data"]["level"] = 0


_STARTERS = {
    "wordcloud": _start_wordcloud,
    "taprace": _start_taprace,
    "bets": _start_bets,
    "bingo": _start_bingo,
    "numbers": _start_numbers,
    "toast": _start_toast,
    "dancewheel": _start_dancewheel,
    "noise": _start_noise,
}


# --------------------------------------------------------------------------
# Ответы гостей
# --------------------------------------------------------------------------
def submit(g, guest, payload):
    """Возвращает (ok, ошибка). Меняет g на месте."""
    if not g:
        return False, "Сейчас нет активного конкурса"
    fn = _SUBMITTERS.get(g["type"])
    if not fn:
        return False, "В этом конкурсе гости не участвуют с телефонов"
    if not g["open"] and g["type"] != "bingo":
        return False, "Приём ответов закрыт"
    return fn(g, guest, payload or {})


def _sub_wordcloud(g, guest, p):
    raw = str(p.get("text", "")).strip()
    if not raw:
        return False, "Напишите слово"
    words = [w.strip(" .,!?;:—-").lower() for w in raw.split()]
    words = [w for w in words if w][: g["config"]["max_words"]]
    if not words:
        return False, "Напишите слово"
    for w in words:
        if len(w) > 24:
            return False, "Слишком длинное слово"
    g["subs"][guest["token"]] = {"name": guest["name"], "words": words}
    return True, None


def _sub_taprace(g, guest, p):
    if time.time() > g["data"]["ends_at"]:
        g["open"] = False
        return False, "Гонка закончилась"
    n = max(0, min(50, int(p.get("taps") or 1)))
    team = team_of(guest)
    g["data"]["taps"][team] = g["data"]["taps"].get(team, 0) + n
    cur = g["subs"].setdefault(guest["token"], {"name": guest["name"], "taps": 0})
    cur["taps"] += n
    return True, None


def _sub_bets(g, guest, p):
    idx = p.get("option")
    stake = int(p.get("stake") or 0)
    if idx is None or not (0 <= int(idx) < len(g["config"]["options"])):
        return False, "Выберите вариант"
    if stake not in g["config"]["stakes"]:
        return False, "Неверная ставка"
    bal = g["data"]["balance"]
    tok = guest["token"]
    have = bal.get(tok, g["data"]["start_balance"])
    if stake > have:
        return False, f"У вас осталось {have} фишек"
    g["subs"][tok] = {"name": guest["name"], "option": int(idx), "stake": stake}
    bal[tok] = have
    return True, None


def _sub_bingo(g, guest, p):
    # гость сам ничего не отправляет — карточка генерируется по токену,
    # но он может нажать «Бинго!», и это видит ведущий
    if p.get("claim"):
        name = guest["name"]
        if name not in g["data"]["winners"]:
            g["data"]["winners"].append(name)
        return True, None
    return False, "Нечего отправлять"


_SUBMITTERS = {
    "wordcloud": _sub_wordcloud,
    "taprace": _sub_taprace,
    "bets": _sub_bets,
    "bingo": _sub_bingo,
}


# --------------------------------------------------------------------------
# Карточка бинго: одинаковая при каждом заходе с того же телефона
# --------------------------------------------------------------------------
def bingo_card(g, token):
    pool = g["config"]["pool"]
    rnd = random.Random(f"{g['id']}:{token}")
    idx = rnd.sample(range(len(pool)), min(9, len(pool)))
    return [{"i": i, "text": pool[i]} for i in idx]


def bingo_has_line(card_idx, marked):
    """card_idx — 9 индексов по порядку сетки 3x3."""
    m = set(marked)
    grid = [[card_idx[r * 3 + c] in m for c in range(3)] for r in range(3)]
    for r in range(3):
        if all(grid[r]):
            return True
    for c in range(3):
        if all(grid[r][c] for r in range(3)):
            return True
    if all(grid[i][i] for i in range(3)):
        return True
    if all(grid[i][2 - i] for i in range(3)):
        return True
    return False


# --------------------------------------------------------------------------
# Действия ведущего
# --------------------------------------------------------------------------
def action(g, name, params=None, guests=None):
    """Возвращает (ok, ошибка). Меняет g на месте."""
    if not g:
        return False, "Сейчас нет активного конкурса"
    p = dict(params or {})
    guests = list(guests or [])

    if name == "close":
        g["open"] = False
        return True, None
    if name == "open":
        g["open"] = True
        return True, None

    fn = _ACTIONS.get((g["type"], name))
    if not fn:
        return False, f"Действие «{name}» недоступно в этом конкурсе"
    return fn(g, p, guests)


def _act_taprace_extend(g, p, guests):
    g["data"]["ends_at"] = time.time() + max(5, int(p.get("seconds") or 15))
    g["open"] = True
    return True, None


def _act_bets_reveal(g, p, guests):
    idx = p.get("option")
    if idx is None or not (0 <= int(idx) < len(g["config"]["options"])):
        return False, "Укажите, что случилось на самом деле"
    idx = int(idx)
    g["open"] = False
    bal = g["data"]["balance"]
    start_bal = g["data"]["start_balance"]
    bank = sum(s["stake"] for s in g["subs"].values())
    winners = {t: s for t, s in g["subs"].items() if s["option"] == idx}
    win_stake = sum(s["stake"] for s in winners.values())
    payouts = []
    for tok, s in g["subs"].items():
        have = bal.get(tok, start_bal)
        have -= s["stake"]
        gain = 0
        if tok in winners and win_stake > 0:
            gain = int(round(bank * s["stake"] / win_stake))
            have += gain
        bal[tok] = have
        payouts.append({"name": s["name"], "won": tok in winners,
                        "stake": s["stake"], "gain": gain, "balance": have})
    payouts.sort(key=lambda r: -r["balance"])
    g["result"] = {"correct": idx, "bank": bank, "payouts": payouts}
    return True, None


def _act_bets_next(g, p, guests):
    pick = random.choice(BETS_QUESTIONS)
    g["config"]["question"] = p.get("question") or pick["question"]
    g["config"]["options"] = p.get("options") or list(pick["options"])
    g["subs"] = {}
    g["result"] = None
    g["open"] = True
    g["data"]["round"] += 1
    return True, None


def _act_bingo_mark(g, p, guests):
    i = int(p.get("index", -1))
    if not (0 <= i < len(g["config"]["pool"])):
        return False, "Нет такого события"
    if i not in g["data"]["marked"]:
        g["data"]["marked"].append(i)
    return True, None


def _act_bingo_unmark(g, p, guests):
    i = int(p.get("index", -1))
    g["data"]["marked"] = [x for x in g["data"]["marked"] if x != i]
    return True, None


def _act_numbers_reveal(g, p, guests):
    i = int(p.get("index", -1))
    if not (0 <= i < len(g["config"]["cards"])):
        return False, "Нет такой карточки"
    if i not in g["data"]["revealed"]:
        g["data"]["revealed"].append(i)
    return True, None


def _act_toast_roll(g, p, guests):
    parts = g["config"]["parts"]
    who = random.choice(parts.get("who") or ["за героя вечера"])
    tone = random.choice(parts.get("tone") or ["как обычно"])
    detail = random.choice(parts.get("detail") or ["без условий"])
    finish = random.choice(parts.get("finish") or ["закончите как хотите"])
    name = str(p.get("guest") or "").strip()
    if not name and guests:
        name = random.choice(guests)["name"]
    g["data"]["current"] = {"guest": name, "who": who, "tone": tone,
                            "detail": detail, "finish": finish}
    g["data"]["shown"] += 1
    return True, None


def _act_dancewheel_spin(g, p, guests):
    dances = g["config"]["dances"]
    used = g["data"]["used"]
    pool = [d for i, d in enumerate(dances) if i not in used] or dances
    d = random.choice(pool)
    g["data"]["current"] = d
    i = dances.index(d)
    if i not in used:
        used.append(i)
    if len(used) >= len(dances):
        g["data"]["used"] = []
    return True, None


def _act_noise_arm(g, p, guests):
    t = str(p.get("team") or "").strip()
    if not t:
        return False, "Укажите команду"
    g["data"]["active"] = t
    g["data"]["level"] = 0
    return True, None


def _act_noise_level(g, p, guests):
    """Экран присылает измеренный уровень с микрофона ноутбука."""
    lvl = max(0, min(100, int(p.get("level") or 0)))
    g["data"]["level"] = lvl
    t = g["data"].get("active")
    if t:
        g["data"]["scores"][t] = max(g["data"]["scores"].get(t, 0), lvl)
    return True, None


def _act_noise_stop(g, p, guests):
    g["data"]["active"] = None
    g["data"]["level"] = 0
    return True, None


_ACTIONS = {
    ("taprace", "extend"): _act_taprace_extend,
    ("bets", "reveal"): _act_bets_reveal,
    ("bets", "next"): _act_bets_next,
    ("bingo", "mark"): _act_bingo_mark,
    ("bingo", "unmark"): _act_bingo_unmark,
    ("numbers", "reveal"): _act_numbers_reveal,
    ("toast", "roll"): _act_toast_roll,
    ("dancewheel", "spin"): _act_dancewheel_spin,
    ("noise", "arm"): _act_noise_arm,
    ("noise", "level"): _act_noise_level,
    ("noise", "stop"): _act_noise_stop,
}


# --------------------------------------------------------------------------
# Публичная проекция: одна для экрана и телефонов
# --------------------------------------------------------------------------
def public(g, guests=None):
    if not g:
        return None
    guests = list(guests or [])
    base = {
        "id": g["id"],
        "type": g["type"],
        "title": g["title"],
        "open": g["open"],
        "phone": CATALOG_BY_TYPE[g["type"]]["phone"],
        "answered": len(g["subs"]),
        "started_at": g["started_at"],
    }
    base.update(_PUBLIC[g["type"]](g, guests))
    return base


def _pub_wordcloud(g, guests):
    counts = {}
    for s in g["subs"].values():
        for w in s["words"]:
            counts[w] = counts.get(w, 0) + 1
    words = [{"word": w, "count": c} for w, c in counts.items()]
    words.sort(key=lambda x: (-x["count"], x["word"]))
    return {"prompt": g["config"]["prompt"], "words": words[:40],
            "max_words": g["config"]["max_words"]}


def _pub_taprace(g, guests):
    taps = g["data"]["taps"]
    goal = g["config"]["goal"]
    rows = [{"team": t, "taps": n, "pct": min(100, round(n / goal * 100)) if goal else 0}
            for t, n in taps.items()]
    rows.sort(key=lambda r: -r["taps"])
    left = max(0, round(g["data"]["ends_at"] - time.time()))
    if left <= 0 and g["open"]:
        g["open"] = False
    return {"rows": rows, "goal": goal, "left": left,
            "seconds": g["config"]["seconds"]}


def _pub_bets(g, guests):
    opts = g["config"]["options"]
    tally = [0] * len(opts)
    pot = [0] * len(opts)
    for s in g["subs"].values():
        tally[s["option"]] += 1
        pot[s["option"]] += s["stake"]
    total = sum(pot)
    coef = []
    for p in pot:
        coef.append(round(total / p, 2) if p else None)
    board = [{"name": s["name"], "balance": g["data"]["balance"].get(t, g["data"]["start_balance"])}
             for t, s in g["subs"].items()]
    board.sort(key=lambda r: -r["balance"])
    return {"question": g["config"]["question"], "options": opts,
            "stakes": g["config"]["stakes"], "tally": tally, "pot": pot,
            "coef": coef, "bank": total, "round": g["data"]["round"],
            "result": g["result"], "board": board[:10],
            "start_balance": g["data"]["start_balance"]}


def _pub_bingo(g, guests):
    pool = g["config"]["pool"]
    marked = g["data"]["marked"]
    return {"pool": [{"i": i, "text": t, "marked": i in marked} for i, t in enumerate(pool)],
            "marked": marked, "winners": g["data"]["winners"],
            "last": pool[marked[-1]] if marked else None}


def _pub_numbers(g, guests):
    cards = g["config"]["cards"]
    rev = g["data"]["revealed"]
    return {"cards": [{"i": i, "n": c["n"], "text": c["text"] if i in rev else None,
                       "open": i in rev} for i, c in enumerate(cards)],
            "left": len(cards) - len(rev)}


def _pub_toast(g, guests):
    return {"current": g["data"]["current"], "shown": g["data"]["shown"]}


def _pub_dancewheel(g, guests):
    return {"current": g["data"]["current"],
            "dances": [d["name"] for d in g["config"]["dances"]]}


def _pub_noise(g, guests):
    scores = g["data"]["scores"]
    rows = [{"team": t, "score": s} for t, s in scores.items()]
    rows.sort(key=lambda r: -r["score"])
    return {"teams": g["config"]["teams"], "active": g["data"]["active"],
            "level": g["data"]["level"], "rows": rows}


_PUBLIC = {
    "wordcloud": _pub_wordcloud,
    "taprace": _pub_taprace,
    "bets": _pub_bets,
    "bingo": _pub_bingo,
    "numbers": _pub_numbers,
    "toast": _pub_toast,
    "dancewheel": _pub_dancewheel,
    "noise": _pub_noise,
}


def guest_view(g, guest):
    """Персональная часть для телефона гостя (карточка бинго, баланс фишек)."""
    if not g:
        return None
    t = g["type"]
    tok = guest["token"]
    if t == "bingo":
        card = bingo_card(g, tok)
        marked = g["data"]["marked"]
        idx = [c["i"] for c in card]
        return {"card": [{"text": c["text"], "marked": c["i"] in marked} for c in card],
                "line": bingo_has_line(idx, marked)}
    if t == "bets":
        return {"balance": g["data"]["balance"].get(tok, g["data"]["start_balance"]),
                "my": g["subs"].get(tok)}
    if t == "wordcloud":
        return {"sent": tok in g["subs"]}
    if t == "taprace":
        return {"my": g["subs"].get(tok, {}).get("taps", 0)}
    return None
