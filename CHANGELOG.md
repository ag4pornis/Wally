# Changelog

Todos los cambios relevantes de Wally.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

## [0.2.0] - 2026-10-13

### Added
- `README.md` con arquitectura, configuración y guía de despliegue (Docker, Compose y CasaOS).
- `CHANGELOG.md`.
- Aviso `⚠️ Fallos de envío (se reintentan)` en el resumen.
- Variable de entorno `WALLY_DATA` para elegir la carpeta de datos.

### Changed
- Despliegue: en vez de montar ficheros sueltos, se monta **una sola carpeta**
  (`/DATA/AppData/wally` → `/data`) y el código resuelve ahí `secrets.json`,
  `busquedas.json` y `vistos.db`.
- `vistos` pasa a ser **por búsqueda** (clave `(q, id)`) y **solo memoriza lo que se ha avisado**.
- El resumen muestra `♻️ Ya avisados` y se envía **solo si hubo novedades** (o en la primera pasada
  de cada búsqueda). Se eliminó el contador `Nuevos`, que era engañoso.
- `enviar()` y `enviar_anuncio()` ahora comprueban la respuesta de Telegram y devuelven `bool`.
- Migración automática del esquema antiguo de `vistos`.

### Fixed
- Los anuncios descartados por los filtros ya no se marcan como vistos: al cambiar
  `max`, `min`, `excluir` u `otros_titulos` vuelven a ser candidatos y se notifican.
- Los envíos fallidos ya no se pierden: no se marcan y se reintentan en la ronda siguiente.
- Corregido el comentario que afirmaba que la API v3 no admite `order_by="newest"`
  (sí lo admite; sin `time_filter` solo devuelve ~24 h).
- **Añadir/editar búsquedas desde el panel ya no falla.** Al montar `busquedas.json`
  como fichero suelto, el guardado atómico (`os.replace`) sobre un punto de montaje
  devolvía `EBUSY` y la búsqueda nunca se guardaba.
- **`vistos.db` ya no se crea como carpeta.** Al montar una carpeta de datos, SQLite
  crea el fichero por sí mismo y desaparece el `unable to open database file`.

### Removed
- El contador `🆕 Nuevos` del resumen (contaba también los anuncios descartados).

## [0.1.0] - 2026-10-12

### Added
- Búsqueda en Wallapop con doble consulta: `most_relevance` (catálogo completo,
  antiguos y nuevos) + red de seguridad `newest` + `time_filter=lastWeek`,
  leyendo solo la sección `organic_search_results`.
- Filtro por título (`q` + `otros_titulos`, comparando sin acentos ni espacios),
  por rango de precio y por palabras excluidas.
- Avisos por Telegram con foto, precio, ubicación, envío, antigüedad y enlace al anuncio.
- Panel de gestión por Telegram (`/menu`): añadir, editar y borrar búsquedas.
- Resúmenes por ronda, enviados una sola vez al final.
- Despliegue con Docker, Docker Compose y CasaOS.
- Gestor por consola (`gestor.py`).
