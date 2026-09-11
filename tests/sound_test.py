# -*- coding: utf-8 -*-
"""Звук: фоновая музыка, эффекты, интеграция со сценарием."""
import json,os,wave,threading,time,urllib.request,http.cookiejar
B="http://127.0.0.1:8000"
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(urllib.request.Request(B+"/admin",data=b"pin=1234",
    headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=20)
def call(p,d=None):
    r=urllib.request.Request(B+p,data=json.dumps(d).encode() if d is not None else None,
        headers={'Content-Type':'application/json'},method='POST' if d is not None else 'GET')
    try:
        with op.open(r,timeout=20) as f: return f.status,json.loads(f.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
ok=lambda c,m: print(("✅" if c else "❌"),m)

events=[]
def listen():
    with op.open(B+"/api/stream",timeout=120) as f:
        ev=None
        for line in f:
            l=line.decode().strip()
            if l.startswith("event:"): ev=l[6:].strip()
            elif l.startswith("data:") and ev in("sound","sfx"): events.append((ev,json.loads(l[5:])))
threading.Thread(target=listen,daemon=True).start(); time.sleep(1)

s,c=call("/api/sound/catalog")
ok(len(c["backgrounds"])==4 and len(c["effects"])==6,
   f"каталог: {len(c['backgrounds'])} фонов, {len(c['effects'])} эффектов")

# файлы реально существуют и валидны
bad=[]
for it in c["backgrounds"]+c["effects"]:
    p="."+it["url"]
    if not os.path.exists(p): bad.append(it["url"]); continue
    w=wave.open(p); d=w.getnframes()/w.getframerate()
    if d<1.0: bad.append(it["url"]+f" ({d:.1f}s)")
ok(not bad,f"все 10 звуковых файлов на месте и не пустые" if not bad else f"проблемы: {bad}")
# лупы должны быть длиннее 15 сек, иначе будет заметное повторение
short=[b["id"] for b in c["backgrounds"] if wave.open("."+b["url"]).getnframes()/22050<15]
ok(not short,f"фоновые треки достаточно длинные (без частых повторов)")

s,d=call("/api/sound/bg",{"bg":"lounge","volume":40})
ok(s==200 and d["bg"]=="lounge" and d["playing"],"фон включён: lounge 40%")
s,d=call("/api/sound/bg",{"playing":False}); ok(not d["playing"],"пауза работает")
s,d=call("/api/sound/bg",{"playing":True,"volume":150}); ok(d["volume"]==100,"громкость ограничена сотней")
s,d=call("/api/sound/bg",{"duck":15}); ok(d["duck"]==15,"уровень приглушения под голос настраивается")
s,d=call("/api/sound/bg",{"bg":"нетакого"}); ok(s==400,"неизвестный трек отклонён")
s,d=call("/api/sound/fx",{"id":"fanfare"}); ok(s==200,"фанфары отправлены на экран")
s,d=call("/api/sound/fx",{"id":"бум"}); ok(s==400,"неизвестный эффект отклонён")
s,d=call("/api/sound/bg",{"bg":""}); ok(d["bg"] is None,"музыку можно выключить")
ok(call("/api/state")[1]["sound"] is not None,"состояние звука есть в общем снапшоте")
ok(any(e=="sfx" for e,_ in events) and any(e=="sound" for e,_ in events),
   f"экран получает события звука по SSE: {len(events)}")

# сценарий
s,d=call("/api/scenario/load",{"file":"корпоративный-юбилей-45.json"})
ok(s==200,f"сценарий загружен: {d['total']} шагов")
titles=[st["title"] for st in d["steps"]]
nums=[t.split(".")[0] for t in titles]
ok(len(set(nums))==len(nums),f"нумерация шагов без дублей: {nums[:6]}…")
s,d=call("/api/scenario/goto",{"index":2})   # «Открытие вечера» — фанфары + solemn
time.sleep(0.6)
st=call("/api/state")[1]["sound"]
ok(st["bg"]=="solemn",f"сценарий переключил музыку: {st['bg']}")
ok(any(e=="sfx" and v["id"]=="fanfare" for e,v in events),"сценарий сыграл фанфары")
s,d=call("/api/scenario/load",{"content":json.dumps({"format":"avatar-host-scenario","version":1,
  "meta":{"title":"X"},"steps":[{"type":"sound"}]})})
ok(s==400,"пустой звуковой шаг отклонён: "+d["error"][:45])
call("/api/sound/bg",{"bg":""}); call("/api/speech/clear",{})

# --- своя музыка из папки music/ и радио ---
import shutil, urllib.parse
MUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music")
os.makedirs(os.path.join(MUS, "Тесты"), exist_ok=True)
src = "static/sound/bg_lounge.wav"
own = os.path.join(MUS, "Тестовый трек.wav")
nested = os.path.join(MUS, "Тесты", "Вложенный.wav")
shutil.copy(src, own); shutil.copy(src, nested)

s, lst = call("/api/music/list")
ids = [t["id"] for t in lst["tracks"]]
ok(s == 200 and "file:Тестовый трек.wav" in ids, "свой файл найден в папке music/")
ok("file:Тесты/Вложенный.wav" in ids, "файл из подпапки тоже виден")
ok(any(t["group"] == "Тесты" for t in lst["tracks"]), "подпапка становится группой в списке")
ok(not lst["status"]["empty"], "статус: папка не пуста")
ok(len(lst["radio"]) >= 10, f"радиостанций не меньше 10: {len(lst['radio'])}")
ok(all(r["url"].startswith("https://") for r in lst["radio"]),
   "все радиопотоки по https (иначе браузер заблокирует)")
ok(all(r.get("genre") for r in lst["radio"]), "у каждой радиостанции подписан жанр")

s, d = call("/api/sound/bg", {"bg": "file:Тестовый трек.wav", "playing": True})
ok(s == 200 and d["kind"] == "file", "свой файл выбран как фон")
ok(d["label"] == "Тестовый трек", f"видно название трека: {d['label']}")
ok(bool(d["url"]), "в состоянии есть адрес для проигрывания")

# сам файл должен реально отдаваться экрану
r = urllib.request.Request(B + d["url"])
with op.open(r, timeout=20) as f:
    body = f.read()
ok(len(body) > 10000, f"файл отдаётся по /music/ ({len(body)//1024} КБ)")

s, d = call("/api/sound/bg", {"bg": "radio:retro"})
ok(s == 200 and d["kind"] == "radio" and d["label"] == "Ретро FM", "радио выбирается и подписано")
ok(d["url"].startswith("https://"), "у радио отдаётся прямой поток")

s, d = call("/api/sound/bg", {"bg": "file:такого-нет.mp3"})
ok(s == 400 and "не найден" in d.get("error", ""), "пропавший файл → понятная ошибка, а не тишина")
s, d = call("/api/sound/bg", {"bg": "radio:такого-нет"})
ok(s == 400, "неизвестная радиостанция отклонена")

# защита: нельзя утащить файл за пределы папки music/
try:
    with op.open(urllib.request.Request(B + "/music/../server.py"), timeout=20) as f:
        code = f.status
except urllib.error.HTTPError as e:
    code = e.code
ok(code == 404, "нельзя вытащить файл за пределы папки music/")

s, d = call("/api/sound/bg", {"bg": "lounge"})
ok(s == 200 and d["kind"] == "gen", "старый формат из сценариев по-прежнему работает")

os.remove(own); os.remove(nested); os.rmdir(os.path.join(MUS, "Тесты"))
