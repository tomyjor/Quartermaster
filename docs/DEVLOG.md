# Quartermaster

**Decision Intelligence System for EVE Online (Jita Trading)**

## Novedad v0.5.0 — Fase 2 (primera porción): Dashboard en NiceGUI

⚠️ **Esta es la pieza con MENOS validación de todo el proyecto hasta ahora.** `nicegui` nunca se
   instaló en el entorno donde se escribió (sin red). A diferencia de FastAPI (donde después
   tuvimos corridas reales confirmando todo), esto todavía no se probó ni una vez con la librería
   real. Escrito con cuidado contra la documentación pública de NiceGUI 1.4, verificado con un
   stub hecho a mano (cero errores de import/lógica de Python), pero el renderizado real en un
   browser -- nombres de props exactos, formato de `columnDefs` de AG-Grid, etc. -- es la primera
   vez que se ejecuta de verdad. Esperá encontrar más ajustes acá que en cualquier otra parte.

✅ `presentation/api_client.py`: se movió de `streamlit_app/` a `presentation/` directo -- ahora
   es compartido entre Streamlit y NiceGUI, ninguna UI depende de la otra.
✅ `presentation/ui/`: Dashboard (única página por ahora) corriendo como proceso separado en el
   puerto 8502, cliente de la misma API que Streamlit -- mismo patrón, distinto framework.
   Usa `ui.aggrid` (AG-Grid) para la tabla, que es la razón original por la que se eligió NiceGUI
   sobre Reflex (mejor manejo de tablas grandes).

### Cómo probarlo

```powershell
pip install nicegui
python src\presentation\ui\main.py
```

Con la API (puerto 8000) ya corriendo en otra terminal. Abre en `http://localhost:8502` (no
choca con Streamlit en 8501 si lo tenés corriendo también -- podés tener las tres cosas
corriendo en paralelo: API + Streamlit + NiceGUI).

**Pegame cualquier error tal cual salga** -- es información real de una librería que nunca se
ejecutó antes en este proyecto.

## Novedad v0.4.0 — Fase 1: API FastAPI + background jobs (Smart Auto-Seed)

⚠️ **Escrito en un entorno sin `fastapi`/`pydantic`/`uvicorn`/`apscheduler` instalados y sin red.**
   Toda la lógica real (`presentation/api/services.py`) está 100% testeada con datos reales.
   El routing/serialización HTTP se verificó con stubs hechos a mano, pero NO se corrió con las
   librerías reales todavía. Ver `docs/ROADMAP_Y_PENDIENTES.md` para el paso a paso de cómo
   probarlo por primera vez y qué reportar si algo falla.

✅ **Smart Auto-Seed**: `MarketOrdersImporter.import_full_region()` trae el order book COMPLETO
   de una región en un solo fetch paginado (ESI permite omitir `type_id`) -- reemplaza tanto al
   muestreo aleatorio como al concepto de "cuántos ítems trackear a mano". El historial de volumen
   se pide después, SOLO para los type_ids que resultaron con actividad real (nunca para el
   catálogo `published=1` completo). Orquestado por `infrastructure/jobs/seed_job.py`.
✅ **API FastAPI** (`presentation/api/`): endpoints para oportunidades (`scope=discovery|tracked`,
   sort_by score/roi/liquidity), tracked items (track/untrack/untrack_many/untrack_all, todos
   atómicos), búsqueda, y sync (trigger + status). Streamlit NO fue tocado todavía -- sigue
   llamando a los use cases directo, migrarlo es el siguiente paso.
✅ **Sin Celery/Redis**: `APScheduler` corriendo en el mismo proceso (2 jobs periódicos: order
   book cada 20 min, historial completo cada 12 hs). Decisión deliberada -- ver
   `docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md` §4 para el razonamiento.
✅ Tablas nuevas `sync_status` / `system_state` + WAL mode, vía migración NO destructiva
   (`scripts/migrate_v3_add_sync_tables.py` -- a diferencia de `setup_database.py`, no borra nada).

