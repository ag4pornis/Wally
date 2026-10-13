import json, os, threading, time, html
from curl_cffi import requests

# Misma carpeta de datos que wallabot.py: configurable con WALLY_DATA y, si no,
# la del propio script. Repetimos la línea porque importar wallabot aquí sería
# circular.
DATA = os.environ.get("WALLY_DATA") or os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(DATA, "busquedas.json")
lock = threading.Lock()
estado = {}
_token = _chat = ""

PREGUNTAS = {
    "q": "Escribe el nuevo texto de búsqueda:",
    "min": "Escribe el nuevo precio mínimo en € (número):",
    "max": "Escribe el nuevo precio máximo en € (número):",
    "excluir": "Escribe las palabras a excluir separadas por comas (o - para vaciar):",
    "otros_titulos": "Escribe otros títulos alternativos separados por comas (o - para vaciar):",
}


def leer():
    with lock:
        try:
            with open(ARCHIVO, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []


def guardar(lista):
    with lock:
        tmp = ARCHIVO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ARCHIVO)


def api(metodo, **datos):
    try:
        r = requests.post(f"https://api.telegram.org/bot{_token}/{metodo}",
                          json=datos, timeout=40)
        return r.json()
    except Exception as e:
        print("Panel error:", e)
        return {}


def decir(texto):
    api("sendMessage", chat_id=_chat, text=texto)


def mostrar(texto, botones, mid=None):
    datos = {"chat_id": _chat, "text": texto, "parse_mode": "HTML",
             "reply_markup": {"inline_keyboard": botones}}
    if mid:
        datos["message_id"] = mid
        api("editMessageText", **datos)
    else:
        api("sendMessage", **datos)


def menu(mid=None):
    lista = leer()
    botones = [[{"text": f"{b['q']} · {b.get('min', 0)}-{b['max']} €",
                 "callback_data": f"ver:{i}"}] for i, b in enumerate(lista)]
    botones.append([{"text": "➕ Añadir búsqueda", "callback_data": "add"}])
    texto = "🔎 <b>Búsquedas activas</b>\n" + (
        "Pulsa una para editarla o borrarla." if lista else "No hay ninguna todavía.")
    mostrar(texto, botones, mid)


def ver(i, mid=None):
    lista = leer()
    if not 0 <= i < len(lista):
        return menu(mid)
    b = lista[i]
    ex = ", ".join(b.get("excluir", [])) or "—"
    ot = ", ".join(b.get("otros_titulos", [])) or "—"
    texto = (f"🔎 <b>{html.escape(b['q'])}</b>\n"
             f"💰 {b.get('min', 0)} – {b['max']} €\n"
             f"🚫 Excluir: {html.escape(ex)}\n"
             f"🅰️ Otros títulos: {html.escape(ot)}")
    botones = [
        [{"text": "✏️ Nombre", "callback_data": f"ed:q:{i}"},
         {"text": "✏️ Mín", "callback_data": f"ed:min:{i}"}],
        [{"text": "✏️ Máx", "callback_data": f"ed:max:{i}"},
         {"text": "✏️ Excluir", "callback_data": f"ed:excluir:{i}"}],
        [{"text": "✏️ Otros títulos", "callback_data": f"ed:otros_titulos:{i}"}],
        [{"text": "🗑 Borrar", "callback_data": f"del:{i}"},
         {"text": "⬅️ Volver", "callback_data": "menu"}],
    ]
    mostrar(texto, botones, mid)


