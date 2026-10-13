# Wally 🔎📲

Bot de Telegram que vigila **Wallapop** y te avisa cada vez que aparece un anuncio
que encaja con tus búsquedas. Está pensado para cazar GPUs (RX 6800 XT, 6900 XT,
7800 XT…), pero sirve para cualquier cosa.

- Corre en Docker, sin dependencias raras.
- Lee **todo** el catálogo (anuncios nuevos **y antiguos**) y no repite avisos.
- Filtros por título, precio y palabras excluidas.
- Se gestiona desde el propio Telegram con `/menu`.

> Nota: la función `excluir` solo mira el **título**, no la descripción.

## Arquitectura

```
                            Telegram
                    ┌───────────────────┐
                    │  /menu · botones  │
                    └─────────┬─────────┘
             getUpdates       │        ▲  sendMessage / sendPhoto
                  │           ▼        │
                  │   ┌──────────────┐ │
                  └──▶│   panel.py   │─┘
                      │ (hilo menú)  │
                      └──────┬───────┘
                             │ lee/escribe
                             ▼
                      ┌──────────────┐        ┌────────────────────┐
                      │busquedas.json│◀──────▶│    wallabot.py     │
                      │(tus búsquedas)│  lee   │ (bucle principal)  │
                      └──────────────┘        └─────────┬──────────┘
                                                        │ consulta
                                                        ▼
                                              ┌────────────────────┐
                                              │ api.wallapop.com   │
                                              │  /api/v3/search    │
                                              └────────────────────┘
                                                        │
                                              ┌─────────▼──────────┐
                                              │     vistos.db      │
                                              │ (q, id) ya avisado │
                                              └────────────────────┘
```

### Componentes

| Fichero | Rol |
|---|---|
| `wallabot.py` | Bucle principal: busca, filtra, avisa y manda el resumen. |
| `panel.py` | Hilo que atiende el menú de Telegram (`/menu`): añade/edita/borra búsquedas en `busquedas.json`. |
| `busquedas.json` | Tus búsquedas (lo edita el panel, o tú a mano). |
| `secrets.json` | `TOKEN` del bot y `CHAT_ID`. **Nunca se sube al repo.** |
| `vistos.db` | SQLite con las parejas `(q, id)` ya avisadas. |
| `gestor.py` | Gestor por consola (alternativa al menú de Telegram). |
| `Dockerfile` · `docker-compose.yml` · `casaos-app.yml` | Despliegue. |

### Estrategia de búsqueda (por qué no se pierde nada)

Para cada búsqueda se lanzan **dos consultas** a la API de Wallapop y se fusionan:

1. **`order_by=most_relevance`** → trae el **catálogo completo** (antiguos **y** nuevos).
   - 12 páginas la primera vez (`PAGINAS_PRIMERA`) y 4 en las rondas normales (`PAGINAS_NORMAL`).
   - La API devuelve hasta 1600+ resultados y no termina; por eso hay un tope de páginas.
2. **`order_by=newest` + `time_filter=lastWeek`** → **red de seguridad** para lo recién publicado.
   - Lee solo la sección `organic_search_results` (el resto es ruido de "similares").
   - Sin `time_filter`, `newest` solo devuelve ~24 h (de ahí el clásico «solo 1 anuncio»).

Después se quitan duplicados por `id`, se ordena por fecha y se descartan los ya avisados.

### Lógica de "vistos" (importante)

`vistos` guarda **solo lo que de verdad se te ha avisado**, y por búsqueda: la clave es `(q, id)`.

- Lo descartado por los filtros **no** se memoriza: si cambias `max`, `min`, `excluir` u
  `otros_titulos`, ese anuncio vuelve a ser candidato y se te avisa.
- Si un envío falla (Telegram caído, red…), **no** se marca y se **reintenta** en la ronda siguiente.
- Si tenías una `vistos.db` del esquema antiguo (solo `id`), se **migra automáticamente**
  y en el primer arranque te re-avisará de todos los coincidentes (una sola vez).

