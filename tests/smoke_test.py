# -*- coding: utf-8 -*-
"""Дымовой прогон по живому серверу: python tests/smoke_test.py (сервер должен быть запущен)."""
import json,time,urllib.request,http.cookiejar,urllib.parse
B="http://127.0.0.1:8000"
_cj=http.cookiejar.CookieJar()
_op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
def _login(pin="1234"):
    try:
        _op.open(urllib.request.Request(B+"/admin",data=b"pin="+pin.encode(),
            headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=20)
    except Exception: pass
_login()
def call(p,d=None,m=None):
    r=urllib.request.Request(B+p,data=json.dumps(d).encode() if d is not None else None,
      headers={'Content-Type':'application/json'},method=m or ('POST' if d is not None else 'GET'))
    try:
        with _op.open(r,timeout=30) as f: return f.status,json.loads(f.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
ok=lambda c,m: print(("✅" if c else "❌"),m)

call("/api/reset",{})
st=call("/api/state")[1]; code=st["code"]
ok(len(code)==5,"код мероприятия выдан: "+code)

# путь гостя
s,d=call("/api/guest/connect",{"code":"ZZZZZ"}); ok(s==404,"неверный код отклонён")
s,d=call("/api/guest/connect",{"code":code}); tok=d["accessToken"]; ok(s==200,"код принят")
s,d=call("/api/guest/join",{"token":tok,"name":"Анна","table":"стол 2"}); g=d["accessToken"]; ok(s==200,"гость зарегистрирован")
s2,_=call("/api/guest/connect",{"code":code})
s,d=call("/api/guest/join",{"token":_["accessToken"],"name":"анна"}); ok(s==409,"дубль имени отклонён: "+d.get("error",""))
s,d=call("/api/guest/join",{"token":"мусор","name":"Хакер"}); ok(s==401,"чужой токен отклонён")
ok(call("/api/guest/me?token="+g)[1]["guest"]["greeted"],"гость авто-приветствован")

# лимит и закрытие приёма
call("/api/settings",{"accepting":False})
s,d=call("/api/guest/connect",{"code":code}); ok(s==403,"закрытый приём не пускает")
call("/api/settings",{"accepting":True})

# очередь: 5 реплик разом не накладываются
for i in range(5): call("/api/say",{"text":f"Реплика номер {i+1}."})
q=call("/api/health")[1]["queue"]
ok(q["speaking"] is None or len(q["pending"])>=1,"очередь копит реплики, не наложение")
call("/api/speech/clear",{}); time.sleep(.5)
q=call("/api/health")[1]["queue"]; ok(not q["pending"],"очередь чистится кнопкой стоп")

# конкурс
call("/api/demo/guests",{"count":6})
s,d=call("/api/quiz/start",{"question":"Любимый цветок именинницы?","options":["Пионы","Розы","Тюльпаны"],"seconds":20})
ok(s==200,"конкурс запущен")
s,d=call("/api/quiz/answer",{"token":g,"index":9}); ok(s==400,"неверный вариант отклонён")
call("/api/quiz/answer",{"token":g,"index":0})
call("/api/demo/answers",{})
s,d=call("/api/quiz/close",{"correct":0}); ok(s==200 and sum(d["tally"])>1,f"итоги подсчитаны: {d['tally']}")
s,d=call("/api/quiz/answer",{"token":g,"index":1}); ok(s==400,"ответ после закрытия отклонён")
lb=call("/api/leaderboard")[1]["rows"]; ok(lb[0]["score"]>=1,f"рейтинг: {lb[0]}")

# синтез и настройки
s,d=call("/api/tts/preview",{"text":""}); ok(s==400,"пустой текст отклонён")
s,d=call("/api/tts/preview",{"text":"Проверка длинного текста. "*30})
ok(s==200 and d["duration"]>5,f"длинный текст: {d['engine']} {d['duration']}s")
call("/api/settings",{"title":"Свадьба Ани и Миши","rate":10})
st=call("/api/state")[1]; ok(st["title"]=="Свадьба Ани и Миши" and st["rate"]==10,"настройки применились")
for p in ["/","/host","/admin","/connect?code="+code,"/qr"]:
    with _op.open(B+p) as f: ok(f.status==200,f"страница {p}")
call("/api/speech/clear",{})
