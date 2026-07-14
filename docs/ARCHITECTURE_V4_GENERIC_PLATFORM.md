# Quartermaster — Evaluación Arquitectónica: de app de EVE a Plataforma de Decision Intelligence

> Documento de análisis, no de implementación. Producido por revisión directa del código real
> (no de memoria) el 12/07/2026, inmediatamente después de confirmar el fix de filtrado por
> estación de Jita. Complementa (no reemplaza) `ARCHITECTURE_V3_FASTAPI_MIGRATION.md` y
> `ROADMAP_Y_PENDIENTES.md`.

---

## 0. Veredicto ejecutivo

El acoplamiento a EVE es **más angosto y más concentrado de lo que probablemente parece desde
afuera**. No está repartido parejo por todo el sistema — está concentrado en tres lugares
puntuales:

1. **Vocabulario** (`type_id`, `region_id`, `ISK`, `TaxProfile`) filtrado hacia arriba desde el
   dominio hasta el contrato público de la API.
2. **El esquema de persistencia** (`market_orders`, `market_history`) que es, literalmente, la
   forma del JSON de ESI — no un modelo de datos de mercado independiente.
3. **La ausencia de un Provider port** — hoy `SQLiteMarketRepository` mezcla "cómo se guardan
   datos de mercado" con "de dónde vienen esos datos", sin una interfaz intermedia.

La matemática en sí (los cinco motores: ROI, Liquidez, Riesgo, Competencia, Exit Time) **ya es
genérica**. No contienen ninguna asunción de EVE en su lógica interna — operan sobre números
puros (precios, volúmenes, conteos de órdenes). Esto es la parte más cara de rehacer en cualquier
plataforma de este tipo, y ya está bien construida. El trabajo real no es "reescribir el cerebro",
es "sacarle las etiquetas de EVE a la ropa y ponerle una capa de traducción en la entrada".

Esto cambia la naturaleza del roadmap: no es un rewrite de cero, es una **capa de abstracción
insertada alrededor de un núcleo que ya casi la respeta.**

---

## 1. Qué se mantiene sin cambios

| Componente | Por qué se mantiene |
|---|---|
| **Los cinco motores de dominio** (`ROIEngine`, `LiquidityEngine`, `RiskEngine`, `CompetitionEngine`, `ExitTimeEngine`) | Ya operan sobre `float`/`Money` puros. Cero referencias a EVE en su lógica de cálculo (verificado por grep, no solo por inspección). El patrón Input/Output value objects + `.calculate()` ya es el patrón "plugin" que pide la visión de producto. |
| **`AnalysisResult[T]` (Generic)** | Ya es un wrapper genérico con parámetro de tipo. Exactamente la abstracción que se necesita para que cualquier motor futuro (Volatility, Market Maker, Arbitrage) devuelva resultados con la misma forma (confidence, validation_status, evidence_count) sin acoplarse al tipo concreto. |
| **Clean Architecture / capas** | La separación domain → application → infrastructure → presentation ya existe y ya se respeta (los engines no importan infraestructura, los repos implementan ports abstractos). No hay que reordenar carpetas de raíz. |
| **El patrón "presentación = cliente HTTP de la API"** | Streamlit, NiceGUI, y cualquier UI futura (móvil, otro dashboard) ya consumen la misma API sin conocer el dominio. Esto es exactamente cómo debería verse una plataforma con múltiples frontends. |
| **RFC-driven / mathematical modules separados de business logic** | Ya es así. `OpportunityEngine` es un motor de *composición* de los otros cinco -- no mezcla su propia matemática con la de ellos. |
| **`Money` como Value Object con minor units** | El patrón (evitar floats para dinero, minor units enteras) es correcto para CUALQUIER mercado, no solo EVE. Solo el default `currency="ISK"` necesita irse (ver §4). |

**Esto importa**: la parte más difícil y más cara de una plataforma de Decision Intelligence
—la calidad y explicabilidad del scoring— ya está resuelta de forma provider-agnostic. El riesgo
de este proyecto NO es "¿la matemática escala a otros mercados?" (sí, ya escala). El riesgo es
"¿el vocabulario y la capa de datos dejan que esa matemática reciba información de otros mercados
sin reescribirla?" — hoy, no.

---

## 2. Qué se debe generalizar (mismo comportamiento, distinto nombre/forma)

