import sqlite3, time, json, html, re, unicodedata, panel
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
PAGINAS_PRIMERA = 12  # páginas de most_relevance en la primera pasada (cubre todos los coincidentes)
PAGINAS_NORMAL = 4    # páginas de most_relevance en rondas normales
PAGINAS_NEWEST = 4    # páginas de la red de seguridad (newest + time_filter)
AVISAR_EXISTENTES = True


URL = "https://api.wallapop.com/api/v3/search"
db = sqlite3.connect("vistos.db")
# 'vistos' es ahora por búsqueda (q, id) y solo guarda lo que se ha AVISADO.
# Si existe el esquema viejo (solo id) lo migramos borrándolo: la siguiente
# pasada vuelve a avisar de todos los coincidentes con la lógica nueva.
_columnas = [f[1] for f in db.execute("PRAGMA table_info(vistos)").fetchall()]
if _columnas and "q" not in _columnas:
    db.execute("DROP TABLE vistos")
    db.execute("DROP TABLE IF EXISTS iniciadas")
db.execute("CREATE TABLE IF NOT EXISTS vistos (q TEXT, id TEXT, PRIMARY KEY (q, id))")
db.execute("CREATE TABLE IF NOT EXISTS iniciadas (q TEXT PRIMARY KEY)")
db.commit()

def cargar():
    with open("busquedas.json", encoding="utf-8") as f:
        return json.load(f)

def _leer_paginas(base, paginas, solo_organic=False):
    # Lee hasta 'paginas' páginas de la API. Con solo_organic se detiene al
    # cambiar de sección: 'newest' mete ruido de 'similar_items_search_results'.
    params = dict(base)
    items, ids = [], set()
    for _ in range(paginas):
        r = requests.get(URL, params=params, headers={"X-DeviceOS": "0"},
                         impersonate="chrome", timeout=30)
        r.raise_for_status()
        j = r.json()
        seccion = j["data"]["section"]
        if solo_organic and seccion.get("type") != "organic_search_results":
            break
        nuevos = [it for it in seccion["payload"]["items"] if it["id"] not in ids]
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

def buscar(b, paginas=1):
    # La API v3 SÍ admite order_by="newest"; pero sin time_filter solo devuelve
    # ~24 h (era el bug del "solo 1 anuncio"). Estrategia doble:
    #   1) most_relevance -> catálogo completo (anuncios antiguos Y nuevos)
    #   2) newest + lastWeek -> red de seguridad para recién publicados,
    #      leyendo solo la sección orgánica (el resto es ruido "similar")
    comunes = {
        "keywords": b["q"],
        "source": "search_box",
        "latitude": LAT,
        "longitude": LON,
        "min_sale_price": b.get("min", 0),
        "max_sale_price": b["max"],
    }
    items = _leer_paginas({**comunes, "order_by": "most_relevance"}, paginas)
    items += _leer_paginas(
        {**comunes, "order_by": "newest", "time_filter": "lastWeek"},
        PAGINAS_NEWEST, solo_organic=True,
    )
    # fusionar y quitar duplicados por id
    unicos, ids = [], set()
    for it in items:
        if it["id"] not in ids:
            ids.add(it["id"])
            unicos.append(it)
    unicos.sort(key=lambda it: it.get("created_at") or 0, reverse=True)
    return unicos

def precio(it):
    p = it.get("price")
    p = p.get("amount") if isinstance(p, dict) else p
    try:
        return float(p)
    except (TypeError, ValueError):
        return None

def _clave(s):
    # minúsculas, sin acentos y sin espacios/símbolos, para comparar títulos
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)

def coincide_titulo(titulo, terminos):
    t = _clave(titulo)
    return any(_clave(x) in t for x in terminos)

