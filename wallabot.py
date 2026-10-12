import sqlite3, time, json
from curl_cffi import requests

TOKEN = "TOKEN_ROTADO"
CHAT_ID = "CHAT_ID"
LAT, LON = 40.4168, -3.7038   # cambia a tu zona
INTERVALO = 120               # segundos; no bajes de 60

URL = "https://api.wallapop.com/api/v3/search"
db = sqlite3.connect("vistos.db")
db.execute("CREATE TABLE IF NOT EXISTS vistos (id TEXT PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS iniciadas (q TEXT PRIMARY KEY)")

def cargar():
    with open("busquedas.json", encoding="utf-8") as f:
        return json.load(f)

def buscar(b):
    r = requests.get(
        URL,
        params={"keywords": b["q"], "order_by": "newest",
                "source": "search_box", "latitude": LAT, "longitude": LON,
                "max_sale_price": b["max"]},
        headers={"X-DeviceOS": "0"},
        impersonate="chrome", timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["section"]["payload"]["items"]

def precio(it):
    p = it.get("price")
    p = p.get("amount") if isinstance(p, dict) else p
    try:
        return float(p)
    except (TypeError, ValueError):
        return None

def enviar(texto):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": texto}, timeout=30,
    )

enviar("Bot de Wallapop arrancado")

while True:
    try:
        busquedas = cargar()
    except Exception as e:
        print("Error leyendo busquedas.json:", e)
        time.sleep(INTERVALO)
        continue
    for b in busquedas:
        try:
            items = buscar(b)
        except Exception as e:
            print("Error:", b["q"], e)
            continue
        primera = db.execute("SELECT 1 FROM iniciadas WHERE q=?", (b["q"],)).fetchone() is None
        for it in items:
            iid = it["id"]
            if db.execute("SELECT 1 FROM vistos WHERE id=?", (iid,)).fetchone():
                continue
            db.execute("INSERT INTO vistos VALUES (?)", (iid,))
            p = precio(it)
            titulo = (it.get("title") or "").lower()
            if any(x in titulo for x in b.get("excluir", [])):
                continue
            if p is not None and p < b.get("min", 0):
                continue
            if primera or (p is not None and p > b["max"]):
                continue  # primera pasada: solo memoriza, no avisa
            link = f"https://es.wallapop.com/item/{it.get('web_slug') or iid}"
            enviar(f"{it.get('title')}\n{p} €\n{link}")
        db.execute("INSERT OR IGNORE INTO iniciadas VALUES (?)", (b["q"],))
        db.commit()
    time.sleep(INTERVALO)