def callback(data, mid):
    p = data.split(":")
    a = p[0]
    if a == "menu":
        estado.clear()
        menu(mid)
    elif a == "ver":
        estado.clear()
        ver(int(p[1]), mid)
    elif a == "add":
        estado.clear()
        estado["st"] = {"accion": "add", "paso": "q", "datos": {}}
        decir("¿Qué quieres buscar? (/cancelar para salir)")
    elif a == "ed":
        estado.clear()
        estado["st"] = {"accion": "editar", "campo": p[1], "i": int(p[2])}
        decir(PREGUNTAS[p[1]] + "\n(/cancelar para salir)")
    elif a == "del":
        i = int(p[1])
        lista = leer()
        if 0 <= i < len(lista):
            mostrar(f"¿Borrar <b>{html.escape(lista[i]['q'])}</b>?",
                    [[{"text": "✅ Sí, borrar", "callback_data": f"delok:{i}"},
                      {"text": "❌ No", "callback_data": f"ver:{i}"}]], mid)
    elif a == "delok":
        i = int(p[1])
        lista = leer()
        if 0 <= i < len(lista):
            lista.pop(i)
            guardar(lista)
        menu(mid)


def palabras(txt):
    if txt == "-":
        return []
    return [x.strip().lower() for x in txt.split(",") if x.strip()]


def lista_textos(txt):
    if txt == "-":
        return []
    return [x.strip() for x in txt.split(",") if x.strip()]


def texto_recibido(txt):
    txt = txt.strip()
    if txt.startswith("/"):
        cmd = txt.split()[0].lower()
        estado.clear()
        if cmd in ("/menu", "/start"):
            return menu()
        if cmd == "/cancelar":
            return decir("Cancelado.")
        return
    st = estado.get("st")
    if not st:
        return

    if st["accion"] == "editar":
        lista = leer()
        i = st["i"]
        if not 0 <= i < len(lista):
            estado.clear()
            return menu()
        campo = st["campo"]
        if campo == "q":
            if not txt:
                return decir("Escribe un texto.")
            lista[i]["q"] = txt
        elif campo in ("min", "max"):
            try:
                lista[i][campo] = int(txt)
            except ValueError:
                return decir("Pon un número entero.")
        elif campo == "otros_titulos":
            lista[i]["otros_titulos"] = lista_textos(txt)
        else:
            lista[i]["excluir"] = palabras(txt)
        guardar(lista)
        estado.clear()
        return ver(i)

    d = st["datos"]
    paso = st["paso"]
    if paso == "q":
        if not txt:
            return decir("Escribe un texto.")
        d["q"] = txt
        st["paso"] = "min"
        return decir("Precio mínimo en € (0 si no quieres mínimo):")
    if paso in ("min", "max"):
        try:
            d[paso] = int(txt)
        except ValueError:
            return decir("Pon un número entero.")
        if paso == "min":
            st["paso"] = "max"
            return decir("Precio máximo en €:")
        st["paso"] = "excluir"
        return decir("Palabras a excluir separadas por comas (o - para ninguna):")
    if paso == "excluir":
        d["excluir"] = palabras(txt)
        st["paso"] = "otros_titulos"
        return decir("Otros títulos alternativos separados por comas (o - para ninguno):")
    d["otros_titulos"] = lista_textos(txt)
    lista = leer()
    lista.append(d)
    guardar(lista)
    estado.clear()
    menu()


def manejar(u):
    if "callback_query" in u:
        cq = u["callback_query"]
        if str(cq["message"]["chat"]["id"]) != _chat:
            return
        api("answerCallbackQuery", callback_query_id=cq["id"])
        callback(cq["data"], cq["message"]["message_id"])
    elif "message" in u:
        m = u["message"]
        if str(m["chat"]["id"]) == _chat and "text" in m:
            texto_recibido(m["text"])


def bucle():
    offset = None
    while True:
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        try:
            r = requests.get(f"https://api.telegram.org/bot{_token}/getUpdates",
                             params=params, timeout=45)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                try:
                    manejar(u)
                except Exception as e:
                    print("Panel error:", e)
        except Exception as e:
            print("Panel error de red:", e)
            time.sleep(5)


def iniciar(token, chat_id):
    global _token, _chat
    _token, _chat = token, str(chat_id)
    api("setMyCommands", commands=[{"command": "menu", "description": "Gestionar búsquedas"}])
    threading.Thread(target=bucle, daemon=True).start()