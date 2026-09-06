# -*- coding: utf-8 -*-
"""Полный прогон корпоративного сценария по живому серверу."""
import json,time,urllib.request,http.cookiejar,urllib.parse,threading,http.cookiejar,urllib.parse
B="http://127.0.0.1:8000"
_cj=http.cookiejar.CookieJar()
_op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
def _login(pin="1234"):
    try:
        _op.open(urllib.request.Request(B+"/admin",data=b"pin="+pin.encode(),
            headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=20)
    except Exception: pass
_login()
def call(p,d=None):
    r=urllib.request.Request(B+p,data=json.dumps(d).encode() if d is not None else None,
      headers={'Content-Type':'application/json'},method='POST' if d is not None else 'GET')
    try:
        with _op.open(r,timeout=30) as f: return f.status,json.loads(f.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
ok=lambda c,m: print(("✅" if c else "❌"),m)
spoken=[]
def listen():
    with _op.open(B+"/api/stream",timeout=600) as f:
        ev=None
        for line in f:
            l=line.decode().strip()
            if l.startswith("event:"): ev=l[6:].strip()
            elif l.startswith("data:") and ev=="speak":
                d=json.loads(l[5:]); spoken.append(d["text"])
                call("/api/speech/done",{"id":d["id"]})   # играем роль экрана
threading.Thread(target=listen,daemon=True).start(); time.sleep(1)

def quiet(t=120):
    end=time.time()+t
    while time.time()<end:
        q=call("/api/health")[1]["queue"]
        if not q["pending"] and not q["speaking"]: return
        time.sleep(.3)

call("/api/reset",{})
s,d=call("/api/scenario/list"); ok(any("корпоратив" in f["file"] for f in d["files"]),
    f"файл найден в scenarios/: {[f['file'] for f in d['files']]}")

# валидация битого файла
s,d=call("/api/scenario/load",{"content":"{не json","filename":"bad.json"}); ok(s==400,"битый JSON отклонён: "+d["error"][:45])
s,d=call("/api/scenario/load",{"content":json.dumps({"format":"avatar-host-scenario","version":1,
  "meta":{"title":"X"},"steps":[{"type":"quiz","questions":[{"q":"a","options":["1"],"correct":0}]}]})})
ok(s==400,"кривой шаг отклонён: "+d["error"][:60])

s,d=call("/api/scenario/load",{"file":"корпоративный-юбилей-45.json"})
ok(s==200 and d["total"]==17,f"сценарий загружен: {d['total']} шагов, «{d['meta']['title']}»")
ok(call("/api/state")[1]["title"]==d["meta"]["title"],"заголовок экрана взят из meta")

# гости заходят
code=call("/api/state")[1]["code"]
call("/api/demo/guests",{"count":6}); quiet()
guests=call("/api/guests")[1]["guests"]
gt=guests[0]["token"]

print("\n--- прогон шагов ---")
for i in range(60):
    st=call("/api/scenario/state")[1]
    if st["status"]=="done": break
    s,d=call("/api/scenario/next",{})
    if d.get("error"): print("  ошибка:",d["error"]); break
    cur=d.get("current")
    if cur: print(f"  {d['index']+1:>2}. {cur['title']}  [{cur['type']}]"
                  + (f" вопрос {d['quiz_pos']}" if cur['type']=='quiz' else ""))
    quiet()
    q=call("/api/state")[1]["quiz"]
    if q and q["open"]: call("/api/demo/answers",{})
    c=call("/api/state")[1].get("collect")
    if c and c["open"]:
        call("/api/collect/add",{"token":gt,"text":"Здоровья и новых проектов!"})
        for g in guests[1:4]: call("/api/collect/add",{"token":g["token"],"text":"Так держать!"})
        call("/api/collect/close",{}); quiet()
    if d["status"]=="done": break

st=call("/api/scenario/state")[1]
ok(st["status"]=="done",f"сценарий доигран до конца (шаг {st['index']+1}/{st['total']})")
ok(len(spoken)>=25,f"реплик озвучено: {len(spoken)}")
lb=call("/api/leaderboard")[1]["rows"]
ok(lb[0]["score"]>0,f"баллы начислены, лидер: {lb[0]['name']} — {lb[0]['score']}")
ok(any("{" not in t for t in spoken) and not any("{hero}" in t or "{count}" in t for t in spoken),
   "все подстановки раскрыты (нет {hero}/{count} в эфире)")
ok(any("Андрей Викторович" in t for t in spoken),"имя юбиляра подставлено")
ok(any("желает" in t for t in spoken),"пожелания зачитаны вслух")
ok(any("гост" in t for t in spoken),"склонение числительных работает")
st2=call("/api/state")[1]["stage"]
ok(st2["mode"] in ("celebration","avatar"),f"экран переключался сценарием, финал: {st2['mode']}, подпись «{st2.get('caption','')}»")
print("\nпримеры реплик:")
for t in spoken[:3]+spoken[-3:]: print("  •",t[:95])