### Cómo probarlo por primera vez (Windows)

**No uses `pip install -e ".[api]"`** -- tenía un bug real en `pyproject.toml`
(ya arreglado, ver más abajo si igual querés el editable install) y de
todas formas no hace falta: nada en este proyecto depende de una
instalación "real", todo usa `sys.path` manual. Instalá directo:

```powershell
pip install fastapi "uvicorn[standard]" apscheduler
```

La migración de la base **no necesita `PYTHONPATH`** (es sqlite3 puro,
no importa nada de `src/`) -- y `PYTHONPATH=src comando` es sintaxis de
bash, no funciona en `cmd.exe` ni en PowerShell:

```powershell
python scripts\migrate_v3_add_sync_tables.py
```

Para levantar el servidor, usá `python -m uvicorn` en vez del comando
`uvicorn` suelto -- evita depender de que la carpeta `Scripts` de tu
instalación de Python esté en el PATH (con `pip install --user`, como
en tu caso, a veces no lo está):

```powershell
python -m uvicorn presentation.api.main:app --reload --app-dir src
```

Para probar los endpoints **en PowerShell**, usá `Invoke-RestMethod` en
vez de `Invoke-WebRequest` -- parsea el JSON directo a un objeto de
PowerShell (más legible que un dump de la respuesta HTTP cruda), evita
el warning de "riesgo de ejecución de script" que tira `Invoke-WebRequest`
en PowerShell 5.1 (usa el motor de IE por default), y no tiene el bug de
mostrar acentos como `Ã¡`/`Ã³` que sí tiene `.Content` de
`Invoke-WebRequest` (esto último es puramente un problema de cómo
PowerShell 5.1 decodifica el string para mostrarlo -- el servidor manda
UTF-8 correcto, se puede confirmar mirando `Content-Length` vs. la
cantidad de caracteres):

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/sync/seed -Method POST
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/sync/status
```

Si preferís seguir con `Invoke-WebRequest` (por ejemplo para ver
status code y headers), agregale `-UseBasicParsing` para evitar el
warning:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/sync/seed -Method POST -UseBasicParsing
```

O, más simple todavía: abrí `http://127.0.0.1:8000/docs` en el navegador
(Swagger autogenerado por FastAPI) y probá los endpoints ahí con botones,
sin pelear con la consola.

### ⚠️ El auto-seed del arranque y el endpoint manual pueden pisarse

Si disparás `POST /api/sync/seed` justo después de arrancar el server
por primera vez, es muy probable que el auto-seed automático (dispara
solo porque nunca corrió antes) ya esté corriendo -- el endpoint ahora
detecta esto (`status: "already_running"` en vez de arrancar una
segunda corrida en paralelo). Antes de este fix no había guard, así que
si ya tenías el server corriendo con la versión anterior, lo más simple
es reiniciarlo (`Ctrl+C` y volver a correr `python -m uvicorn ...`) para
tomar el fix.

<details>
<summary>Si igual querés <code>pip install -e ".[api]"</code></summary>

El bug estaba en que `pyproject.toml` no le decía a hatchling qué
empaquetar (el proyecto no tiene un único directorio que coincida con
el nombre `quartermaster`). Ya está arreglado con
`[tool.hatch.build.targets.wheel] packages = [...]`. No lo pude probar
en este entorno (no tengo hatchling instalado acá tampoco) -- si te
sigue fallando con OTRO error, pegámelo.
</details>

## Novedad v0.3.3 — Bugs de UI reportados (borrado en tandas, pestaña colgada, botón colgado)

✅ **"Borra de a tandas" en vez de todo junto**: causa real -- `untrack()` en loop Python (una
   conexión SQLite por ítem) para watchlists grandes era lo bastante lento como para que un click
   de más (mientras el loop seguía corriendo) lo interrumpiera a la mitad -- Streamlit cancela el
   script en curso ante cualquier interacción nueva. Fix: `SQLiteTypeRepository.untrack_all()` /
   `.untrack_many()`, una sola sentencia SQL atómica, sin loop que se pueda cortar.
