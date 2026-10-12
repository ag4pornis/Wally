import json

ARCHIVO = "busquedas.json"

def cargar():
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def guardar(lista):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)

def listar(lista):
    if not lista:
        print("(no hay búsquedas)")
    for i, x in enumerate(lista, 1):
        ex = ", ".join(x.get("excluir", [])) or "-"
        print(f"{i}. {x['q']} | {x.get('min', 0)}-{x['max']} € | excluye: {ex}")

def numero(texto, actual):
    while True:
        v = input(texto).strip()
        if not v:
            return actual
        try:
            return int(v)
        except ValueError:
            print("Pon un número.")

def pedir(base=None):
    base = base or {"q": "", "min": 0, "max": 100, "excluir": []}
    q = input(f"Qué buscar [{base['q']}]: ").strip() or base["q"]
    if not q:
        return None
    mn = numero(f"Precio mínimo [{base.get('min', 0)}]: ", base.get("min", 0))
    mx = numero(f"Precio máximo [{base['max']}]: ", base["max"])
    actual = ", ".join(base.get("excluir", []))
    ex = input(f"Palabras a excluir, separadas por comas [{actual}] (- para vaciar): ").strip()
    if ex == "-":
        excluir = []
    elif ex:
        excluir = [p.strip().lower() for p in ex.split(",") if p.strip()]
    else:
        excluir = base.get("excluir", [])
    return {"q": q, "min": mn, "max": mx, "excluir": excluir}

def elegir(lista, texto):
    try:
        i = int(input(texto)) - 1
        return i if 0 <= i < len(lista) else None
    except ValueError:
        return None

while True:
    lista = cargar()
    print("\n--- Búsquedas actuales ---")
    listar(lista)
    op = input("\n1) Añadir  2) Editar  3) Borrar  0) Salir: ").strip()
    if op == "1":
        nueva = pedir()
        if nueva:
            lista.append(nueva)
            guardar(lista)
    elif op == "2":
        i = elegir(lista, "Número a editar: ")
        if i is not None:
            nueva = pedir(lista[i])
            if nueva:
                lista[i] = nueva
                guardar(lista)
    elif op == "3":
        i = elegir(lista, "Número a borrar: ")
        if i is not None:
            lista.pop(i)
            guardar(lista)
    elif op == "0":
        break