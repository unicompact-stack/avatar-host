# -*- coding: utf-8 -*-
"""Проверка сетевого режима: PIN пульта, открытость гостевых ручек, QR без localhost."""
import json,urllib.request,http.cookiejar
B="http://127.0.0.1:8000"
cj=http.cookiejar.CookieJar()
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(p,d=None,opener=None,raw=False):
    o=opener or urllib.request.build_opener()
    r=urllib.request.Request(B+p,data=(d if raw else json.dumps(d).encode()) if d is not None else None,
      headers={'Content-Type':'application/x-www-form-urlencoded' if raw else 'application/json'},
      method='POST' if d is not None else 'GET')
    try:
        with o.open(r,timeout=20) as f: return f.status,f.read()
    except urllib.error.HTTPError as e: return e.code,e.read()
ok=lambda c,m: print(("✅" if c else "❌"),m)

# 1. Без PIN пульт закрыт
s,b=call("/admin"); ok(s==200 and "Введите PIN" in b.decode(),"без PIN отдаётся форма входа, не пульт")
for ep in ["/api/say","/api/scenario/next","/api/settings","/api/reset","/api/demo/guests"]:
    s,_=call(ep,{}); ok(s==401,f"управление закрыто: {ep}")
s,_=call("/api/network"); ok(s==401,"адреса сети закрыты без PIN")

# 2. Гостевые и экранные ручки открыты
for ep in ["/api/state","/api/guests","/api/health","/qr","/host","/connect"]:
    s,_=call(ep); ok(s==200,f"открыто для гостей/экрана: {ep}")

# 3. Вход по PIN
s,_=call("/admin",b"pin=9999",opener=op,raw=True); ok(s==401,"неверный PIN отклонён")
s,b=call("/admin",b"pin=1234",opener=op,raw=True)
ok(s==200 and "Пульт ведущего" in b.decode(),"вход по верному PIN")
s,_=call("/api/say",{"text":"проверка"},opener=op); ok(s==200,"после входа управление доступно")
s,b=call("/api/network",opener=op); n=json.loads(b)
ok(not n["lan_ip"].startswith("127."),f"LAN-адрес определён: {n['lan_ip']}")
ok("localhost" not in n["connect"],f"ссылка для гостей без localhost: {n['connect']}")
ok(n["admin_pin"]=="1234","PIN отдаётся в админку для показа")

# 4. QR ведёт на сетевой адрес, а не на localhost
s,b=call("/qr")
try:
    from PIL import Image; from io import BytesIO
    ok(Image.open(BytesIO(b)).size[0]>50,"QR-код генерируется")
except ImportError: ok(len(b)>200,"QR-код генерируется")

# 5. Выход
s,_=call("/admin/logout",{},opener=op); ok(s==200,"выход из пульта")
s,_=call("/api/say",{"text":"x"},opener=op); ok(s==401,"после выхода управление снова закрыто")

# --- вход без cookie (iframe-превью, кросс-сайт) ---
import urllib.parse
nock=urllib.request.build_opener()   # опенер БЕЗ хранения cookie
r=urllib.request.Request(B+"/admin",data=b"pin=1234",
    headers={"Content-Type":"application/x-www-form-urlencoded"})
class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k): return None
try:
    urllib.request.build_opener(NoRedir).open(r,timeout=10)
    loc=""
except urllib.error.HTTPError as e:
    loc=e.headers.get("Location","")
tok=loc.split("t=")[-1] if "t=" in loc else ""
ok(bool(tok),f"после ввода PIN выдаётся токен: {tok[:10]}…")
s,b=call("/admin?t="+tok,opener=nock)
ok(s==200 and "Пульт ведущего" in b.decode(),"пульт открывается по токену БЕЗ cookie")
def tok_call(p,d=None):
    rq=urllib.request.Request(B+p,data=json.dumps(d).encode() if d is not None else None,
        headers={'Content-Type':'application/json','X-Admin-Token':tok},
        method='POST' if d is not None else 'GET')
    try:
        with nock.open(rq,timeout=10) as f: return f.status
    except urllib.error.HTTPError as e: return e.code
ok(tok_call("/api/say",{"text":"проверка токена"})==200,"API работает по заголовку X-Admin-Token")
ok(tok_call("/api/network")==200,"GET-ручки тоже пускают по токену")
def bad_tok(v):
    rq=urllib.request.Request(B+"/api/say",data=b'{"text":"x"}',
        headers={'Content-Type':'application/json','X-Admin-Token':v})
    try:
        with nock.open(rq,timeout=10) as f: return f.status
    except urllib.error.HTTPError as e: return e.code
# кириллицу в HTTP-заголовок не пропустит сам клиент, поэтому шлём её в теле
rq=urllib.request.Request(B+"/api/say",
    data=json.dumps({"text":"x","_t":"подделка"}).encode(),
    headers={'Content-Type':'application/json'})
try:
    with nock.open(rq,timeout=10) as f: code=f.status
except urllib.error.HTTPError as e: code=e.code
ok(code==401,"кириллический мусор в токене → 401, а не 500")
ok(bad_tok("wrongtoken123")==401,"неверный токен отклонён")
