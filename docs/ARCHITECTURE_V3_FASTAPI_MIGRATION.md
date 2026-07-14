# Quartermaster → v3: Arquitectura cliente-servidor (diseño de alto nivel)

> Estado: PROPUESTA, no implementado. Este documento responde al pedido
> del usuario de diseño + recomendación de stack antes de tocar código,
> tal como pide el brief original. No confundir con
> `ROADMAP_Y_PENDIENTES.md` (ese es sobre fixes/mejoras del sistema
> actual en Streamlit; este es sobre el reemplazo de esa capa).

---

## 0. Encuadre: esto no es "cerrar un sprint"

El brief pide reemplazar el frontend, meter un backend HTTP separado,
background jobs, y un flujo de auto-seed -- son cuatro proyectos, no uno.
Ninguno de mis entregables anteriores en esta conversación se mandó sin
antes ejecutarlo y validarlo de verdad (tests + smoke tests contra la DB
real). Acá no puedo hacer eso: mi sandbox no tiene Docker, ni Redis, ni
salida de red para instalar NiceGUI/Reflex o correr un worker de Celery.
Cualquier código que escriba para esta capa nueva va a ser, por
definición, no verificado hasta que vos lo corras.

Por eso, en vez de generar un `docker-compose.yml` con cuatro servicios
y esperar que funcione a la primera, propongo tratarlo como **Fase 1
real y acotada** (más abajo), y usar esta sesión para dejar el diseño
sólido y decidido -- que es exactamente lo que pediste primero.

---

## 1. Lo que NO cambia (y por qué eso es la parte importante)

```
src/domain/          ← 0 cambios. Ya es Python puro, sin I/O, sin framework.
src/application/     ← 0 cambios. Los use cases ya reciben ports abstractos
                        (MarketRepository, TypeRepository), no saben si el
                        caller es Streamlit o un router de FastAPI.
src/infrastructure/
  esi/                ← 0 cambios. ESIClient, importers, ya son reusables.
  repositories/       ← 0 cambios. SQLiteTypeRepository/MarketRepository
                        no saben qué los llama.
```

Esto confirma que el Sprint 1 (Clean Architecture estricta) fue la
inversión correcta: la migración de frontend es, literalmente, escribir
una capa de presentación NUEVA al lado de la vieja, no reescribir nada
de lo que ya funciona y está testeado.

---

## 2. Estructura de carpetas propuesta

```
src/
├── domain/                          # sin cambios
├── application/                     # sin cambios
├── infrastructure/
│   ├── esi/                         # sin cambios
│   ├── repositories/                # sin cambios
│   └── jobs/                        # NUEVO
│       ├── scheduler.py                 # wiring de APScheduler (ver §4)
│       ├── seed_job.py                  # Smart Auto-Seed (bootstrap)
│       ├── sync_job.py                  # refresh periódico incremental
│       └── sync_status_repository.py    # progreso persistido (tabla sync_status)
└── presentation/
    ├── streamlit_app/                # se mantiene viva durante Fase 1 (ver §6)
    ├── api/                          # NUEVO -- FastAPI
    │   ├── main.py
    │   ├── dependencies.py               # inyección de repos/engines (mismo patrón que ya usás)
    │   ├── routers/
    │   │   ├── opportunities.py
    │   │   ├── tracked_items.py
    │   │   ├── search.py
    │   │   └── sync.py
    │   └── schemas/                      # Pydantic: traducen VOs de dominio a JSON
    └── ui/                            # NUEVO -- ver §3 para qué framework
        ├── main.py
        ├── pages/
        └── theme.py                      # el tema ámbar se porta tal cual
```

`schemas/` es la única traducción nueva de verdad: Pydantic models que
espejan `Opportunity`, `Liquidity`, `Risk`, etc. para servirlos por HTTP
sin filtrar tipos de dominio directo al wire. Es mecánico, no hay
decisiones de diseño ahí.

---

## 3. Frontend: NiceGUI, no Reflex, no React

Comparación real, no una tabla de marketing:

| | **NiceGUI** | **Reflex** | **React + FastAPI** |
|---|---|---|---|
| Corre sobre | FastAPI (literal, mismo proceso si querés) | Su propio backend (compila a React + servidor propio) | Lo que vos armes |
| Tablas grandes | `ui.aggrid()` -- wrapper de AG-Grid, virtualización probada para miles de filas | Sin wrapper maduro de grid; para tablas grandes hay que armar algo o envolver un componente React vos mismo | Mejor techo posible, pero hay que construirlo |
| Curva de migración desde Streamlit | Baja -- el modelo mental es parecido (llamás funciones, arma UI) | Media -- modelo declarativo tipo React, aunque en Python | Alta -- dos lenguajes, dos toolchains |
| 100% Python | Sí | Sí (compila a JS por debajo, pero vos no escribís JS) | No |
| Madurez | Media, pero estable en lo core | Creciendo rápido, más "flashy", más rough edges reportados | Máxima |
| Deploy | Se puede fusionar con la API en el MISMO proceso FastAPI | Servicio aparte (build de React + servidor Python) | Servicio aparte |

**Recomiendo NiceGUI.** Tres razones concretas, no gusto:

1. **Ya tuvimos el problema de tablas grandes con Streamlit** (el bug de
   `st.tabs()` ejecutando todo, la necesidad de vista tabla ordenable
   para 500 ítems). `ui.aggrid()` resuelve esto de fábrica con
   virtualización real del lado del cliente -- no es un "nice to have",
   es la respuesta directa a un dolor que ya tuvimos.
