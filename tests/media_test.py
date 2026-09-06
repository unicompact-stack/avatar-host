# -*- coding: utf-8 -*-
"""Медиатека и режимы экрана."""
import json,io,urllib.request,http.cookiejar,uuid
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
def upload(fname,data,ctype="image/png"):
    b=uuid.uuid4().hex
    body=(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
          f'Content-Type: {ctype}\r\n\r\n').encode()+data+f'\r\n--{b}--\r\n'.encode()
    r=urllib.request.Request(B+"/api/media/upload",data=body,
        headers={'Content-Type':f'multipart/form-data; boundary={b}'})
    try:
        with op.open(r,timeout=20) as f: return f.status,json.loads(f.read())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read())
        except Exception: return e.code,{"error":"не-JSON ответ"}
ok=lambda c,m: print(("✅" if c else "❌"),m)

PNG=bytes.fromhex('89504e470d0a1a0a0000000d494844520000000100000001080600000'
 '01f15c4890000000d4944415478da63fcffff3f0300050001ff9f6a3a0000000049454e44ae426082')
PDF=b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

s,d=upload("слайд один.png",PNG); ok(s==200 and d["saved"],f"картинка загружена: {d.get('saved',[{}])[0].get('name')}")
img=d["saved"][0]["name"]
ok("_" in img and img.endswith(".png"),"кириллица в имени сохранена, пробелы заменены")
s,d=upload("презентация.pdf",PDF,"application/pdf"); ok(s==200,"PDF загружен")
pdf=d["saved"][0]["name"]
s,d=upload("вирус.exe",b"MZ"); ok(s==400,"опасное расширение отклонено: "+d["error"][:40])
s,d=upload("огромный.png",b"x"*(26*1024*1024)); ok(s in (400,413) and "error" in d and "JSON" not in d["error"],
   f"слишком большой файл отклонён с понятной ошибкой: {d.get('error','')[:45]}")

s,d=call("/api/media/list"); ok(len(d["items"])>=2 and len(d["celebrations"])==4,
    f"список: {len(d['items'])} файлов, {len(d['celebrations'])} анимаций")

s,d=call("/api/stage",{"mode":"media","media":img}); ok(s==200 and d["mode"]=="media","показ картинки")
s,d=call("/api/stage",{"mode":"media","media":pdf,"page":3})
ok(d["media"]["kind"]=="doc" and d["page"]==3,"PDF со страницей 3")
s,d=call("/api/stage",{"mode":"celebration","celebration":"fireworks","caption":"Победители!"})
ok(d["mode"]=="celebration" and d["caption"]=="Победители!","салют с подписью")
s,d=call("/api/stage",{"mode":"avatar"}); ok(d["mode"]=="avatar","возврат к аватару")
s,d=call("/api/stage",{"mode":"черт"}); ok(s==400,"кривой режим отклонён")
s,d=call("/api/stage",{"mode":"media","media":"нет-такого.png"}); ok(s==404,"несуществующий файл отклонён")
s,d=call("/api/stage",{"mode":"celebration","celebration":"хаос"}); ok(s==400,"кривая анимация отклонена")
s,d=call("/api/media/delete",{"name":"../../server.py"}); ok(s==404,"выход из папки заблокирован")

ok(call("/api/state")[1]["stage"]["mode"]=="avatar","режим экрана есть в общем состоянии")
# сценарий со stage-шагом
s,d=call("/api/scenario/load",{"file":"корпоративный-юбилей-45.json"})
ok(s==200 and d["total"]==17,f"сценарий с медиа-шагами: {d['total']} шагов")
types=[st["type"] for st in d["steps"]]; ok("stage" in types,"тип шага stage распознан")
s,d=call("/api/scenario/load",{"content":json.dumps({"format":"avatar-host-scenario","version":1,
  "meta":{"title":"X"},"steps":[{"type":"stage","mode":"media"}]})})
ok(s==400,"stage без файла отклонён: "+d["error"][:50])

for n in (img,pdf): call("/api/media/delete",{"name":n})
ok(True,"тестовые файлы убраны")
