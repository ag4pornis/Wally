import sqlite3, time, json, html, re, panel
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

def enviar(texto, formato=None):
    datos = {"chat_id": CHAT_ID, "text": texto}
    if formato:
        datos["parse_mode"] = formato
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json=datos, timeout=30,
    )

def tiempo(it):
    ms = it.get("created_at")
    if not ms:
        return "desconocido"
    m = max(0, int((time.time() * 1000 - ms) / 60000))
    if m < 60:
        return f"hace {m} min"
    if m < 1440:
        return f"hace {m // 60} h"
    return f"hace {m // 1440} d"

def enviar_anuncio(it, p, b, link):
    loc = it.get("location") or {}
    ciudad = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x) or "?"
    sh = it.get("shipping") or {}
    envio = "Disponible" if sh.get("item_is_shippable") and sh.get("user_allows_shipping") else "No"
    reservado = " (RESERVADO)" if (it.get("reserved") or {}).get("flag") else ""
    texto = (
        f"🚨 <b>Nuevo producto</b>{reservado}\n\n"
        f"📝 <b>{html.escape(it.get('title') or '')}</b>\n"
        f"💰 Precio: {p} €\n"
        f"📍 Ubicación: {html.escape(ciudad)}\n"
        f"📦 Envío: {envio}\n"
        f"⏱️ Publicado: {tiempo(it)}\n\n"
        f"🏷️ Alerta: {html.escape(b['q'])}"
    )
    botones = {"inline_keyboard": [[{"text": "🔗 Ver producto", "url": link}]]}
    imgs = it.get("images") or []
    foto = imgs[0]["urls"].get("big") if imgs else None
    api = f"https://api.telegram.org/bot{TOKEN}"
    if foto:
        r = requests.post(f"{api}/sendPhoto", json={
            "chat_id": CHAT_ID, "photo": foto, "caption": texto,
            "parse_mode": "HTML", "reply_markup": botones}, timeout=30)
        if r.status_code == 200:
            return
    requests.post(f"{api}/sendMessage", json={
        "chat_id": CHAT_ID, "text": texto,
        "parse_mode": "HTML", "reply_markup": botones}, timeout=30)

panel.iniciar(TOKEN, CHAT_ID)
enviar("Bot de Wallapop arrancado")

while True:
    try:
        busquedas = cargar()
    except Exception as e:
        print("Error leyendo busquedas.json:", e)
        time.sleep(INTERVALO)
        continue
    hubo = False
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
            try:
                enviar_anuncio(it, p, b, link)
                c["enviados"] += 1
            except Exception as e:
                print("Error enviando:", e)
            time.sleep(1)

        pal = ", ".join(f"{html.escape(k)} ×{v}" for k, v in palabras.items())
        resumen = (
            f"📊 <b>Resumen · {html.escape(b['q'])}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👀 Leídos: {len(items)}\n"
            f"♻️ Ya vistos: {c['vistos']}\n"
            f"🆕 Nuevos: {c['nuevos']}\n\n"
            f"🚫 <b>Descartados</b>\n"
            f"   • Por palabra: {c['excluidos']}" + (f" ({pal})" if pal else "") + "\n"
            f"   • Precio bajo: {c['bajo']}\n"
            f"   • Precio alto: {c['alto']}\n"
            f"🔇 Memorizados sin avisar: {c['silenciosos']}\n\n"
            f"✅ <b>Enviados: {c['enviados']}</b>"
        )
        print("\n" + html.unescape(re.sub(r"<[^>]+>", "", resumen)))
        if c["nuevos"] > 0:
            hubo = True
            try:
                enviar(resumen, "HTML")
            except Exception as e:
                print("Error enviando resumen:", e)
        db.execute("INSERT OR IGNORE INTO iniciadas VALUES (?)", (b["q"],))
        db.commit()
    if hubo:
        panel.menu()
    time.sleep(INTERVALO)