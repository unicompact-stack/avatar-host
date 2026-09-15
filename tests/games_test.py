# -*- coding: utf-8 -*-
"""Конкурсы: движок games.py без сети + ручки через HTTP."""
import json
import os
import sys
import time
import urllib.request
import http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import games

ok = lambda c, m: print(("✅" if c else "❌"), m)

GUESTS = [
    {"token": "t1", "name": "Аня", "table": "1"},
    {"token": "t2", "name": "Боря", "table": "1"},
    {"token": "t3", "name": "Вика", "table": "2"},
    {"token": "t4", "name": "Гена", "table": "2"},
    {"token": "t5", "name": "Дима", "table": ""},
]

print("— движок —")
ok(len(games.CATALOG) == 8, f"в каталоге {len(games.CATALOG)} конкурсов")
ok(all(g["type"] in games._PUBLIC for g in games.CATALOG),
   "у каждого конкурса есть публичная проекция")
ok(all(g["type"] in games._STARTERS for g in games.CATALOG),
   "у каждого конкурса есть запуск")

# --- облако слов ---
g = games.start("wordcloud", {"prompt": "Одно слово о Захаре"}, GUESTS)
games.submit(g, GUESTS[0], {"text": "весёлый"})
games.submit(g, GUESTS[1], {"text": "Весёлый!"})
games.submit(g, GUESTS[2], {"text": "добрый"})
p = games.public(g, GUESTS)
top = p["words"][0]
ok(top["word"] == "весёлый" and top["count"] == 2, "облако: регистр и знаки схлопнулись, счёт 2")
ok(len(p["words"]) == 2, "облако: два уникальных слова")
_, err = games.submit(g, GUESTS[3], {"text": "   "})
ok(err is not None, "облако: пустое слово отклонено")

# повторная отправка заменяет, а не плодит
games.submit(g, GUESTS[0], {"text": "громкий"})
p = games.public(g, GUESTS)
ok(sum(w["count"] for w in p["words"]) == 3, "облако: повторный ответ заменил прежний")

# --- гонка столов ---
g = games.start("taprace", {"seconds": 30, "goal": 100}, GUESTS)
for _ in range(10):
    games.submit(g, GUESTS[0], {"taps": 5})
games.submit(g, GUESTS[2], {"taps": 7})
p = games.public(g, GUESTS)
ok(p["rows"][0]["team"] == "1" and p["rows"][0]["taps"] == 50, "гонка: стол 1 лидирует с 50")
ok(p["rows"][0]["pct"] == 50, "гонка: прогресс 50%")
ok(any(r["team"] == games.NO_TABLE for r in p["rows"]), "гонка: гости без стола в своей команде")
_, err = games.submit(g, GUESTS[0], {"taps": 9999})
p = games.public(g, GUESTS)
ok(p["rows"][0]["taps"] <= 100, "гонка: накрутка за один запрос ограничена")

# --- ставки ---
g = games.start("bets", {"question": "Сколько?", "options": ["А", "Б"],
                         "start_balance": 100}, GUESTS)
games.submit(g, GUESTS[0], {"option": 0, "stake": 50})
games.submit(g, GUESTS[1], {"option": 0, "stake": 10})
games.submit(g, GUESTS[2], {"option": 1, "stake": 25})
p = games.public(g, GUESTS)
ok(p["bank"] == 85, f"ставки: банк 85, получили {p['bank']}")
ok(p["coef"][0] == round(85 / 60, 2), "ставки: коэффициент считается от банка")
games.action(g, "reveal", {"option": 0}, GUESTS)
p = games.public(g, GUESTS)
win = {r["name"]: r for r in p["result"]["payouts"]}
ok(win["Аня"]["balance"] > 100, f"ставки: победитель в плюсе ({win['Аня']['balance']})")
ok(win["Вика"]["balance"] == 75, f"ставки: проигравший -25 ({win['Вика']['balance']})")
ok(sum(r["gain"] for r in p["result"]["payouts"]) == 85, "ставки: банк роздан полностью")
_, err = games.submit(g, GUESTS[0], {"option": 0, "stake": 10})
ok(err is not None, "ставки: после раскрытия приём закрыт")
games.action(g, "next", {"question": "Дальше?", "options": ["Да", "Нет"]}, GUESTS)
ok(g["open"] and g["data"]["round"] == 2, "ставки: второй круг открылся")
_, err = games.submit(g, GUESTS[2], {"option": 0, "stake": 100})
ok(err is not None, "ставки: нельзя поставить больше, чем есть фишек")

