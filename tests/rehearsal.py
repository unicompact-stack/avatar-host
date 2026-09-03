# -*- coding: utf-8 -*-
"""Репетиция вечера: запускает сценарий и печатает все реплики и события."""
import json,time,urllib.request,threading
B="http://127.0.0.1:8000"
def req(p,d=None):
    r=urllib.request.Request(B+p,data=json.dumps(d).encode() if d is not None else None,
        headers={'Content-Type':'application/json'},method='POST' if d is not None else 'GET')
    try:
        with urllib.request.urlopen(r,timeout=30) as f: return json.loads(f.read())
    except urllib.error.HTTPError as e: return json.loads(e.read())

events=[]
def listen():
    with urllib.request.urlopen(B+"/api/stream",timeout=200) as f:
        ev=None
        for line in f:
            line=line.decode().strip()
            if line.startswith("event:"): ev=line[6:].strip()
            elif line.startswith("data:") and ev:
                events.append((ev,json.loads(line[5:])))
threading.Thread(target=listen,daemon=True).start()
time.sleep(1)

print("== старт сценария ==")
print(req("/api/demo/scenario",{"fast":True}))
for _ in range(120):
    st=req("/api/demo/scenario/state")
    if not st["running"] and st["step"]: break
    time.sleep(1)
print("шаги:",[l["step"] for l in st["log"]])
h=req("/api/health"); print("health:",h["guests"],"гостей, очередь:",h["queue"])
print("лидеры:",req("/api/leaderboard")["rows"][:3])
kinds={}
for ev,d in events: kinds[ev]=kinds.get(ev,0)+1
print("события SSE:",kinds)
print("реплик озвучено:",sum(1 for e,_ in events if e=="speak"))
for e,d in events:
    if e=="speak": print("  •",d["engine"],round(d["duration"],1),"s:",d["text"][:60])