def enviar(texto, formato=None):
    datos = {"chat_id": CHAT_ID, "text": texto}
    if formato:
        datos["parse_mode"] = formato
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json=datos, timeout=30,
    )
    return r.status_code == 200

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
            return True
    r = requests.post(f"{api}/sendMessage", json={
        "chat_id": CHAT_ID, "text": texto,
        "parse_mode": "HTML", "reply_markup": botones}, timeout=30)
    return r.status_code == 200

panel.iniciar(TOKEN, CHAT_ID)
enviar("Bot de Wallapop arrancado. Usa /menu para gestionar tus búsquedas")

while True:
    try:
        busquedas = cargar()
    except Exception as e:
        print("Error leyendo busquedas.json:", e)
        time.sleep(INTERVALO)
        continue
    resumenes = []
    for b in busquedas:
        q = b["q"]
        primera = db.execute("SELECT 1 FROM iniciadas WHERE q=?", (q,)).fetchone() is None
        try:
            items = buscar(b, PAGINAS_PRIMERA if primera else PAGINAS_NORMAL)
        except Exception as e:
            print("Error:", q, e)
            continue
        c = {"vistos": 0, "excluidos": 0, "titulo": 0, "bajo": 0,
             "alto": 0, "silenciosos": 0, "enviados": 0, "fallos": 0}
        palabras = {}
        for it in items:
            iid = it["id"]
            # Solo cuenta como "ya avisado" lo que de verdad se avisó (en esta búsqueda).
            if db.execute("SELECT 1 FROM vistos WHERE q=? AND id=?", (q, iid)).fetchone():
                c["vistos"] += 1
                continue
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
            terminos = [q] + b.get("otros_titulos", [])
            if not coincide_titulo(it.get("title") or "", terminos):
                c["titulo"] += 1
                continue
            if primera and not AVISAR_EXISTENTES:
                # Se memoriza sin avisar: no hay que volver a verlo.
                db.execute("INSERT OR IGNORE INTO vistos VALUES (?,?)", (q, iid))
                c["silenciosos"] += 1
                continue
            link = f"https://es.wallapop.com/item/{it.get('web_slug') or iid}"
            try:
                if enviar_anuncio(it, p, b, link):
                    db.execute("INSERT OR IGNORE INTO vistos VALUES (?,?)", (q, iid))
                    c["enviados"] += 1
                else:
                    c["fallos"] += 1
                    print("Fallo al enviar (se reintentará):", iid)
            except Exception as e:
                c["fallos"] += 1
                print("Error enviando (se reintentará):", e)
            time.sleep(1)

        pal = ", ".join(f"{html.escape(k)} ×{v}" for k, v in palabras.items())
        resumen = (
            f"📊 <b>Resumen · {html.escape(q)}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👀 Leídos: {len(items)}\n"
            f"♻️ Ya avisados: {c['vistos']}\n\n"
            f"🚫 <b>Descartados</b>\n"
            f"   • Por palabra: {c['excluidos']}" + (f" ({pal})" if pal else "") + "\n"
            f"   • Por título: {c['titulo']}\n"
            f"   • Precio bajo: {c['bajo']}\n"
            f"   • Precio alto: {c['alto']}\n"
            f"🔇 Memorizados sin avisar: {c['silenciosos']}\n"
        )
        if c["fallos"]:
            resumen += f"⚠️ Fallos de envío (se reintentan): {c['fallos']}\n"
        resumen += f"\n✅ <b>Enviados: {c['enviados']}</b>"
        print("\n" + html.unescape(re.sub(r"<[^>]+>", "", resumen)))
        # Avisa del resumen si hubo envíos, o siempre en la primera pasada
        # (para saber que la búsqueda existe aunque no dé resultados).
        if c["enviados"] > 0 or primera:
            resumenes.append(resumen)
        db.execute("INSERT OR IGNORE INTO iniciadas VALUES (?)", (q,))
        db.commit()
    for resumen in resumenes:
        try:
            if not enviar(resumen, "HTML"):
                print("Fallo al enviar el resumen")
        except Exception as e:
            print("Error enviando resumen:", e)
    time.sleep(INTERVALO)