# --- бинго ---
g = games.start("bingo", {}, GUESTS)
c1 = games.bingo_card(g, "t1")
c1b = games.bingo_card(g, "t1")
c2 = games.bingo_card(g, "t2")
ok([x["i"] for x in c1] == [x["i"] for x in c1b], "бинго: карточка стабильна при перезаходе")
ok([x["i"] for x in c1] != [x["i"] for x in c2], "бинго: у разных гостей разные карточки")
idx = [x["i"] for x in c1]
for i in idx[:3]:
    games.action(g, "mark", {"index": i}, GUESTS)
ok(games.bingo_has_line(idx, idx[:3]), "бинго: верхняя строка засчитана как линия")
ok(not games.bingo_has_line(idx, idx[:2]), "бинго: двух клеток мало")
ok(games.bingo_has_line(idx, [idx[0], idx[4], idx[8]]), "бинго: диагональ засчитана")
v = games.guest_view(g, GUESTS[0])
ok(v["line"] is True, "бинго: гость видит, что линия собрана")
games.action(g, "unmark", {"index": idx[0]}, GUESTS)
ok(len(g["data"]["marked"]) == 2, "бинго: отметку можно снять")

# --- цифры вечера ---
g = games.start("numbers", {"cards": [{"n": "38", "text": "лет"},
                                      {"n": "7", "text": "в школе"}]}, GUESTS)
p = games.public(g, GUESTS)
ok(p["cards"][0]["text"] is None, "цифры: расшифровка скрыта до раскрытия")
games.action(g, "reveal", {"index": 0}, GUESTS)
p = games.public(g, GUESTS)
ok(p["cards"][0]["text"] == "лет" and p["left"] == 1, "цифры: карточка раскрыта, осталась одна")

# --- тост-конструктор ---
g = games.start("toast", {}, GUESTS)
games.action(g, "roll", {"guest": "Аня"}, GUESTS)
cur = games.public(g, GUESTS)["current"]
ok(all(cur[k] for k in ("who", "tone", "detail", "finish")), "тост: собраны все четыре части")
ok(cur["guest"] == "Аня", "тост: имя гостя подставлено")
games.action(g, "roll", {}, GUESTS)
ok(games.public(g, GUESTS)["current"]["guest"] in [x["name"] for x in GUESTS],
   "тост: без имени выбирается случайный гость")

# --- колесо танцев ---
g = games.start("dancewheel", {}, GUESTS)
seen = set()
for _ in range(len(games.DANCES)):
    games.action(g, "spin", {}, GUESTS)
    seen.add(games.public(g, GUESTS)["current"]["name"])
ok(len(seen) == len(games.DANCES), "колесо: за полный круг выпали все танцы без повторов")

# --- шумомер ---
g = games.start("noise", {}, GUESTS)
games.action(g, "arm", {"team": "1"}, GUESTS)
games.action(g, "level", {"level": 60}, GUESTS)
games.action(g, "level", {"level": 40}, GUESTS)
games.action(g, "stop", {}, GUESTS)
games.action(g, "arm", {"team": "2"}, GUESTS)
games.action(g, "level", {"level": 80}, GUESTS)
p = games.public(g, GUESTS)
ok(p["rows"][0]["team"] == "2" and p["rows"][0]["score"] == 80, "шумомер: стол 2 громче")
ok([r for r in p["rows"] if r["team"] == "1"][0]["score"] == 60,
   "шумомер: запоминается пик, а не последнее значение")

# --- ошибки ---
try:
    games.start("нетакого", {}, GUESTS)
    ok(False, "неизвестный конкурс должен падать")
except ValueError:
    ok(True, "неизвестный тип конкурса отклонён")
_, err = games.submit(None, GUESTS[0], {})
ok(err is not None, "ответ без активного конкурса отклонён")
g = games.start("toast", {}, GUESTS)
_, err = games.submit(g, GUESTS[0], {"text": "х"})
ok(err is not None, "в «ведёте вы» гости с телефона не отвечают")

# --- команды ---
ok(games.teams_from_guests(GUESTS) == ["1", "2", games.NO_TABLE],
   "команды собраны по столам в порядке появления")