2. **Corre sobre FastAPI de verdad**, no "al lado de". Podés montar la
   UI y la API en el mismo proceso (`app.mount()`) si querés simplicidad
   de deploy, o separarlos en dos servicios si preferís aislar cargas --
   la decisión queda abierta, no forzada por el framework.
3. **Menor riesgo de migración**: el estilo de código (`ui.label(...)`,
   `ui.button(...).on_click(...)`) se parece más a lo que ya tenés en
   Streamlit que el modelo de componentes/estado de Reflex. Menos
   reescritura conceptual, más traducción directa.

Cuándo NO elegiría NiceGUI: si en algún momento el objetivo pasa a ser
un producto multi-usuario con una identidad visual muy custom/pulida
tipo SaaS comercial -- ahí React gana por techo de calidad y ecosistema
de componentes. Para una herramienta personal/de nicho con foco en
datos y velocidad, es overkill.

---

## 4. Background jobs: NO a Celery + Redis

El brief lo sugiere pero invita a evaluar alternativas -- lo hago.
Celery+Redis está pensado para procesamiento distribuido, multi-worker,
alto throughput. Este proyecto es una herramienta de un usuario (vos)
corriendo local. Meter Redis como dependencia dura para esto es
complejidad operativa sin beneficio real: un proceso más para levantar,
un punto de falla más, sin ninguna ganancia porque nunca vas a necesitar
escalar workers horizontalmente para sincronizar el mercado de Jita.

**Propuesta**: `APScheduler` para los jobs periódicos (corre en el mismo
proceso que FastAPI, sin dependencias externas) + `BackgroundTasks` de
FastAPI para acciones on-demand disparadas por el usuario (ej. "refrescá
este ítem ahora"). Si en algún momento necesitás persistencia de jobs
entre reinicios o reintentos más robustos que lo que da APScheduler,
la escala intermedia es **Huey con backend SQLite** (mismo archivo de
datos que ya usás, cero infra nueva) -- lo dejo anotado como opción B,
no lo recomiendo de entrada porque APScheduler alcanza para el volumen
de jobs que este sistema realmente tiene (un puñado de sync periódicos,
no miles de tareas concurrentes).

Esto también simplifica el Docker Compose: **2 servicios, no 4**
(API+scheduler en un contenedor, UI en otro si los separás -- o 1 solo
si montás todo en el mismo proceso FastAPI). Sin Redis.

---

## 5. Smart Auto-Seed = lo que ya diseñamos, con otro disparador

Esto NO es una pieza nueva a diseñar de cero. Es exactamente el "sync
completo de región" que ya está en `ROADMAP_Y_PENDIENTES.md` §4 (fetch
de `/markets/{region_id}/orders/` SIN filtro de `type_id`, un barrido
paginado completo en vez de miles de requests por ítem), ahora disparado
automáticamente en vez de por un botón manual.

Lo único nuevo es el *trigger* y el *estado*:
- Tabla `system_state` (o similar): `last_full_seed_at`. Si es NULL al
  arrancar, se dispara el seed automáticamente.
- Tabla `sync_status`: fase actual ("importando order book" /
  "importando historial X/N"), timestamp, para que la UI pueda mostrar
  progreso real vía polling a `GET /api/sync/status` (o websocket si
  querés que sea push en vez de poll -- NiceGUI lo soporta nativo).

---

## 6. Plan de fases (realista, no el mío original sino ajustado)

**Fase 1 (esto SÍ podría ser "sprint 2 de esta migración", acotado):**
Extraer use cases detrás de endpoints FastAPI, dejando Streamlit vivo
pero como CLIENTE de esa API en vez de llamar a los use cases directo.
Cero UI nueva todavía. Esto de por sí ya resuelve varios dolores
(Streamlit deja de bloquear en imports de ESI porque esos pasan a un
job en background; el dashboard lee datos ya calculados). Es
verificable con los mismos tests que ya tenemos + tests de API nuevos.

**Fase 2:** Construir la UI en NiceGUI consumiendo la misma API,
en paralelo a Streamlit (no reemplazo big-bang). Migrar pantalla por
pantalla, comparando contra la versión Streamlit antes de apagarla.

**Fase 3:** Smart Auto-Seed automático + apagar Streamlit definitivamente.

Esto es más lento que "todo junto" pero es la única forma de que cada
paso sea verificable por vos corriéndolo, en vez de que yo te entregue
un stack de 4 piezas nuevas sin haber podido probar ninguna acá.

---

## 7. Riesgos ya identificados (honestos, no genéricos)

- **Rate limits de ESI**: ya los tenemos mapeados (retry+backoff en
  `ESIClient`, y el plan de full-region-sync reduce drásticamente la
  cantidad de requests vs. el modelo actual de "uno por ítem"). No es
  un riesgo nuevo que introduce esta migración, es uno que ya veníamos
  resolviendo.
- **SQLite bajo concurrencia**: con un scheduler + una API sirviendo
  requests al mismo tiempo, hay más de una conexión escribiendo. SQLite
  con WAL mode (`PRAGMA journal_mode=WAL`) maneja esto bien para el
  volumen de este proyecto; si migran a Postgres en el futuro esto deja
  de ser un tema. Lo marco para activar WAL mode como parte de Fase 1,
  no esperar a que sea un problema.
- **Frescura vs. performance**: con el full-region-sync corriendo cada
  N minutos vía APScheduler, el dashboard siempre lee datos de hace
  como máximo N minutos, nunca hace I/O de red en el request path. Este
  es el mecanismo que responde al "quiero que cargue rápido" del brief
  -- no hace falta una capa de cache adicional el día 1.