| Hoy | Debería ser | Nota |
|---|---|---|
| `Opportunity.type_id` / `type_name` / `region_id` | `Opportunity.instrument_id` / `instrument_name` / `market_id` | El campo existe y funciona -- solo el nombre asume EVE. Un rename de dominio, no una reescritura de lógica. |
| `TaxProfile(broker_fee_rate, sales_tax_rate)` | `FeeProfile(entry_fee_rate, exit_fee_rate)` o `CostProfile` | La ESTRUCTURA (dos tasas que se suman al costo total de una operación) es universal a cualquier mercado con fees. Solo los nombres son EVE ("broker fee" es jerga específica del juego). |
| `Money(currency="ISK")` | `Money(currency: str)` sin default, o default `"USD"` / sin default en absoluto | Un default silencioso a ISK es el tipo de acoplamiento más peligroso: no rompe nada al usarlo con otro mercado, simplemente miente en los datos. |
| `MarketRepository.get_current_snapshot(type_id, region_id)` | `MarketDataPort.get_current_snapshot(instrument_id, market_id)` | El PORT (interfaz abstracta) ya existe y ya está bien ubicado en `domain/ports/`. Es una cuestión de nombres de parámetros, no de mover archivos. |
| `TypeRepository` | `InstrumentCatalogPort` o `AssetCatalogPort` | "Type" es literalmente el nombre que usa EVE (`type_id` del SDE) para "ítem". En cualquier otro mercado esto se llama instrumento, activo, o ticker. |
| Tabla `market_orders` (columnas `type_id`, `region_id`, `location_id`) | Tabla genérica `market_listings` o `order_book_entries` con `instrument_id`, `market_id`, `venue_id` | Estructuralmente es "una entrada de order book" -- eso es universal. Los NOMBRES de columna son ESI calcado. Ver §5 sobre el problema más profundo de jerarquía de ubicación. |
| Endpoints `/api/opportunities`, `/api/tracked-items` | Se mantienen conceptualmente, pero el path debería llevar el mercado como parámetro: `/api/markets/{market_id}/opportunities` | Hoy la API asume implícitamente "siempre Jita" -- no hay forma de pedirle oportunidades de otro mercado sin cambiar código. |

---

## 3. Qué se debe reescribir (no solo renombrar)

### 3.1 La capa de ingesta de datos (`infrastructure/esi/*`)
No se reescribe el CONTENIDO (la lógica de paginación, reintentos, Smart Auto-Seed es sólida y
reusable como *patrón*), pero su ROL cambia: hoy es "la" fuente de datos. Debe pasar a ser **una
implementación concreta de un `MarketDataProvider` port que todavía no existe** (ver §4). El
código de `ESIClient`/`MarketOrdersImporter` se mueve conceptualmente de "infraestructura core"
a "provider plugin -- el primero de varios".

### 3.2 El esquema de persistencia
Esto es lo más caro de tocar porque hay datos reales de producción (19.111 ítems sincronizados)
en el esquema actual. Dos caminos, no mutuamente excluyentes:
- **Camino conservador**: agregar una vista/capa de traducción entre el esquema físico (que puede
  seguir pareciéndose a ESI por ahora) y lo que el dominio consume -- mismo principio que un
  Anti-Corruption Layer de DDD.
- **Camino correcto a largo plazo**: nueva tabla genérica `market_listings` con
  `provider: str` (ej: `"eve_esi"`, `"steam"`, `"binance"`), `instrument_id`, `market_id`,
  `venue_id`, y una migración de los datos existentes. Más trabajo ahora, pero evita acumular una
  segunda capa de traducción permanente.

### 3.3 La jerarquía de ubicación (region → estación)
Ver §5 -- este es el punto de fricción más sutil y más específico de EVE de todo el sistema.

### 3.4 El nombre `JITA_STATION_ID` / `JITA_REGION_ID` como constantes de clase
Hoy viven hardcodeadas en `SQLiteMarketRepository`. Deben migrar a configuración por
`MarketDefinition` (ver §4) -- cada mercado soportado define sus propios IDs de venue por defecto,
el repositorio no debería conocer "Jita" por nombre en absoluto.

---

## 4. Abstracciones faltantes

Estas son conceptos que **no existen todavía** en el código y que la visión de plataforma
necesita:

### `MarketDataProvider` (Port)
```
domain/ports/market_data_provider.py
```
El faltante más importante. Hoy `MarketRepository` mezcla dos responsabilidades: "persistir y
consultar datos de mercado" (infraestructura genérica, correcta) y, implícitamente, "los datos
vienen de ESI" (acoplamiento oculto, porque nada más los provee). Un `MarketDataProvider`
explícito sería el punto de extensión real:

```
MarketDataProvider (ABC)
├── EVEProvider    (usa ESIClient -- lo que hoy es infrastructure/esi/*)
├── SteamProvider  (futuro)
└── BinanceProvider (futuro)
```

`MarketRepository` deja de ser "el repositorio", pasa a ser "la capa de persistencia genérica que
CUALQUIER provider usa para guardar lo que trajo".

### `Market` / `Venue` (Value Objects de dominio)
Hoy "dónde" es un `region_id: int` suelto, sin ningún objeto que lo represente. Un mercado real
de Decision Intelligence necesita un concepto explícito de **dónde ocurre una operación**, porque
eso varía radicalmente entre providers:
- EVE: región + estación (jerarquía de 2 niveles, con la limitación real de que el historial de
  volumen es solo por región -- ver §5).
- Steam: no hay "ubicación", es un mercado único global.
- Binance: pares de trading (`BTC/USDT`), no ubicaciones físicas.

Proponer un `Venue` con un `venue_id: str` opaco (no un `int` que asuma el esquema de IDs de
EVE) y metadata específica del provider en un campo `extra: dict`, para no forzar una jerarquía
universal que no existe en la realidad.

### `Instrument` (reemplaza el uso disperso de `type_id`/`type_name`)
Un Value Object simple (`instrument_id: str`, `display_name: str`, `provider: str`) en vez de
pasar `type_id: int` y `type_name: str` sueltos por todos lados como hoy. Esto también resuelve
un problema real: `type_id` es un `int` porque ESI usa enteros, pero Steam/crypto suelen usar
strings o IDs compuestos -- forzar `int` en el dominio es una asunción de EVE escondida en el
tipo de dato, no solo en el nombre.

### `Portfolio` / `Watchlist` / `User` (para la visión SaaS)
No existen hoy en absoluto -- todo el estado de "qué estoy siguiendo" vive en una tabla
`tracked_types` sin owner. Para multi-usuario esto necesita, como mínimo, un `owner_id` en cada
entidad de estado, y probablemente un dominio `Portfolio` separado del dominio de análisis de
mercado (son bounded contexts distintos: "qué es una buena oportunidad" no debería saber nada de
"quién la está mirando").

### `Strategy` (para la mentalidad de plugin de engines)
Hoy `OpportunityEngine` combina los 5 motores con pesos fijos hardcodeados
(`WEIGHT_RISK=0.32`, etc.). Para que "motores" sea realmente plug-in, hace falta una abstracción
de **estrategia de composición** -- qué motores correr y con qué pesos -- separada del motor de
composición en sí. Hoy la única "estrategia" es la que vive hardcodeada en
`OpportunityEngine.detect()`.

---

## 5. El problema más sutil, específico de este dominio

**La jerarquía "región contiene estación" de EVE no tiene equivalente universal.**

El fix reciente (filtrar por `location_id` de Jita, no solo `region_id`) resolvió un bug real,
pero también expuso que el modelo de datos asume una jerarquía de 2 niveles (región → estación)
que es idiosincrática de EVE. Otros mercados no tienen esta forma:
- Steam Community Market: no hay "ubicación", el mercado es global y único.
- Binance: hay "pares de trading" y posiblemente "exchanges", pero no una jerarquía
  región/estación.
- Un mercado de commodities real: podría tener "bolsa" → "contrato", una jerarquía distinta de
  nuevo.

Otra asunción específica de ESI que quedó documentada pero no resuelta en el fix reciente: el
historial de volumen (`daily_volume`) es inevitablemente regional en EVE porque ESI no expone
historial por estación. Esto es una limitación de ESE provider, no algo que la
`LiquidityEngine` genérica debería saber. Hoy esa limitación se filtra hacia arriba como un
comentario en el repositorio -- en la plataforma generalizada, el `EVEProvider` debería
absorber esa limitación y devolver lo mejor que pueda, sin que el dominio genérico necesite saber
por qué el volumen es "un poco menos preciso" para este provider en particular.