✅ **"Buscar y Agregar" no mostraba nada con muchos ítems trackeados**: causa real -- `st.tabs()`
   ejecuta el cuerpo de TODAS las pestañas en cada rerun (la visible es solo CSS del lado del
   cliente); con watchlists grandes, el cálculo pesado de "Tracked Items" bloqueaba a "Buscar y
   Agregar" aunque no se estuviera mirando esa pestaña. Fix: navegación con `st.radio` +
   `st.session_state`, con ejecución condicional real (`if`/`elif`, no `with`).
✅ **Botón "Trackear + Importar" parecía colgado**: causa real -- un solo `st.spinner()` genérico
   envolvía dos llamadas ESI secuenciales sin feedback intermedio. Fix: `st.status()` con pasos
   explícitos + guard en `session_state` contra doble-click (mismo patrón de causa que el bug de
   borrado en tandas).
✅ Nuevos tests de infraestructura (`tests/infrastructure/`, antes solo había tests de dominio)
   para `untrack_all` / `untrack_many` contra una DB temporal con schema real.
✅ Ver `docs/ROADMAP_Y_PENDIENTES.md` para el análisis integral pedido, con las mejoras discutidas
   y no implementadas todavía (sync completo de región en vez de muestreo, diversidad de
   recomendaciones) documentadas con el razonamiento completo para retomar sin perder contexto.

## Novedad v0.3.2 — Confiabilidad del precio + recomendación siempre visible + tema visual

✅ **`CAUTION_THIN_ORDER_BOOK`**: un ROI de miles de % puede ser matemáticamente correcto
   (verificado a mano: buy=1.00 ISK, sell=30.00 ISK → 2702% es exactamente lo que da la fórmula)
   y aun así no ser confiable, si ese precio está sostenido por una sola orden de compra y/o
   venta. Es una señal DISTINTA de `liquidity_score` (que mide profundidad total, no si el precio
   puntual es representativo). Ahora `OpportunityEngine` exige `MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST`
   (2) órdenes de cada lado para confiar en el precio, y si no se cumple, lo dice explícitamente
   en vez de mostrar un ROI extremo sin ninguna advertencia. El número de ROI NO se esconde ni se
   modifica -- se sigue mostrando tal cual, con el motivo de desconfianza al lado.
✅ **Toda Opportunity tiene ahora una recomendación explícita, incluyendo NEUTRAL** -- antes,
   NEUTRAL no pintaba ningún badge en la UI, dejando al usuario sin saber si un ítem sin badge fue
   evaluado (y resultó sin señal fuerte) o si algo se había salteado.
✅ `Opportunity` expone `sell_order_count` / `buy_order_count` (antes solo vivían dentro del
   cálculo interno) -- visibles en tarjetas y en la vista de tabla.
✅ **Upgrade visual**: tema oscuro "trading terminal" con acento ámbar (`.streamlit/config.toml`),
   evocando la propia paleta de EVE Online en vez de los defaults genéricos de Streamlit. Ícono de
   página cambiado de 🚀 a 📡. CSS adicional en `presentation/streamlit_app/theme.py` (tipografía
   tipo HUD para títulos, monoespaciada para métricas numéricas, tarjetas con borde ámbar sutil).

## Novedad v0.3.1 — Sesgo de muestreo en bulk import + vistas ordenables

✅ **Bug real encontrado**: el import masivo "Panorama General" traía `ORDER BY name LIMIT N`
   -- al ordenar alfabéticamente, la muestra quedaba sistemáticamente concentrada en variantes
   narrativas/de facción (ítems que empiezan con comilla, ej. `'Basic' X`), que casi nunca se
   comercian en Jita. Con 400 ítems así trackeados, el 100% mostraba liquidez 0 -- no porque el
   motor estuviera roto, sino porque la muestra estaba sesgada hacia lo menos líquido del juego.
   Cambiado a `ORDER BY RANDOM()`. Cap del slider subido de 400 a 2000 (tu SDE tiene ~27.000
   ítems publicados; 400 nunca fue "todos los items", era el tope arbitrario del slider).