ok(games.teams_from_guests([{"table": "стол 1"}, {"table": "Стол  1"},
                            {"table": "СТОЛ 2"}]) == ["Стол 1", "Стол 2"],
   "столы «стол 1» и «Стол 1» — одна команда")

# ---------------------------------------------------------------- HTTP
print("— через сервер —")
B = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:
    op.open(urllib.request.Request(B + "/admin", data=b"pin=1234",
            headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=20)
except Exception as e:
    print("⚠️  сервер не запущен, пропускаю сетевые проверки:", e)
    raise SystemExit(0)


def call(p, d=None):
    r = urllib.request.Request(B + p, data=json.dumps(d).encode() if d is not None else None,
                               headers={"Content-Type": "application/json"},
                               method="POST" if d is not None else "GET")
    try:
        with op.open(r, timeout=20) as f:
            return f.status, json.loads(f.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


s, c = call("/api/games/catalog")
ok(s == 200 and len(c["games"]) == 8, f"каталог по HTTP: {len(c.get('games', []))} конкурсов")

# заводим двух живых гостей
call("/api/reset", {})
s, d = call("/api/guest/connect", {"code": call("/api/state")[1]["code"]})
at = d["accessToken"]
s, g1 = call("/api/guest/join", {"token": at, "name": "Тестовая Аня", "table": "1"})
s, d2 = call("/api/guest/connect", {"code": call("/api/state")[1]["code"]})
s, g2 = call("/api/guest/join", {"token": d2["accessToken"], "name": "Тестовый Боря", "table": "2"})
ok(g1.get("accessToken") and g2.get("accessToken"), "два гостя подключились")

s, d = call("/api/games/start", {"type": "wordcloud", "config": {"prompt": "Слово?"}})
ok(s == 200 and d["type"] == "wordcloud", "конкурс запущен через админку")

s, d = call("/api/games/submit", {"token": g1["accessToken"], "payload": {"text": "огонь"}})
ok(s == 200, "гость отправил слово")
s, d = call("/api/games/submit", {"token": g2["accessToken"], "payload": {"text": "огонь"}})
s, d = call("/api/games/state")
ok(d["game"]["words"][0]["count"] == 2, "оба слова долетели до экрана")

s, d = call("/api/guest/me?token=" + g1["accessToken"])
ok(d.get("game") and d["game"]["type"] == "wordcloud", "телефон гостя видит активный конкурс")
ok(d.get("mine", {}).get("sent") is True, "гость видит, что его ответ принят")

s, d = call("/api/games/submit", {"token": "чужой", "payload": {"text": "х"}})
ok(s == 400, "чужой токен отклонён")

s, d = call("/api/games/start", {"type": "нетакого"})
ok(s == 400, "неизвестный конкурс отклонён сервером")

# счёт вечера
call("/api/score/reset", {})
call("/api/score/add", {"team": "Стол 1", "points": 3})
call("/api/score/add", {"team": "Стол 2", "points": 5})
s, d = call("/api/score/add", {"team": "Стол 1", "points": 4})
ok(d["rows"][0]["team"] == "Стол 1" and d["rows"][0]["score"] == 7,
   f"счёт вечера: стол 1 набрал 7 ({d['rows'][0]['score']})")
s, d = call("/api/score/add", {"team": "стол 1", "points": 2})
row1 = [r for r in d["rows"] if r["team"].lower() == "стол 1"]
ok(len(row1) == 1 and row1[0]["score"] == 9,
   f"счёт: разный регистр стола не раздваивает команду ({row1})")
s, d = call("/api/score/show", {"on": True})
ok(d["on"] is True, "таблица счёта включается на экран")

s, d = call("/api/games/stop", {})
s, d = call("/api/games/state")
ok(d["game"] is None, "конкурс остановлен")

# админские ручки закрыты для гостей
bare = urllib.request.build_opener()
try:
    bare.open(urllib.request.Request(B + "/api/games/start", data=b"{}",
              headers={"Content-Type": "application/json"}), timeout=10)
    ok(False, "запуск конкурса должен требовать админку")
except urllib.error.HTTPError as e:
    ok(e.code in (401, 403), f"запуск конкурса закрыт без админки ({e.code})")

call("/api/reset", {})
print("Готово.")