**Recomendación concreta**: no intentar modelar una jerarquía universal de ubicación. En cambio,
`Venue` debería ser un `venue_id: str` opaco con metadata libre por provider (`extra: dict`), y
cada `MarketDataProvider` decide internamente cómo mapea su propia jerarquía (o ausencia de ella)
a ese único string. Esto evita el error clásico de diseñar una abstracción "genérica" que en
realidad solo generaliza el caso que ya conocés (EVE).

---

## 6. Mejoras de nombres (resumen de tabla, para referencia rápida)

| Dominio EVE | Dominio genérico propuesto |
|---|---|
| `type_id` | `instrument_id` |
| `type_name` | `instrument_name` / `display_name` |
| `region_id` | `market_id` |
| `location_id` | `venue_id` |
| `ISK` (default de `Money`) | sin default, o `currency` requerido siempre |
| `TaxProfile` | `FeeProfile` |
| `broker_fee_rate` | `entry_fee_rate` (o `listing_fee_rate`) |
| `sales_tax_rate` | `exit_fee_rate` (o `transaction_tax_rate`) |
| `TypeRepository` | `InstrumentCatalogPort` |
| `MarketRepository` | se mantiene el nombre, pero se separa la responsabilidad de provider (ver §4) |
| `tracked_types` (tabla) | `watchlist_items` (con `owner_id`, pensando en SaaS) |
| "JitaTrader" en logs/UA-strings de ESI | ya resuelto (rename a Quartermaster) |

---

## 7. Roadmap propuesto (por etapas, no big-bang)

El sistema tiene datos reales de producción y un usuario que depende de él funcionando -- un
rewrite de una sola vez es el error más común y más caro en este tipo de transición. Etapas
pensadas para que el sistema siga funcionando (para EVE) en cada paso intermedio:

**Etapa 1 — Vocabulario del dominio (bajo riesgo, alto valor de claridad)**
Renombrar campos de Value Objects y Ports según §2/§6, SIN tocar el esquema de base de datos ni
los providers. Es un rename mecánico grande pero mecánico -- el comportamiento no cambia, solo
los nombres que ve el código (y, en cascada, la API pública). Habilita razonar sobre el dominio
sin traducir mentalmente EVE→genérico todo el tiempo.

**Etapa 2 — Introducir `MarketDataProvider` como abstracción explícita**
Extraer un port nuevo, hacer que `EVEProvider` (renombrando lo que hoy es
`infrastructure/esi/*`) lo implemente. El comportamiento hacia afuera no cambia -- es una
refactorización interna que prepara el terreno para un segundo provider real.

**Etapa 3 — Anti-Corruption Layer sobre el esquema actual**
Antes de migrar el esquema físico (riesgoso, hay datos reales), agregar una capa de traducción
entre `market_orders`/`market_history` (que puede seguir teniendo forma de ESI un tiempo más) y
los Value Objects genéricos del dominio. Esto separa "cuándo migro el esquema físico" de "cuándo
el dominio deja de conocer EVE" -- pueden pasar en momentos distintos.

**Etapa 4 — Segundo provider real (prueba de la abstracción)**
No agregar un segundo provider es la forma más común de descubrir, tarde, que la abstracción de
la Etapa 2 en realidad solo generalizaba el caso de EVE. Steam Community Market es un candidato
razonable: API pública, sin auth compleja, y un modelo de datos deliberadamente MÁS simple que
EVE (sin jerarquía de ubicación) -- es un buen caso de prueba precisamente porque es distinto,
no porque sea fácil.

**Etapa 5 — Migración de esquema físico + multi-tenancy**
Recién acá migrar `market_orders` al esquema genérico con `provider` como columna, y agregar
`owner_id`/autenticación para la visión SaaS. Se deja para el final a propósito: es lo más caro
de deshacer si alguna decisión de las etapas anteriores resulta equivocada una vez que hay un
segundo provider real probándola.

---

## 8. Lo que este documento NO recomienda

- **No** reescribir los 5 motores de dominio -- ya son genéricos, tocarlos ahora es riesgo sin
  beneficio.
- **No** intentar diseñar la jerarquía universal de "ubicación de mercado" antes de tener un
  segundo provider real -- ver §5, es la trampa más probable de esta transición.
- **No** migrar el esquema físico de la base de datos como primer paso -- hay datos reales de
  producción, y hacerlo antes de validar la abstracción con un segundo provider es el orden
  equivocado.
- **No** agregar autenticación/multi-tenancy todavía -- es la etapa 5 a propósito, no la 1.