✅ Estimación de tiempo del import masivo corregida (contaba solo la fase de órdenes, no la de
   historial de volumen que corre inmediatamente después -- estaba subestimada a la mitad).
✅ **Vista de tabla ordenable** (Dashboard y Tracked Items): toggle 🗂️ Tarjetas / 📊 Tabla —
   la tabla usa `st.dataframe`, que ya soporta ordenar por click en cualquier columna (Score,
   ROI %, Liquidez, etc.) sin código adicional. En Tracked Items arranca en modo Tabla
   automáticamente si tenés más de 50 ítems trackeados (renderizar cientos de checkboxes +
   badges + expanders individuales es pesado para el navegador).
✅ `scripts/diagnose_liquidity.py`: script nuevo para inspeccionar los números crudos de
   liquidez (`daily_volume`, `total_sell_volume_remain`, etc.) de tu watchlist real y distinguir
   "sesgo de muestra" de "bug real" sin tener que confiar en una explicación — mirá vos los datos.

## Novedad v0.3 (Sprint 1 — Julio 2026) — Fix de scoring saturado + transparencia

✅ **Bug real identificado y corregido**: ítems con ROI muy distinto (ej. 292% / 1558% / 3559%)
   terminaban con scores casi idénticos cuando tenían baja liquidez. La causa NO era una sola:
   1. `roi_component` y `spread_quality` saturaban a partir de ~139% / ~46% respectivamente
      (rango logarítmico demasiado angosto) — ver `OpportunityEngine` (formula_version `log_v2`).
   2. **La causa más grave**: `LiquidityEngine` podía dar hasta 40/100 de liquidez a un ítem con
      **cero** volumen diario real, solo por tener mucho `volume_remain` estancado en el book
      ("order book fantasma"). Corregido con media geométrica (MATH-002 v1.4).
   3. El badge "Compra recomendada" vivía hardcodeado en `app.py` (Streamlit), desincronizado del
      score real. Ahora es una regla de dominio (`OpportunityEngine._classify_recommendation` +
      `Opportunity.recommendation`), la única fuente de verdad para la UI.
✅ `score_breakdown` rediseñado: cada componente vive en escala 0-100 propia, los pesos declarados
   son literalmente los que se aplican, y la suma de contribuciones coincide con el score final
   (auditable, ver `sum_of_contributions`).
✅ `CompetitionEngine`: corregido bug de escala (`order_pressure` vivía en [0,1] pero se pesaba
   como si estuviera en [0,100] — MATH-003 v1.1) y wireado `total_buy_volume` real (antes hardcodeado en 0.0).
✅ **Addendum:** `price_spread_percent` eliminado de `CompetitionEngine` (MATH-003 v1.2) — su signo
   estaba invertido respecto a la propia definición del documento (spread ancho ≠ más competencia)
   y, corregido o no, era redundante con `roi_component`/`spread_quality`. Ver changelog en
   `CompetitionEngine` y `math/MATH-003_Competition.md`. Sin efecto observable en resultados previos
   (nunca estuvo conectado). `pytest` ahora corre sin configurar `PYTHONPATH` a mano (ver sección Tests).
✅ `get_daily_volume` ahora promedia una ventana de 7 días en vez de un solo día (menos ruido).
✅ Reintentos con backoff en `ESIClient` ante errores transitorios de ESI durante imports masivos.
✅ Eliminado código muerto (`esi_live_market_repository.py`, `scripts/jita_analyze.py` — ambos
   pertenecían a una generación de arquitectura anterior e incompatible con la actual).
✅ 22 tests unitarios (11 nuevos, cubriendo específicamente estos fixes) — dominio 100% puro, sin I/O.

## Novedad v0.2 (Julio 2026) — Importación Automática

✅ **Al trackear un producto desde la GUI Streamlit, el order book se importa automáticamente desde ESI (Jita).**
✅ **Al quitarlo de la watchlist, se borra su snapshot de órdenes activas (manteniendo la DB limpia).**
✅ Ya no hace falta correr scripts bash manualmente para cada item. Todo fluye desde la interfaz.

