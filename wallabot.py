import sqlite3, time, json
from curl_cffi import requests
import os

def _secretos():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json")
    with open(ruta, encoding="utf-8") as f:
        s = json.load(f)
    return s["TOKEN"], str(s["CHAT_ID"])

TOKEN, CHAT_ID = _secretos()

LAT, LON = 40.4168, -3.7038   # cambia a tu zona
INTERVALO = 120               # segundos; no bajes de 60
PAGINAS_PRIMERA = 4   # páginas (unos 40 anuncios cada una) a leer en la primera pasada
AVISAR_EXISTENTES = True


URL = "https://api.wallapop.com/api/v3/search"
db = sqlite3.connect("vistos.db")
db.execute("CREATE TABLE IF NOT EXISTS vistos (id TEXT PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS iniciadas (q TEXT PRIMARY KEY)")

def cargar():
    with open("busquedas.json", encoding="utf-8") as f:
        return json.load(f)

def buscar(b, paginas=1):
    base = {"keywords": b["q"], "order_by": "newest",
            "source": "search_box", "latitude": LAT, "longitude": LON,
            "max_sale_price": b["max"]}
    params = dict(base)
    items, ids = [], set()
    for _ in range(paginas):
        r = requests.get(URL, params=params, headers={"X-DeviceOS": "0"},
                         impersonate="chrome", timeout=30)
        r.raise_for_status()
        j = r.json()
        pagina = j["data"]["section"]["payload"]["items"]
        nuevos = [it for it in pagina if it["id"] not in ids]
        if not nuevos:
            break  # la página no aportó nada nuevo
        items += nuevos
        ids.update(it["id"] for it in nuevos)
        nxt = (j.get("meta") or {}).get("next_page")
        if not nxt:
            break
        params = {**base, "next_page": nxt}
        time.sleep(1)
    return items

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
        primera = db.execute("SELECT 1 FROM iniciadas WHERE q=?", (b["q"],)).fetchone() is None
        try:
            items = buscar(b, PAGINAS_PRIMERA if primera else 1)
        except Exception as e:
            print("Error:", b["q"], e)
            continue
        c = {"vistos": 0, "nuevos": 0, "excluidos": 0, "bajo": 0,
             "alto": 0, "silenciosos": 0, "enviados": 0}
        palabras = {}
        for it in items:
            iid = it["id"]
            if db.execute("SELECT 1 FROM vistos WHERE id=?", (iid,)).fetchone():
                c["vistos"] += 1
                continue
            db.execute("INSERT INTO vistos VALUES (?)", (iid,))
            c["nuevos"] += 1
            p = precio(it)
            titulo = (it.get("title") or "").lower()
            mala = [x for x in b.get("excluir", []) if x in titulo]
            if mala:
                c["excluidos"] += 1
                for x in mala:
                    palabras[x] = palabras.get(x, 0) + 1
                continue
            if p is not None and p < b.get("min", 0):
                c["bajo"] += 1
                continue
            if p is not None and p > b["max"]:
                c["alto"] += 1
                continue
            if primera and not AVISAR_EXISTENTES:
                c["silenciosos"] += 1
                continue
            link = f"https://es.wallapop.com/item/{it.get('web_slug') or iid}"
            enviar(f"{it.get('title')}\n{p} €\n{link}")
            c["enviados"] += 1
            time.sleep(1)

        resumen = (
            f"== {b['q']} ==\n"
            f"Leídos: {len(items)}\n"
            f"  Ya vistos (no se reenvían): {c['vistos']}\n"
            f"  Nuevos: {c['nuevos']}\n"
            f"    Excluidos por palabra: {c['excluidos']} {palabras or ''}\n"
            f"    Excluidos por precio bajo (< min): {c['bajo']}\n"
            f"    Excluidos por precio alto (> max): {c['alto']}\n"
            f"    Memorizados sin avisar (primera pasada): {c['silenciosos']}\n"
            f"    ENVIADOS a Telegram: {c['enviados']}"
        )
        print("\n" + resumen)
        if c["nuevos"] > 0:
            enviar(resumen)
        db.execute("INSERT OR IGNORE INTO iniciadas VALUES (?)", (b["q"],))
        db.commit()
    time.sleep(INTERVALO)