## Configuración

### `secrets.json`

```json
{
  "TOKEN": "123456:ABC-tu-token-de-BotFather",
  "CHAT_ID": "123456789"
}
```

- `TOKEN`: créalo con [@BotFather](https://t.me/BotFather).
- `CHAT_ID`: tu id de Telegram (puedes verlo con [@userinfobot](https://t.me/userinfobot)).

### `busquedas.json`

```json
[
  {
    "q": "rx 6800 xt",
    "min": 200,
    "max": 450,
    "excluir": ["roto", "averiado", "para piezas"],
    "otros_titulos": ["radeon 6800 xt", "6800xt"]
  }
]
```

| Campo | Qué es |
|---|---|
| `q` | Texto que se manda a Wallapop. |
| `min` / `max` | Rango de precio en € (se aplica ya en la API). |
| `excluir` | Palabras que, si aparecen en el **título**, descartan el anuncio. |
| `otros_titulos` | Títulos alternativos que también valen. |

La comparación de títulos ignora acentos, mayúsculas y espacios:
`"RX 6800 XT"`, `"rx6800xt"` y `"Radeon Rx 6800XT"` coinciden.

### Variables del código

| Constante (`wallabot.py`) | Por defecto | Qué hace |
|---|---|---|
| `INTERVALO` | `120` | Segundos entre rondas (no bajes de 60). |
| `PAGINAS_PRIMERA` | `12` | Páginas de `most_relevance` en la 1ª pasada. |
| `PAGINAS_NORMAL` | `4` | Páginas de `most_relevance` en rondas normales. |
| `PAGINAS_NEWEST` | `4` | Páginas de la red de seguridad `newest`. |
| `AVISAR_EXISTENTES` | `True` | Avisar también de los anuncios antiguos al añadir una búsqueda. |
| `LAT` / `LON` | Madrid | Coordenadas para la búsqueda. |

## Crearlo tú mismo (despliegue)

### 1. Requisitos
- Python 3.12 o Docker.
- Un bot de Telegram (token de BotFather) y tu `CHAT_ID`.
- `curl_cffi` (única dependencia, ver `requirements.txt`).

### 2. Local (sin Docker)

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
# crea secrets.json y busquedas.json en la raíz
./venv/bin/python wallabot.py
```

Luego, en Telegram: `/start` o `/menu`.

### 3. Docker

```bash
docker build -t wally:latest .
docker run -d --name wally --restart unless-stopped \
  -v /ruta/secrets.json:/app/secrets.json:ro \
  -v /ruta/busquedas.json:/app/busquedas.json \
  -v /ruta/vistos.db:/app/vistos.db \
  wally:latest
```

### 4. Docker Compose

```bash
docker compose up -d --build
```

### 5. CasaOS (Ubuntu Server LTS)

1. Copia `secrets.json` y `busquedas.json` a `/DATA/AppData/wally/`.
2. Construye la imagen: `docker build -t wally:latest .`
3. En CasaOS: **Install a customized app** → pega el contenido de `casaos-app.yml`.
4. El contenedor usa `restart: unless-stopped`, así que se levanta solo tras reinicios.

Los volúmenes montan `secrets.json` (solo lectura), `busquedas.json` y `vistos.db`
dentro de `/app`, de modo que los datos viven en el servidor y no dentro de la imagen.

## Gestión desde Telegram

`/menu` (o `/start`) abre el panel:

- **➕ Añadir búsqueda** → te pide `q`, `min`, `max`, `excluir` y `otros_titulos`.
- Pulsa una búsqueda para **editar** sus campos o **borrarla**.
- Los resúmenes de cada ronda se mandan **una sola vez, al final**, y solo si hubo novedades.

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).

## Licencia

[GNU AGPL-3.0](LICENSE).

## Ayuda

¿Dudas con la instalación? Pregunta a Devin: https://deepwiki.com/ag4pornis/Wally