## Estado Actual

- ✅ MATH Suite v1.3 aprobada por Gemini
- ✅ Clean Architecture + DDD completa
- ✅ Value Objects inmutables + Domain Services (ROIEngine, Liquidity, Risk, Competition, ExitTime, OpportunityEngine)
- ✅ Repositorios SQLite reales + Puerto abstracto
- ✅ Importador ESI modular (por región o por type individual)
- ✅ **GUI Streamlit con importación automática al trackear + limpieza al deseleccionar**
- ✅ Use Case DetectOpportunitiesUseCase con exclusión estricta cuando falta evidencia real
- ✅ Modo Discovery mejorado cuando no hay watchlist

## Cómo usar (nuevo flujo recomendado)

1. `cd Quartermaster`
2. `streamlit run src/presentation/streamlit_app/app.py`
3. En la sidebar → "Tracked Items" (o navegación multi-página)
4. Buscá un item (ej: "Caldari Navy Scourge" o "Tritanium")
5. Click en **"➕ Trackear + Importar"** → ¡Automáticamente se agrega y descarga el order book actual!
6. Volvé al Dashboard principal → el análisis se actualiza solo.
7. Para quitar: botón 🗑️ Quitar → se elimina de tracked y se limpia su market_orders.

## Estructura

```
src/
├── domain/
│   ├── value_objects/     ← Money, TaxProfile, Opportunity, Risk, Liquidity, RecommendationLevel...
│   ├── services/          ← ROIEngine, LiquidityEngine, CompetitionEngine, OpportunityEngine...
│   └── ports/              ← MarketRepository, TypeRepository (interfaces)
├── infrastructure/
│   ├── esi/               ← ESIClient (con reintentos) + MarketOrdersImporter + MarketHistoryImporter
│   └── repositories/      ← SQLiteTypeRepository (con untrack + auto-clean), SQLiteMarketRepository
├── application/
│   └── use_cases/         ← DetectOpportunitiesUseCase
├── presentation/
│   └── streamlit_app/
│       ├── app.py              ← Dashboard
│       ├── pages/               ← Tracked Items (gestión + score inline por ítem)
│       └── components/          ← opportunity_table.py: renderizado compartido (badge + breakdown)
└── shared/
```

## Principios (sin cambios)

- Dominio puro (sin Pandas, sin SQL, sin HTTP en domain)
- Inmutabilidad total de Value Objects
- Determinismo + tests
- Explicabilidad (AnalysisResult con confidence + evidence; score_breakdown auditable)
- Separación estricta de concerns (Ports & Adapters) — las reglas de recomendación viven en
  `OpportunityEngine`, nunca en la capa de presentación

## Próximos pasos recomendados

1. Recalibrar los umbrales de recomendación (`OpportunityEngine.RECOMMEND_MIN_SCORE`, etc.) con
   uso real una vez que haya más historial de trading -- son constantes de clase, fáciles de tunear.
2. Agregar PortfolioOptimizer (MATH-007)
3. Mejorar UI con gráficos (Plotly) y alertas
4. Añadir Experience Layer / aprendizaje de predicciones pasadas (MATH-006 + RFC-007)

## Tests

```bash
pip install -e ".[dev]"
pytest
```

`pytest` ya sabe encontrar `src/` solo (configurado en `pyproject.toml` vía
`[tool.pytest.ini_options] pythonpath = ["src"]`) -- no hace falta setear
`PYTHONPATH` a mano. Para ver más detalle por test: `pytest -v`. Para correr
solo un archivo: `pytest tests/domain/services/test_opportunity_engine.py -v`.

## Requisitos

```bash
pip install -e .
# o
pip install streamlit requests
```

**Nota**: Necesita internet para llamadas ESI. La primera vez que trackeás un item puede tardar 1-3 segundos por item (rate limit respetado).

¡Disfrutá el trading informado en Jita! 🚀
