# Quartermaster — Roadmap y pendientes (post Sprint 1)

## ✅ Corrección honesta: el primer pase visual de NiceGUI no alcanzaba

El usuario probó el rediseño anterior y fue directo: "sigue pareciendo
muy feo comparado con Streamlit". Con capturas reales, señaló 3
problemas concretos -- no una impresión vaga, cosas puntuales:

### 1. Bug real: Discovery se quedaba en blanco

Streamlit tiene un fallback (si NADA cruza el score mínimo pero hay
evidencia real para al menos un ítem, muestra los mejores disponibles
igual, con advertencia) -- este fallback nunca se había portado a
NiceGUI. El Dashboard de NiceGUI simplemente mostraba la advertencia y
nada más debajo. Portado exacto (mismo texto, misma lógica de
`min_score=0` + top 15). **Probado explícitamente**: forzado un
`min_score` que excluye todo, confirmado que dispara una segunda
llamada con `min_score=0` y trae resultados -- antes esto nunca se
verificó con un test real, solo se asumió que "ya estaba".

### 2. Nav y sidebar sin ningún tratamiento visual real

`render_nav_header` nunca había recibido estilo -- era texto plano con
un separador abajo. Rediseñado como barra real (`.jt-nav-bar`) con
pestañas marcadas (línea inferior de color en la activa).

El sidebar (`.jt-panel`) se veía sin fondo/borde a pesar de tener la
clase aplicada -- causa real: `ui.left_drawer()` es un `q-drawer` de
Quasar con su propio fondo, que pisa cualquier clase puesta en el
drawer mismo. Solución: el panel real va en un `ui.column()` DENTRO
del drawer, no en el drawer directamente -- más una regla CSS
apuntando a `.q-drawer` para el fondo general.

### 3. Layout: "el detalle me encanta, debería estar arriba"

Antes: tabla AG-Grid primero, tarjetas después -- exactamente al
revés de lo que el usuario valoraba. Ahora son pestañas
(`ui.tabs`/`ui.tab_panels`), Tarjetas como default, Tabla como
segunda opción -- mismo patrón que ya funcionaba bien en Streamlit
(ahí es un radio button), no una idea nueva sin probar.

166 tests, todos pasando (mismo número que antes -- este pase fue
presentación + un fix de lógica de fallback ya cubierto
indirectamente por los tests de `ApiServices.list_opportunities`
existentes).

### Nota honesta

El primer pase visual (`Quartermaster_COMPLETO.zip` de la sesión
anterior) declaró "listo" sin haber sido validado contra capturas
reales -- pasó los tests automatizados (que no verifican apariencia)
pero no correspondía a cómo se ve de verdad. La lección para
próximos pases de UI: pedir captura de pantalla real antes de
declarar un rediseño visual terminado, los smoke tests solo prueban
"no explota", nunca "se ve bien".

---

## ✅ Visión de empresa formalizada + Etapa 2 de la generalización

### `docs/VISION.md` (nuevo)

El fundador redefinió Quartermaster: de "app para EVE" a "empresa +
motor de inteligencia para toma de decisiones", con EVE como primer
caso de uso, no el producto final. Documento agregado tal cual fue
escrito, más una nota de disciplina de ingeniería (agregada acá, no
parte del manifiesto original) que conecta la visión con la trampa ya
documentada en `ARCHITECTURE_V4_GENERIC_PLATFORM.md` §5/§8: diseñar la
abstracción universal de "mercado" antes de tener un segundo proveedor
real generaliza mal el único caso conocido. La visión define el
NORTE; el roadmap por etapas de ese mismo documento sigue siendo la
SECUENCIA de bajo riesgo para llegar ahí sin romper lo que ya funciona
para EVE.

### Etapa 2: `MarketDataProvider` como abstracción explícita

Primer paso técnico ejecutado con la misma disciplina de siempre --
comportamiento hacia afuera SIN CAMBIOS, confirmado con tests, no
solo declarado:

- **`domain/ports/market_data_provider.py`** (nuevo): port ABC con dos
  métodos (`sync_full_market_orders`, `sync_instrument_history`) --
  diseñados a partir de lo que `MarketOrdersImporter`/
  `MarketHistoryImporter` YA hacían en producción, no una interfaz
  "ideal" inventada de antemano (la misma disciplina que evitó la
  trampa de §5).
- **`infrastructure/providers/eve_provider.py`** (nuevo): `EVEProvider`
  implementa el port ENVOLVIENDO los importadores existentes por
  composición, no reescribiéndolos -- cero riesgo para el Smart
  Auto-Seed que ya corre en producción.
- **Probado**: delegación 1:1 verificada explícitamente (mismos
  argumentos, mismo resultado, no solo "no tira error") + confirmación
  de que el ABC rechaza instanciación directa (protege contra
  implementaciones futuras incompletas).
- **Deliberadamente NO hecho todavía**: `SmartAutoSeedJob` sigue
  llamando a los importadores directo, no a través de `EVEProvider` --
  migrar el orquestador es un paso aparte, para no mezclar "introducir
  la abstracción" con "migrar quién la usa" en el mismo cambio.

166 tests, todos pasando (5 nuevos, cero regresiones -- exactamente lo
que Etapa 2 prometía).

### Sigue pendiente

- Migrar `SmartAutoSeedJob` para consumir `EVEProvider` en vez de los
  importadores directo (natural próximo paso de Etapa 2, pospuesto a
  propósito).
- Etapa 3 (`Anti-Corruption Layer` sobre el esquema físico), Etapa 4
  (segundo proveedor real -- prueba de que la abstracción generaliza
  de verdad), Etapa 5 (migración de esquema + multi-tenancy ya
  parcialmente hecha).
- Wiring de multi-hub en la API/UI, alertas, historial de precios,
  comparación entre hubs, exportar CSV -- sin tocar, siguen en cola.

---

## ✅ Rediseño visual del Dashboard de NiceGUI (mismo pase que Tracked Items)

Continuación directa del rediseño anterior -- mismo sistema de diseño
aplicado a la página que faltaba:

- **Sidebar como panel sólido** (`.jt-panel`, mismo lenguaje que
  `.jt-row-card`) en vez de quedar flotando sobre el fondo sin
  contenedor propio.
- **Banners de estado** (`.jt-status-banner`, con variante `.warning`)
  reemplazan el texto plano suelto para "Modo Discovery", "sync en
  curso", "0 resultados con estos filtros" -- mismo lenguaje visual que
  el banner de recomendación de las tarjetas, coherencia en toda la
  página.
- **AG-Grid con tema oscuro nativo** (`ag-theme-alpine-dark`, con
  variables CSS mapeadas a la paleta del proyecto) -- antes usaba el
  tema claro default de AG-Grid, que desentonaba fuerte contra el
  fondo `#090D16` del resto.
- **Watchlist del sidebar con íconos** de ítem, mismo criterio que las
  tarjetas de Tracked Items.
- Sliders con color ámbar explícito (`props("color=amber")`) en vez
  del primary default de Quasar.

Probado con datos reales en los 3 casos: sin sesión (Discovery
anónimo), con sesión y watchlist, y con banner de advertencia (0
resultados con los filtros actuales).

161 tests, todos pasando -- este rediseño no tocó lógica de negocio,
solo presentación, así que no había tests nuevos que agregar (los
existentes ya cubren `opportunity_to_grid_row` y el resto de la lógica
que este archivo consume).

### Sigue pendiente

- Wiring de multi-hub en la API/UI.
- Alertas, historial de precios, comparación entre hubs, exportar CSV.
- Revisar si haría falta un pase de responsividad/mobile -- no
  evaluado todavía en ninguna de las dos páginas rediseñadas.

---

## 🎯 Decisión de enfoque: NiceGUI a partir de ahora

El usuario definió explícitamente: de acá en adelante, el desarrollo
se enfoca completamente en NiceGUI -- Streamlit queda como está,
funcionando, pero deja de recibir features nuevas ni rediseños. Motivo
directo: "de las 2 [UIs], la de NiceGUI me parece la más fea por
lejos" + la idea propuesta antes de converger a una sola UI para
reducir superficie de mantenimiento. **Esto no significa que
Streamlit se borre** -- sigue siendo la versión estable de referencia
mientras NiceGUI se pone al día visualmente.

## ✅ Rediseño visual completo de NiceGUI (Tracked Items)

Brief detallado del usuario: estética "Sci-Fi / Tactical Dark Mode",
con foco explícito en el punto débil real de NiceGUI -- inputs y
selectores planos, de bajo contraste, "cero accesibles" comparados con
Streamlit.

**Inputs/selects rediseñados** (`theme.styled_search_input`,
`theme.styled_select`): los componentes de NiceGUI son Quasar por
dentro -- clases Tailwind en `.classes()` no penetran los pseudo-
elementos que Quasar usa para el borde "outlined", hizo falta CSS
dirigido a las clases internas de Quasar (`.q-field__control`,
`.q-field--outlined...:before`, etc.) además de los props de Quasar
(`outlined dark color=amber`) pedidos explícitamente. Contenedor sólido
(slate-900/90), borde slate-800, foco ámbar-500/50, texto slate-100,
placeholder slate-400, ícono de lupa en la búsqueda -- todo tal como se
pidió.

**Tarjetas horizontales compactas** (`.jt-row-card`): reemplazan las
tarjetas grandes de antes en la lista de trackeados y resultados de
búsqueda -- bordes finos translúcidos, hover elegante, menos alto por
ítem.

**Botones compactos** (`.jt-btn-compact`): bordes definidos, sin
colores sólidos chillones, hover sutil.

**Explorador de Categoría → Grupo portado desde Streamlit**: existía
como método de repositorio hace tiempo, pero NUNCA se había expuesto
vía HTTP -- Streamlit accedía directo a la base, NiceGUI necesita todo
vía API. Se agregaron 3 endpoints nuevos (`GET /api/catalog/categories`,
`GET /api/catalog/categories/{id}/groups`,
`GET /api/catalog/groups/{id}/types`) + métodos correspondientes en
`ApiClient` + 5 tests nuevos, todos probados contra datos reales
(navegación completa categoría → grupo → ítems funcionando de punta a
punta).

**Íconos de ítems** también agregados en esta pasada a las tarjetas de
búsqueda y del explorador (ya estaban en Discovery de una sesión
anterior).

161 tests, todos pasando.

### Sigue pendiente

- El Dashboard de NiceGUI (`pages/dashboard.py`) todavía no recibió
  este mismo pase visual -- solo Tracked Items por ahora.
- Wiring de multi-hub en la API/UI.
- Alertas, historial de precios, comparación entre hubs, exportar CSV.

---

## ✅ Login funcionando de punta a punta + íconos + insight protagonista

**Login confirmado funcionando con credenciales reales** -- primer
login exitoso del usuario ("Dimitri Dakan"), después de tres bugs
reales encontrados y arreglados en cadena (PyJWKClient, InvalidIssuer,
copy-paste del Fernet key).

**`scripts/setup_env.py` extendido**: además de generar las 4 claves
auto-generables, ahora también PIDE interactivamente
`EVE_SSO_CLIENT_ID`/`SECRET` si están vacíos (con las instrucciones de
developers.eveonline.com inline) y los escribe directo en `.env` --
sigue siendo el único paso que no se puede generar solo (requiere
registrar la app en el sitio de CCP), pero ya no requiere abrir un
editor de texto para pegarlo. Salteable con Enter vacío, no bloquea el
arranque del resto de la app. 2 tests nuevos cubren el flujo
interactivo (con TTY simulada).

**Íconos de ítems** (pedido pendiente de varias sesiones atrás):
imagen real de cada ítem en las tarjetas principales de las dos UIs,
vía el servidor de imágenes público de CCP
(`https://images.evetech.net/types/{type_id}/icon?size=32`, sin auth).
Con fallback silencioso (`onerror` que oculta la imagen) para ítems sin
variante de ícono (SKINs, algunos blueprints) -- no rompe el layout si
el CDN devuelve 404.

**Insight como protagonista**: el banner de recomendación ahora
muestra DOS líneas -- el resumen (como antes) MÁS el primer insight de
`OpportunityExplainer` como segunda línea, con ícono 💡. Antes el
insight completo solo vivía en el panel expandido.

156 tests, todos pasando.

### Sigue pendiente

- NiceGUI: pase visual (el usuario lo calificó "más feo por lejos").
- Wiring de multi-hub en la API/UI (`?hub=amarr`, selector).
- Ideas propuestas sin empezar: alertas, historial de precios,
  comparación entre hubs, exportar CSV.
- Íconos solo en vista de tarjetas -- las tablas (dataframe/AG-Grid) no
  los tienen, agregar imágenes inline en esas requiere un cell renderer
  custom, no trivial en ninguna de las dos librerías.

---

## ✅ Login: issuer inválido + automatización completa del .env

### Segundo bug real de login: InvalidIssuerError

Pasado el bug de `PyJWKClient`, apareció otro en el primer login real:
`jwt.exceptions.InvalidIssuerError`. `issuer="login.eveonline.com"`
estaba hardcodeado sin el esquema -- desde nov. 2023 EVE emite
`"https://login.eveonline.com"` (con esquema). La documentación
oficial de EVE dice explícitamente que hay que aceptar las dos formas.
PyJWT no permite pasar una lista a `issuer=` (solo un string), así que
la validación se movió a mano contra ambas formas aceptadas.
Verificado con 3 tests usando JWT RS256 real (clave RSA generada en el
momento, no simulada): forma vieja, forma nueva, y un issuer ajeno
correctamente rechazado.

### Automatización completa de .env -- eliminado el copy-paste manual

El bug siguiente (`QUARTERMASTER_ENCRYPTION_KEY inválida`) no era un
bug de código -- era un `=` final del base64 cortado al copiar el
valor generado a mano a la terminal. Como esto es un error fácil de
repetir (copiar con doble-click no toma signos de puntuación como
parte de la "palabra"), se automatizó por completo:
`scripts/setup_env.py` genera y ESCRIBE directo en `.env` las 4 claves
auto-generables (`QUARTERMASTER_SESSION_SECRET`,
`QUARTERMASTER_ENCRYPTION_KEY`, `QUARTERMASTER_ADMIN_KEY`,
`QUARTERMASTER_UI_STORAGE_SECRET`) -- cero copy-paste. Integrado en
`Iniciar Quartermaster.bat`, corre solo antes de levantar nada. Nunca
pisa un valor ya seteado (probado explícitamente). `EVE_SSO_CLIENT_ID`/
`SECRET` siguen necesitando completarse a mano -- no hay forma de
generarlos localmente.

155 tests, todos pasando.

---

## ✅ Login roto en producción real + sesgo de referencia para ítems bulk

### Bug real: login fallaba con TypeError en el primer intento real

Primera vez que alguien probó el login con credenciales reales de EVE
-- `PyJWKClient(JWKS_URL, session=self.session)` tiraba
`TypeError: PyJWKClient.__init__() got an unexpected keyword argument 'session'`.
Confusión propia con el patrón de otras librerías que sí aceptan
inyectar una `requests.Session` -- `PyJWKClient` nunca aceptó ese
kwarg, en ninguna versión de PyJWT. Sacado. **Por qué ningún test lo
había cazado**: los tests existentes de `decode_character_identity`
usaban `verify_signature=False`, así que nunca ejercitaban
`_get_signing_key` en absoluto -- agregado un test nuevo que sí lo
llama (con `PyJWKClient` mockeado, sin red real) y afirma explícitamente
que `session` nunca se pasa, para que esto no pueda volver a colarse.

### Sesgo real en el tiempo de venta para ítems que se comercian en bulk

Observación del usuario: calcular el tiempo de venta sobre una
posición de referencia fija de 100 unidades es sesgado para ítems como
munición/misiles, que se comercian en lotes mucho más grandes -- 100
unidades no representa nada real de cómo se tradea ese ítem en la
práctica.

Implementado tamaño de posición de referencia ADAPTATIVO por ítem
(`OpportunityEngine._reference_position_size`): volumen diario dividido
por cantidad de órdenes de venta activas (proxy de "por vendedor", ya
que ESI no expone identidad de vendedor en el book público), con piso
en las 100 unidades de siempre. Expuesto como campo nuevo
(`estimated_exit_position_size`) para que la UI muestre el número REAL
usado, no un "100u" hardcodeado que ya no sería cierto.

**Bug propio encontrado en el camino**: la primera versión dividía el
STOCK listado ahora mismo (`total_sell_volume_remain`) en vez del
FLUJO diario real (`daily_volume`) -- una sola orden atípica (alguien
liquidando un stockpile) podía disparar la referencia a un tamaño
absurdo (1.5 millones de unidades en un caso de test real, 75 días de
"tiempo de venta"). Corregido a `daily_volume / sell_order_count`,
inmune a ese tipo de outlier. Verificado contra munición real:
"Carbonized Lead M" pasó de "100u, ~0 min" (sesgado, como señaló el
usuario) a "11.931u, ~2.7h" (representativo).

146 tests, todos pasando.

---

## ✅ Los 5 hubs verificados + watchlist multi-hub completa

### Verificación externa de los 5 hubs

Antes de construir sobre los IDs de `trade_hub.py`, se verificaron
contra fuentes independientes reales (búsqueda web, ya que no hay
acceso a ESI desde este entorno): Adam4EVE (listado de estaciones
sacado directo del SDE de CCP), DOTLAN EveMaps, zkillboard, y las URLs
de mercado de EVE Workbench (que codifican region_id/station_id en la
ruta). **Los 5 hubs -- Jita, Amarr, Dodixie, Rens, Hek -- confirmados
exactos**, region_id y station_id coinciden en las 4 fuentes cruzadas
para cada uno. Ya no queda ninguna advertencia de "no verificado" en
el código.

### Watchlist multi-hub (punto 1, completo)

Antes, un ítem trackeado (user_id, type_id) no decía a qué hub
pertenecía -- pero "Tritanium" se comercia en los 5 hubs simultáneamente
con precios distintos. Migración no destructiva
(`scripts/migrate_v5_tracked_types_region.py`) agrega `region_id` a la
clave de `tracked_types`: ahora es (user_id, type_id, region_id), no
(user_id, type_id). Todo lo que ya estaba trackeado se migra a Jita
(el único hub que existía antes) -- probado contra una copia real:
40 → 40 filas, sin pérdida, idempotente.

Repositorio (`SQLiteTypeRepository`) y `ApiServices` actualizados:
`track`/`untrack`/`untrack_many`/`untrack_all`/`is_tracked`/`tracked_type_ids`
ahora todos requieren `region_id` explícito. **Probado de punta a
punta**: trackear "Tritanium" en Amarr mientras ya está trackeado en
Jita no afecta la watchlist de Jita en absoluto -- son entradas
completamente independientes, confirmado con datos reales.

145 tests, todos pasando.

### Sigue pendiente (sin cambios respecto al roadmap anterior)

- La API todavía no acepta un parámetro de hub desde afuera (`dependencies.py`
  sigue construyendo un `ApiServices` fijo a Jita al arrancar).
- Ninguna UI tiene selector de hub.
- El scheduler automático solo corre para Jita.
- Rate limits de ESI con varios hubs en paralelo, no evaluado.

---

## 🔴 Modularización multi-hub: base construida y probada, UI y watchlist pendientes

Pedido del usuario: expandir el rango de la herramienta más allá de
Jita, modularizando cada región. Investigado antes de tocar nada: la
base de datos YA era multi-región por diseño (`region_id` es columna
real en `market_orders`/`market_history`/`sync_status` desde el
principio) -- lo hardcodeado era la CONSTANTE de Jita usada en la capa
de orquestación, no el schema.

### Construido y probado

- **`domain/value_objects/trade_hub.py`** (nuevo): registro curado de
  los 5 hubs de trading reales de EVE (Jita, Amarr, Dodixie, Rens,
  Hek) -- cada uno como (region_id, station_id) juntos, nunca por
  separado (la lección del bug "Jita vs. La Forge entera" aplica
  igual: mezclar región de un hub con estación de otro repite el mismo
  error). ⚠️ Los region_id/station_id de Amarr/Dodixie/Rens/Hek son de
  memoria de entrenamiento, nunca verificados contra ESI real en este
  entorno (sin red) -- Jita sí está confirmado (es el que ya se usaba).
  Si al sincronizar alguno de los otros 4 da 0 resultados, ese ID es
  el primer sospechoso.
- **Hallazgo real revisando el código**: `ApiServices` nunca pasaba
  `location_id` explícito a NINGUNA llamada del repositorio -- todas
  confiaban en el default hardcodeado a Jita de
  `SQLiteMarketRepository`. Cambiar `region_id` a otro hub sin arreglar
  esto hubiera emparejado la región nueva con la estación de Jita
  (resultados vacíos o, peor, mezclados). Mismo hallazgo en
  `DetectOpportunitiesUseCase` y en `MarketSnapshotRecorder`
  (`JITA_STATION_ID` hardcodeado DENTRO de la query SQL).
- **`ApiServices.station_id`** (nuevo campo) + **`ApiServices.for_hub(hub_key)`**
  (nuevo classmethod): construye el servicio completo para cualquier
  hub del registro, resolviendo region_id/station_id juntos. 100%
  retrocompatible -- el constructor viejo (`region_id=...` sin
  `station_id`) sigue funcionando exactamente igual, default a Jita.
- **`DetectOpportunitiesRequest.station_id`**, **`SmartAutoSeedJob.station_id`**,
  **`MarketSnapshotRecorder.record_snapshot(region_id, station_id)`**:
  mismo patrón, todos con default a Jita, threading explícito en cada
  llamada al repositorio.
- **Probado de punta a punta contra datos reales**: `ApiServices.for_hub("jita")`
  sigue devolviendo exactamente los mismos resultados de siempre;
  `ApiServices.for_hub("amarr")` devuelve una lista VACÍA (nunca se
  sincronizó), no datos de Jita filtrados mal -- exactamente el
  comportamiento correcto, confirmado explícitamente con un test que
  falla si se mezclan.

### 🐛 Bug propio encontrado y arreglado en el camino

Al insertar el classmethod `for_hub`, un `str_replace` mal apuntado
cortó el cuerpo de `__init__` a la mitad -- todo lo que venía después
(`self.use_case`, `self.status_repo`, `self.eve_sso_client`, el lock
del seed) quedó como código muerto después de un `return`, en vez de
adentro del constructor. Se detectó de inmediato al correr la suite
completa (8 tests fallaron con `AttributeError` sobre atributos que
deberían existir) -- exactamente el tipo de error que ejecutar tests
después de cada cambio está pensado para cazar. Arreglado, 145 tests
pasando de nuevo.

### Lo que falta -- no se tocó todavía

1. **`tracked_types` no sabe a qué hub pertenece cada ítem** -- hoy la
   clave es (user_id, type_id). Un ítem como "Tritanium" se comercia en
   TODOS los hubs simultáneamente con precios distintos -- trackearlo
   sin especificar hub es ambiguo. Necesita una migración de schema
   (agregar `region_id` a la clave, no destructiva, mismo patrón que
   las anteriores) antes de que la watchlist tenga sentido multi-hub.
2. **Los routers de la API no aceptan un parámetro de hub** -- hoy
   `dependencies.py` construye UN `ApiServices` global (Jita
   hardcodeado) al arrancar. Necesita aceptar `?hub=amarr` (o similar)
   y usar `ApiServices.for_hub(...)` en vez de la instancia fija.
3. **Ninguna UI tiene selector de hub** -- ni Streamlit ni NiceGUI
   saben que esto existe todavía.
4. **El scheduler automático** (sync periódico en background) solo
   corre para Jita -- correr para varios hubs a la vez es una decisión
   de diseño aparte (¿todos en paralelo? ¿uno por vez, rotando?).
5. **Credenciales/rate limits de ESI con 5 hubs en paralelo** -- no
   evaluado. Sincronizar 5 regiones en vez de 1 multiplica por 5 la
   carga contra ESI; puede necesitar espaciar las corridas.

145 tests, todos pasando. La base es sólida y real, pero esto es
backend únicamente todavía -- no hay forma de usarlo desde ninguna UI
hasta que se completen los puntos 1-3.

---

## ✅ ROI absurdo sin advertencia -- causa real encontrada (no era Jita vs. Forge)

El usuario reportó ROI de miles de % sin ninguna advertencia, y planteó
que el problema era seguir analizando solo Jita 4-4 en vez de The
Forge completo. Investigado con sus datos reales antes de tocar nada
-- la hipótesis de fondo (Jita vs. Forge) es la dirección CONTRARIA a
la correcta: mezclar estaciones de toda la región produciría
"arbitrajes" entre lugares que ni siquiera están conectados sin
transporte, exactamente el bug que ya se había corregido antes (el
"hallazgo mayor" de sesiones atrás). Volver a eso habría empeorado el
problema, no arreglado.

**Causa real, confirmada con las 3 órdenes de libro de los ítems
exactos de la captura**: "Arch Angel Nuclear S" tenía 4 órdenes de
compra (mejor precio 1.1 ISK) y 19 de venta (mejor precio 78.69 ISK) --
spread de ~70x, ROI 6581.8%. El chequeo existente
(`CAUTION_THIN_ORDER_BOOK`) solo mide CANTIDAD de órdenes por lado
(mínimo 2) -- 4 órdenes de compra pasan ese umbral sin problema, pero
esas 4 órdenes están en un mundo de precio totalmente distinto a las
de venta. El conteo mide profundidad, no si compradores y vendedores
están mirando el mismo rango de precio -- son chequeos distintos,
faltaba el segundo.

**Arreglado**: nueva categoría `CAUTION_IMPLAUSIBLE_SPREAD` -- se
dispara cuando el precio de venta supera 5x el de compra
(`MAX_PLAUSIBLE_SPREAD_RATIO`), incluso con suficientes órdenes de cada
lado. Verificado contra los 3 ítems exactos de la captura del usuario:
- "Carbonized Lead M" (ROI 83.3%, spread ~2x, book real de ambos
  lados): sigue "Neutral" -- correcto, no es spread implausible, es un
  mercado genuinamente ineficiente (ya reflejado en su liquidez baja).
- "Arch Angel Nuclear S" (ROI 6581.8%, spread ~70x): ahora
  `caution_implausible_spread` -- éste era el que se estaba colando.
- "Arch Angel Carbonized Lead S" (ROI 11350%, 1 sola orden de compra):
  sigue `caution_thin_order_book` -- ya se detectaba bien.

Precedencia de chequeos ajustada: `thin_order_book` → `no_volume_data`
→ `implausible_spread` → `low_liquidity` → `high_risk` → `neutral` --
los problemas más fundamentales de calidad de dato se chequean antes
que la coherencia del spread puntual.

Badges actualizados en las dos UIs (`↕️ Precaución · Spread
implausible`). `exclude_caution` (el filtro existente) reconoce la
categoría nueva automáticamente -- no dependía de una lista
hardcodeada, solo del prefijo `caution_`.

## ✅ Bug real: el launcher solo abría Streamlit, nunca NiceGUI

`Iniciar Quartermaster.bat` nunca se actualizó cuando se agregó la
segunda UI -- solo lanzaba la API y Streamlit. Agregado el paso que
falta: NiceGUI en su propia ventana (mismo patrón que la API, para ver
sus logs por separado), puerto 8502, sin necesidad de un `start
http://...` manual (NiceGUI abre el navegador solo, igual que
Streamlit con `--server.headless false`).

138 tests, todos pasando.

---

## ✅ Bug real de Windows en los tests + diagnóstico de checkout desactualizado

Primera corrida real de `pytest` en Windows del usuario -- reveló dos
problemas distintos, uno mío y uno de sincronización de archivos:

### Bug real: `PermissionError: [WinError 32]` al limpiar DBs temporales

En POSIX (donde se escribió y probó todo hasta ahora) se puede borrar
un archivo aunque siga abierto. Windows bloquea el borrado mientras
cualquier proceso tenga el archivo abierto -- varios tests hacían
`db_path.unlink(missing_ok=True)` confiando en que el garbage collector
ya hubiera cerrado la conexión SQLite antes de esa línea, lo cual no
está garantizado en el momento exacto. Nunca se vio en este entorno
(Linux, sin Windows real para probar) hasta la primera corrida real del
usuario.

**Arreglado**: `tests/_winsafe.py` (nuevo) -- `safe_unlink()` reintenta
con un `gc.collect()` de por medio antes de rendirse. Aplicado a los 9
archivos de test afectados (`test_seed_job.py`,
`test_market_snapshot_recorder.py`, `test_services.py`, etc.).
`pyproject.toml` actualizado (`pythonpath = ["src", "tests"]`) para que
el helper sea importable desde cualquier test sin imports relativos
frágiles.

### No es un bug: checkout desactualizado

`sqlite3.OperationalError: no such table: users` en varios tests --
significa que el `database/schema.sql` LOCAL del usuario todavía es la
versión pre-multi-tenancy (sin `users`/`oauth_tokens`). Confirma la
sospecha de la sesión anterior (UI vieja en las capturas): la carpeta
`Quartermaster` del usuario tiene una mezcla de archivos viejos y
nuevos, no una extracción limpia del último zip. No es algo para
arreglar en código -- es un problema de sincronización de archivos,
comunicado claramente para que haga una extracción limpia.

136 tests (mismo número que antes -- este fix no agrega tests nuevos,
corrige infraestructura de testing existente).

---

## ✅ Feedback real de UX + preparación de versión compartible

### Recomendación protagonista + liquidez rediseñada (feedback real)

- **Recomendación**: antes era texto chico al final de la tarjeta (o la
  palabra plana "neutral" en la tabla) -- "la recomendación tiene que
  ser protagonista, no algo que solo se ve en el detalle". Ahora es un
  banner de ancho completo con fondo de color, ubicado entre el header
  y las métricas -- lo segundo que se lee después del nombre/score, en
  las dos UIs, en tarjetas Y en tablas (con ícono en la columna).
- **Liquidez**: la barra horizontal larga y fina "quedaba fuera de
  lugar comparada con el resto". Reemplazada por un pill compacto --
  mismo tamaño y forma que el badge de riesgo de al lado, mismo peso
  visual. La barra detallada se mantiene disponible para contextos con
  más espacio (no se usa en la tarjeta principal).

### Bug real: Streamlit abría dos pestañas siempre

`Iniciar Quartermaster.bat` tenía DOS mecanismos de apertura de browser
al mismo tiempo: `--server.headless false` (que ya hace que Streamlit
abra el navegador solo) MÁS un `start http://localhost:...` explícito
agregado "como red de seguridad" sin darnos cuenta de que duplicaba lo
que Streamlit ya hacía. Sacado el segundo. De paso, el `pip install`
del mismo .bat estaba desactualizado (no instalaba `cryptography`/
`pyjwt`, agregadas para el login) -- ahora usa `pip install -e ".[api]"`
en vez de una lista de paquetes sueltos, así nunca más queda
desactualizado cuando se agregue una dependencia nueva.

### Preparación de versión compartible

- **`LICENSE`** (nuevo): source-available -- libre para uso personal y
  comunitario sin fines de lucro, prohibido revender o redistribuir
  como producto comercial sin permiso. Protección legal real, dado que
  la protección técnica de código Python es limitada por naturaleza
  (ver nota abajo).
- **`.gitignore`** (nuevo): protege `.env` (secretos), `database/*.db`
  (datos personales del usuario -- cada quien corre su propio
  Smart Auto-Seed), logs, y los archivos generados de siempre.
- **`.env.example`** (nuevo): plantilla documentada de todas las
  variables de entorno, sin valores reales.
- **`python-dotenv`** conectado en `main.py` -- antes el `.env` hubiera
  sido un archivo muerto, nada lo cargaba. Probado con un `.env` real
  (no simulado).
- **README.md reescrito** para público externo -- el anterior era en
  realidad un changelog de desarrollo interno (movido a
  `docs/DEVLOG.md`, preservado por su valor histórico).
- **`docs/SETUP.md`** (nuevo): pasos completos, incluidos los de EVE
  SSO prometidos hace unas sesiones.
- **Hallazgo real durante la preparación**: un clon nuevo del proyecto
  arrancaba con `item_types` completamente vacía -- el Smart Auto-Seed
  trae order books y volumen, pero NUNCA nombres de ítems. Sin esto,
  todo se vería como "Type-1234". Faltaba un importador para el
  catálogo completo (`invTypes` del SDE) -- solo existía uno para
  categorías/grupos. Construido `scripts/import_sde_types.py`, mismo
  patrón que el existente, con backfill de `category_id` vía JOIN con
  `groups`. Probado con datos sintéticos reales (formato JSONL real del
  SDE), incluido el caso de líneas inválidas salteadas correctamente.

### Nota honesta sobre "proteger el código"

Python es un lenguaje interpretado -- no existe una forma de compilar
esto a algo verdaderamente irreversible como sí se puede con C/C++. Lo
que SÍ es real y ya está:
- Protección **legal** (LICENSE) -- lo que efectivamente usa la enorme
  mayoría de proyectos solo-dev para esto.
- Ningún secreto ni dato personal se distribuye (`.gitignore`, `.env.example`).

Lo que NO se hizo (y sería el siguiente nivel si de verdad hace falta):
compilar los motores de dominio (el "secret sauce" real: los 5 engines
+ el explainer) con Cython a extensiones nativas -- protección técnica
genuina pero parcial (un atacante decidido igual puede desensamblar),
y es un trabajo de build tooling separado, no algo para hacer sin que
el usuario decida invertir tiempo específicamente en eso.

136 tests, todos pasando.

---

## ✅ Etapa 1 de la generalización: vocabulario del dominio (completa y probada)

Retomado tras la decisión del usuario de apuntar a otros mercados,
usando EVE como primer caso -- ver
docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md para el plan completo de 5
etapas. Esta es la primera, acotada deliberadamente al **núcleo de
dominio**, dejando el contrato de la API estable a propósito.

**Renombrado:**
- `TaxProfile` → `FeeProfile` (`broker_fee_rate`→`entry_fee_rate`,
  `sales_tax_rate`→`exit_fee_rate`). Archivo movido:
  `domain/value_objects/tax_profile.py` → `fee_profile.py`.
- `Opportunity.type_id/type_name/region_id` →
  `instrument_id/instrument_name/market_id`.
- `OpportunityInput` (motor) y `OpportunityEngine.TransactionCost.broker_fee_buy`
  → `entry_fee`, mismo criterio.
- `DetectOpportunitiesRequest.tax_profile` → `fee_profile`.

**Deliberadamente NO tocado en esta etapa** (para acotar el alcance a
algo verificable en una sola pasada):
- Los Ports (`MarketRepository`, `TypeRepository`) y sus implementaciones
  SQLite siguen usando `type_id`/`region_id` en sus firmas -- son la
  capa de infraestructura específica de EVE/ESI, renombrarlos es una
  Etapa 1b separada.
- **El contrato JSON de la API sigue exponiendo `type_id`/`region_id`**
  -- `OpportunitySchema.from_domain()` traduce explícitamente
  `opportunity.instrument_id` → JSON `"type_id"`. Esto es intencional:
  generalizar el dominio y romper el contrato público (forzando cambios
  en cascada en las dos UIs) en el mismo movimiento hubiera sido
  arriesgado sin necesidad. Confirmado con smoke tests reales: ninguna
  de las dos UIs necesitó cambios.

132 tests, todos pasando. Probado de punta a punta contra datos reales
de `trader.db` -- incluida una verificación explícita de que el dominio
usa `instrument_id`/`market_id` internamente pero el JSON que consumen
las UIs no cambió ni un carácter.

## 🔧 Errores reportados al probar en Windows (resueltos)

1. `ModuleNotFoundError: No module named 'presentation'` -- el usuario
   corrió uvicorn desde `C:\Users\Toto` en vez de
   `C:\Users\Toto\Quartermaster`. No es un bug, se resolvió solo al
   pararse en la carpeta correcta.
2. `ModuleNotFoundError: No module named 'jwt'` -- real: `pyjwt` y
   `cryptography` (agregados a `pyproject.toml` cuando se construyó el
   sistema de login) nunca se instalaron en el entorno del usuario.
   Fix: `pip install pyjwt cryptography`, o `pip install -e ".[api]"`
   para traer todo el extra `api` de una.

---

## 🔴 Hallazgo real: liquidez=100 con órdenes de compra sin moverse (investigado y parcialmente resuelto)

Reporte del usuario: ítems con liquidez 100 cuyas órdenes de compra
seguían casi intactas un día después. Investigado a fondo, causa raíz
confirmada:

**`daily_volume` (mitad de la fórmula de liquidez, media geométrica con
`depth_score`) es REGIONAL (La Forge entera), no específico de Jita** --
limitación real de ESI (no hay endpoint de historial por estación), ya
documentada en el código pero cuyo impacto práctico no estaba bien
comunicado. Un ítem puede parecer muy líquido por actividad en OTRAS
estaciones de la región, mientras que en Jita 4-4 específicamente (donde
están las órdenes del usuario) casi no se mueve. La profundidad del
book (`total_sell_volume_remain`) SÍ está bien filtrada a Jita desde la
v1.4 -- el problema es solo el lado del volumen.

**Encontrado de paso**: la tabla `market_order_snapshots` existía en el
schema desde hace tiempo, diseñada exactamente para resolver este
problema (guardar el estado del book de Jita en el tiempo), pero
**nadie escribía ahí -- 0 filas en producción**. Infraestructura muerta.

**Arreglado esta sesión:**
1. `MarketSnapshotRecorder` (nuevo) -- graba un snapshot diario del book
   de Jita (filtrado por estación, no región) en cada Smart Auto-Seed.
   `get_jita_turnover_proxy()` compara snapshots en el tiempo para
   derivar cuánto se movió REALMENTE en Jita -- devuelve `None`
   explícito con menos de 2 snapshots (nunca inventa un número con un
   solo punto de datos). Conectado al final de `SmartAutoSeedJob.run()`,
   probado con datos reales (40 ítems capturados en la primera corrida
   contra `trader.db`).
2. `OpportunityExplainer` ahora advierte EXPLÍCITAMENTE en la
   interpretación de liquidez que el volumen es regional, no de Jita,
   cuando hay evidencia de volumen (antes no lo mencionaba en absoluto).

**Lo que falta -- necesita días de datos acumulados:**
El proxy de turnover de Jita (`get_jita_turnover_proxy`) todavía NO se
usa en el score ni se muestra en la UI -- recién tiene sentido una vez
que se acumulen varios días de snapshots (con 1-2 no hay señal
confiable). Próximo paso una vez haya suficiente historia: usar el
proxy como cross-check -- si `daily_volume` regional sugiere liquidez
alta pero el proxy de Jita sugiere mucho menos movimiento real, generar
un insight/advertencia específica en vez de solo el caveat genérico
actual. Requiere además decidir cómo exponer esto en `Opportunity`/API
sin romper el score existente.

132 tests. `MarketSnapshotRecorder` probado con datos reales de Jita
(no simulados) -- confirma 40 type_ids con orden activa capturados en
la primera corrida.

---

## ✅ Rediseño visual REAL (no solo color, jerarquía de información)

El usuario marcó correctamente que el rediseño anterior (pills de
color) era superficial -- coloreaba lo que ya estaba, sin cambiar qué
se muestra ni cuánto. Esta vuelta se atacó eso puntualmente:

- **Tarjeta reducida a lo mínimo por defecto**: nombre, score, 3
  métricas compactas (ROI/Riesgo/Liquidez), y un badge CORTO (ícono +
  categoría, ej. "✅ Comprar") en vez de la oración completa. Todo lo
  demás -- razón completa de la recomendación, precios buy/sell, conteo
  de órdenes, tiempo de venta, confianza, explicación completa,
  desglose numérico -- se movió al panel expandible. Esto es
  literalmente lo que pedía el punto 7 del documento de rediseño
  ("visible inicialmente: score, indicadores principales, resumen
  corto") -- la versión anterior no lo había cumplido de verdad, seguía
  mostrando todo siempre.
- **Barra de resumen agregado** (nueva, no existía): mostrando/score
  promedio/mejor score/cantidad recomendadas, ANTES de la lista --
  elemento de "dashboard profesional" que faltaba por completo.
- **Números de ranking** (#1, #2, #3...) en las tarjetas -- el ranking
  es el valor central de la herramienta y antes no se reforzaba
  visualmente en ningún lado.

Aplicado consistente en Streamlit (Dashboard + Tracked Items) y NiceGUI
(mismas dos páginas) -- mismos componentes compartidos entre ambas UIs,
mismo criterio en las dos. 124 tests, probado con datos reales contra
`trader.db` migrado (server falso, mismo patrón de siempre).

**Honestidad sobre el alcance**: se tocó la vista de mayor tráfico
(lista de oportunidades, tarjetas). No se rediseñó el layout general
(sidebar, navegación, tipografía de encabezados) más allá de lo ya
hecho la vuelta anterior -- si se quiere ir más lejos con eso, es
trabajo aparte.

## 💬 Evaluación de negocio (conversación, no código)

El usuario preguntó si esto tiene potencial comercial real. Respuesta
dada, resumida acá para no perderla: la comunidad de EVE es chica pero
con cultura de trading real, y el motor de explicaciones es un
diferenciador genuino frente a lo que ya existe gratis. PERO: los datos
de ESI son públicos (sin moat), ya hay herramientas gratuitas
establecidas en el nicho, el mercado direccionable es chico, y **CCP
tiene reglas propias sobre monetización de apps de terceros que no se
investigaron todavía** -- eso es lo primero a revisar antes de asumir
que cobrar es viable. Veredicto: buen proyecto para reputación/comunidad,
expectativas bajas para "SaaS que escala" en el sentido tradicional.

---

## ✅ Login con EVE conectado a las dos UIs -- construido y probado

Cierra el trabajo de multi-tenancy: ahora Streamlit y NiceGUI tienen un
botón real de "Iniciar sesión con EVE", guardan la sesión, y usan
`scope=tracked` (watchlist personal) solo cuando corresponde.

### 🐛 Bug de concurrencia real encontrado ANTES de que llegara a producción

Al conectar el login, encontré que tanto Streamlit (`@st.cache_resource`
en `get_client()`) como NiceGUI (`client = ApiClient()` a nivel de
módulo en `main.py`, compartido entre las dos páginas) tenían el mismo
patrón: **una sola instancia de `ApiClient` compartida entre TODAS las
sesiones de usuario del proceso**. Antes de login esto no importaba
(`ApiClient` no tenía estado propio); ahora que `session_token` vive en
la instancia, compartirla significa que el token de un usuario podría
filtrarse al request de otro -- dos personas usando el mismo server al
mismo tiempo verían la watchlist equivocada. Mismo tipo de bug que el
de `market_orders` compartido, pero en la capa de sesión. Arreglado
ANTES de que hubiera un segundo usuario real para sufrirlo:

- **Streamlit**: sacado `@st.cache_resource` de `get_client()` -- cada
  rerun construye su propio cliente, barato (`requests.Session()`), sin
  riesgo de cruce.
- **NiceGUI**: cada función de página (`@ui.page`) construye SU PROPIO
  `ApiClient()` -- ya no recibe uno compartido como parámetro. La
  persistencia entre navegaciones usa `app.storage.user` (por navegador,
  vía cookie que maneja NiceGUI), no un objeto Python compartido.

### Lo construido

- **`ApiClient`**: soporta `session_token`, adjunta
  `Authorization: Bearer` automático en cada request una vez logueado,
  `get_login_url()`, `get_me()`. Probado con sesión HTTP falsa -- header
  presente/ausente según corresponda, logout limpia todo.
- **`streamlit_app/auth_ui.py`** (nuevo, compartido entre `app.py` y
  `pages/02_tracked_items.py`): restaura el token desde
  `st.query_params` cuando el browser vuelve del login, lo guarda en
  `st.session_state` (persiste dentro de la pestaña), sidebar de
  login/logout.
- **`ui/auth_ui.py`** (nuevo, compartido entre las dos páginas de
  NiceGUI): mismo patrón, usando `app.storage.user` para persistencia
  entre navegaciones internas.
- **Dashboard (ambas UIs)**: sigue funcionando sin sesión (Discovery
  público), pasa a `scope=tracked` automáticamente al loguearse.
- **Tracked Items (ambas UIs)**: login obligatorio -- sin sesión válida,
  muestra el prompt y no llama a ningún endpoint protegido (verificado
  con un fake session que hace `assert` si algo protegido se llama sin
  header).

Probado de punta a punta con sesión HTTP falsa + datos reales de
`trader.db` migrado: login vía query param, persistencia entre páginas
sin repetir el token en cada URL, y los tres casos sin sesión (Dashboard
cae a Discovery, Tracked Items frena con prompt, ningún endpoint
protegido se llama antes de tener sesión válida). 124 tests totales.

### Lo que sigue sin poder probarse acá

El intercambio real de tokens contra `login.eveonline.com` sigue sin
correr contra el servidor real (sin red en este entorno) -- ver
changelog de `eve_sso_client.py`. Es el primer punto donde de verdad
hace falta que el usuario tenga credenciales reales de
developers.eveonline.com para confirmar el flujo completo.

Nueva variable de entorno opcional: `QUARTERMASTER_UI_STORAGE_SECRET`
(si no se fija, NiceGUI genera una random en cada arranque -- funciona,
pero invalida todos los logins activos cada vez que se reinicia el
proceso; fijarla es mejor para algo que se comparte con la comunidad).

---

## ✅ Observabilidad (logging real) -- construida y probada

Aclarado lo que "herramientas de logeo" quería decir: logging/observabilidad,
no login (eso ya estaba cubierto). Hallazgo real revisando el proyecto:
existían loggers (`quartermaster.api`, `quartermaster.scheduler`) pero
**cero handlers configurados en ningún lado** -- todos los
`logger.info(...)` que ya estaban en el código no iban a ningún lado
útil, se descartaban en silencio.

- **`infrastructure/observability/logging_setup.py`** (nuevo): handlers
  reales -- consola + archivo rotativo (`logs/quartermaster.log`, 10MB
  x 5 backups). Idempotente (no duplica handlers si se llama dos veces,
  importante por el `--reload` de uvicorn). Probado de verdad con
  escritura real a archivo temporal (stdlib puro, sin dependencias).
- **Middleware de request logging** en `main.py`: método, path, status,
  duración de CADA request. Warnings automáticos en 4xx/5xx.
- **Logging explícito de eventos de auth** en `ApiServices`:
  `login_success`/`login_failed` con contexto (user_id, character_id,
  motivo del fallo) -- confirmado funcionando en vivo durante los tests
  de auth (se ven los logs reales en la salida de la suite).
- **`GET /api/admin/stats`** (nuevo router, protegido con
  `QUARTERMASTER_ADMIN_KEY` -- un secreto compartido, NO un sistema de
  roles, todavía no existe ese concepto): usuarios totales, cuántos
  tienen watchlist, logins recientes, estado del último sync. Pensado
  para chequear rápido "¿hay gente usándolo, está todo bien?" sin leer
  archivos de log a mano.

Nueva variable de entorno: `QUARTERMASTER_ADMIN_KEY` (cualquier string
secreto elegido a mano, no hay generador -- es más simple que las otras
claves porque no cifra nada, solo compara un string).

117 tests, todos pasando. Probado con datos reales de `trader.db`
migrado (stats reflejan los 40 ítems / 1 usuario legacy reales).

---

## 🔴 MULTI-TENANCY + EVE SSO -- base construida y probada, falta el frontend

Trabajo grande: usuarios reales vía login de EVE, cada uno con su
propia watchlist. Decisión del usuario: multi-usuario desde el
arranque (no "yo primero, generalizo después"), pensando en compartir
con la comunidad para juntar referencias.

### Lo que está construido Y probado de verdad (sin red externa)

- **Migración no destructiva** (`scripts/migrate_v4_multi_tenant.py`):
  agrega `users`/`oauth_tokens`, y migra `tracked_types` (antes sin
  dueño) a un usuario "legacy" placeholder, preservando los 40 ítems
  reales del usuario sin pérdida. Probada contra una copia real de
  `trader.db`: 40→40 filas, idempotente (correrla dos veces no duplica
  nada).
- **`User` (domain) + `UserRepository` (port) + `SQLiteUserRepository`**:
  login/re-login idempotente, nombres de personaje actualizables (por
  si el jugador renombra su personaje en EVE).
- **`TokenEncryptor`** (Fernet/AES): tokens de EVE SSO cifrados en
  reposo, NUNCA texto plano. Probado con la librería `cryptography`
  real (SÍ estaba disponible en este sandbox) -- roundtrip, rechazo de
  clave incorrecta, error claro sin clave configurada.
- **`session_tokens`** (JWT propios, HS256): emisión/verificación de
  sesión después de un login exitoso. Probado con `PyJWT` real (SÍ
  disponible acá) -- roundtrip, rechazo de token manipulado, expiración
  real forzada y verificada.
- **`EveSSOClient`**: flujo OAuth2 + PKCE completo, según la spec de
  CCP. PKCE (generación y verificación SHA256) y construcción de URL de
  autorización probados 100% reales (son criptografía/parsing puro).
  Intercambio de code por tokens y decodificación de JWT probados con
  sesión HTTP falsa (mismo patrón que `ESIClient`) -- el intercambio
  real contra `login.eveonline.com` NUNCA se probó en este entorno (sin
  red), primera vez que corre de verdad es cuando el usuario lo pruebe
  con credenciales reales de developers.eveonline.com.
- **Todo `tracked_types` re-scopeado por `user_id`** (repo + servicio +
  routers), con tests de aislamiento cruzado (usuario A no ve ni puede
  tocar la watchlist de B).
- **Router `/api/auth/*`** (login, callback, me) + `get_current_user`/
  `get_optional_current_user` como dependencies de FastAPI.
  `scope=discovery` en `/api/opportunities` sigue siendo público (es
  inteligencia de mercado general, no debería requerir login);
  `scope=tracked` sí exige sesión válida (401 si no).
- **Flujo completo probado end-to-end** llamando directo a las
  funciones handler del router (login → callback simulado → me →
  tracked-items scoped → 401 en tracked sin login) -- 111 tests totales.

### 🐛 Bug real encontrado en el camino (arreglado)

`untrack`/`untrack_many`/`untrack_all` tenían un flag `also_cleanup_orders`
que borraba `market_orders` del ítem al destrackearlo. Tenía sentido
cuando `tracked_types` era la única fuente de qué sincronizar; desde el
Smart Auto-Seed, `market_orders` es un recurso COMPARTIDO por todos los
usuarios (alimenta Discovery para todo el mundo). Si esto hubiera
llegado a producción multi-usuario tal cual estaba, el Usuario A
destrackeando algo le habría borrado los datos de mercado al Usuario B
que seguía mirando ese mismo ítem. Sacado por completo (no solo
desactivado), con test de regresión explícito.

### Lo que falta -- no se tocó todavía

1. **Botón de login en Streamlit y NiceGUI** -- ninguna de las dos UIs
   tiene todavía un botón "Iniciar sesión con EVE", ni lógica para
   guardar el `session_token` (llega por query param a la URL de
   retorno) ni para mandarlo en el header `Authorization` de cada
   request. `api_client.py` no tiene todavía soporte para auth en
   absoluto.
2. **Credenciales reales de EVE SSO** -- el usuario necesita registrar
   una app en https://developers.eveonline.com (obtener
   `EVE_SSO_CLIENT_ID`/`EVE_SSO_CLIENT_SECRET`, configurar la URL de
   callback exacta) antes de que el login real pueda probarse.
3. **Variables de entorno nuevas a configurar** antes de arrancar la
   API: `EVE_SSO_CLIENT_ID`, `EVE_SSO_CLIENT_SECRET`,
   `QUARTERMASTER_SESSION_SECRET` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`),
   `QUARTERMASTER_ENCRYPTION_KEY` (`python -c "from infrastructure.security.token_encryption import generate_key; print(generate_key())"`).
4. **Reclamar el usuario "legacy"** -- los 40 ítems trackeados que
   tenía el usuario antes de esto quedaron asociados a un usuario
   placeholder (`eve_character_id=-1`). Falta decidir e implementar
   cómo "reclamarlos" la primera vez que el usuario real haga login con
   su personaje de EVE (¿fusionar automático si es el primer login?
   ¿un botón explícito "migrar mi watchlist vieja"?).
5. **"Herramientas de logeo"** -- el usuario pidió esto pero quedó
   ambiguo si se refería a login (cubierto arriba) o a
   logging/observabilidad (ver errores, cuántos usuarios, actividad).
   Sin resolver todavía, pendiente de su respuesta.
6. **Manejo del caso "usuario cancela el login"** -- si el usuario
   aprieta "Denegar" en la pantalla de EVE, el callback recibe
   `error=access_denied` en vez de `code`, y hoy eso rompería con un
   error de FastAPI poco claro en vez de un mensaje entendible.
   Anotado en el router, no arreglado todavía.
7. **Refresh automático de sesión** -- hoy la sesión dura 24hs fijas,
   sin renovación automática ni uso del refresh_token de EVE para
   extenderla sin pedirle al usuario que vuelva a loguearse.

---

## ✅ Rediseño visual completo (Streamlit + NiceGUI)

Sistema de diseño real, no parches sueltos: paleta, tipografía y umbrales
de color definidos UNA vez y reusados en ambos frameworks (mismos
valores hex en `streamlit_app/theme.py` y `ui/theme.py`, documentado
explícitamente que si uno cambia, el otro debe cambiar igual).

**Tokens**: fondo más profundo (`#0B0D12`), superficie/superficie-elevada
diferenciadas, jerarquía de texto (primario/secundario/muted), colores
semánticos (éxito/advertencia/peligro/info) que usan los MISMOS
umbrales que `OpportunityExplainer` (70/40) -- el color de un indicador
nunca contradice el texto que lo acompaña.

**Componentes visuales nuevos** (HTML/CSS reusable, no repetido por
call site):
- Score pill coloreado por rango (verde/ámbar/rojo).
- Badge de riesgo con color semántico (Low=verde .. Critical=rojo),
  reemplaza el texto plano "Medium"/"High".
- Barra de liquidez horizontal (refuerzo visual del número, no lo
  reemplaza).

**Tarjeta de oportunidad rediseñada** en las dos UIs: header con nombre
prominente + score pill alineado a la derecha, fila de métricas con
íconos y los indicadores de color nuevos, meta-info más discreta
(tipografía monoespaciada, color muted), mismo panel expandible de
análisis de la mejora anterior. Aplicado también a la vista compacta de
gestión de Tracked Items (checkbox list), no solo a las tarjetas
completas de Discovery.

**Honestidad sobre el alcance**: esto es un rediseño real y coherente,
aplicado a los componentes que existen HOY (tarjetas, listas, badges).
No se tocó la estructura de layout general (sidebar/drawer, navegación),
ni se agregó iconografía más allá de la ya usada -- si se quiere ir más
lejos (nuevo layout, más iconografía, animaciones), es una tarea aparte.

76 tests, todos pasando (sin tests nuevos -- este cambio es
estrictamente visual, no toca lógica de negocio). Ambas UIs, las tres
páginas, probadas de punta a punta contra datos reales con el patrón de
"server falso" de siempre.

---

## ✅ Motor de explicaciones + mejoras de UX/análisis (nuevo)

**Confirmado**: la segunda página de NiceGUI (Tracked Items) funciona en producción --
el usuario mandó captura real con las 40 tarjetas renderizando bien.

**`OpportunityExplainer` (nuevo domain service, `domain/services/opportunity_explainer.py`)**:
interpreta una `Opportunity` ya calculada y genera texto DATA-DRIVEN (nunca genérico) --
resumen, fortalezas/debilidades/factores neutros clasificados por umbral sobre
`score_breakdown`, interpretación en profundidad de liquidez (velocidad de
ejecución, slippage, aptitud para trading frecuente vs. posiciones largas) y de
riesgo (qué sub-componente pesa más), e insights que cruzan múltiples señales
(ROI alto + liquidez baja, order book fino, riesgo alto sin prima de ROI, etc.).
Separado a propósito de `OpportunityEngine` -- el engine decide el score, este
servicio solo interpreta un resultado ya cerrado (mismo principio de
Single Responsibility que separa los motores entre sí).

**Bug real encontrado testeando contra datos de producción**: ítems con spread
extremo (ej. 12150%) recibían la etiqueta "saludable" porque el componente
normalizado (log-scaled) trata cualquier spread grande como favorable para el
ROI -- corregido para matizar spreads >200% como señal de mercado fino, no como
algo genuinamente bueno.

**Conectado a la API**: `OpportunitySchema` ahora incluye `explanation` (generada
en `from_domain`, no en los routers). **Conectado a ambas UIs**: el panel
expandible "Ver análisis completo" (antes "Ver cálculo del score") ahora muestra
resumen + fortalezas + debilidades + interpretación de liquidez/riesgo + insights,
y DESPUÉS el desglose numérico de siempre -- visible por default sigue siendo
solo score/indicadores/badge corto, sin sobrecargar la tarjeta.

**Pulido visual (contenido, no rediseño completo)**: pill de score coloreado por
rango (verde/ámbar/rojo apagado, mismos umbrales que el Explainer) en Streamlit,
más sombra/profundidad sutil en hover de las tarjetas. Un rediseño visual de raíz
(tipografía completa, layout, iconografía extensiva) queda pendiente como tarea
aparte si se quiere -- lo que se hizo es una mejora real pero acotada, no la
reescritura visual completa que se pidió.

6 tests nuevos para el Explainer (incluida la regresión del bug de spread). 76
tests totales, todos pasando. Ambas UIs (Streamlit + las dos páginas de NiceGUI)
probadas de punta a punta con explicaciones reales contra datos de `trader.db`.

---

## ✅ Sesión post-rename: SDE import, ETA de sync, y tiempo estimado de venta

**SDE import fallando**: no era bug de código -- verificado que el algoritmo de
búsqueda de carpeta funciona bien. La carpeta `sde/` con los `.jsonl` de CCP nunca
existió en el proyecto que se mandó. Las categorías/grupos YA tenían nombres reales
de EVE (`Ship`, `Module`, `Charge`, etc. -- confirmado contra la DB), vienen de un
import anterior fuera de este mecanismo. Baja prioridad: el botón es para un
refresco secundario, no para los datos base.

**ETA de sincronización (`shared/eta.py`, nuevo)**: un usuario real esperó sin
feedback de tiempo durante una corrida larga y pensó que estaba roto -- después de
esperar, empezó a llenarse normal. `estimate_seconds_remaining()` extrapola el
ritmo observado (`done`/tiempo transcurrido) para estimar cuánto falta; nunca
inventa un número sin evidencia suficiente (devuelve `None` explícito). Enchufado
en `ApiServices.get_sync_status()` (`eta_seconds`/`eta_human` en el JSON), y
mostrado en el sidebar de Streamlit y en la página de Tracked Items de NiceGUI con
barra de progreso + aviso explícito de "no está colgado, solo está trabajando".

**Tiempo estimado de venta**: `ExitTimeEngine` ya calculaba esto (`estimated_hours`
sobre una posición de referencia de 100 unidades) pero se descartaba después de
convertirse en componente de score -- nunca llegaba como número crudo a ninguna UI.
Ahora `Opportunity.estimated_exit_hours` lo persiste, la API lo expone
(`estimated_exit_hours`/`estimated_exit_human`), y ambas UIs lo muestran --
dejando explícito que es sobre una cantidad de referencia fija, NO la posición real
del usuario (no hay tracking de portfolio todavía).

**Fix del `Money.currency` sin default (acordado la sesión anterior)**: ya no
asume ISK en silencio -- ahora es obligatorio pasarlo. Los 4 sitios reales que lo
necesitaban (todos en `SQLiteMarketRepository`, la implementación específica de
EVE) lo pasan explícito.

**Bug propio encontrado y arreglado en el camino**: al escribir `format_duration_hours`
en `shared/eta.py`, un `str_replace` mal apuntado se comió la línea `def` de
`format_eta`, dejando el código de esa función como parte de la anterior (código
muerto, nunca se ejecutaba). Se detectó recién al testear ambas funciones por
separado -- no antes, porque el archivo compilaba igual (era sintácticamente
válido, solo semánticamente incorrecto). Sirve de recordatorio: compilar no es
suficiente, hay que ejecutar/testear después de cada edit, no solo verificar sintaxis.

70 tests, todos pasando. Ambas UIs (Streamlit y NiceGUI, las tres páginas) probadas
de punta a punta contra datos reales de `trader.db` vía el patrón de "server falso"
de siempre. La página de Tracked Items de NiceGUI sigue sin confirmarse con
`nicegui` real -- el usuario todavía no la corrió.

---

## 🔴🔴 HALLAZGO MAYOR: "Quartermaster" analizaba La Forge ENTERA, no Jita (arreglado)

El usuario comparó manualmente contra el cliente real del juego (mercado
regional de The Forge) y notó un comprador en "Kisogo VII - AIR
Laboratories" (alcance "Región") apareciendo mezclado en el análisis de
"Jita" de una oportunidad totalmente distinta. Investigado y confirmado:

- `region_id=10000002` es **La Forge**, la región completa (decenas de
  sistemas, cientos de estaciones) -- NO es específico de Jita.
- Jita es UN sistema dentro de esa región. "Jita 4-4" (Jita IV - Moon 4
  - Caldari Navy Assembly Plant, `location_id=60003760`) es UNA estación
  dentro de ese sistema -- la que concentra la inmensa mayoría del
  trading real, y a la que cualquiera se refiere cuando dice "precio de
  Jita".
- `location_id` se guardaba en cada orden desde el principio (viene tal
  cual de ESI), pero **nunca se filtraba en ninguna query** -- todo
  "Quartermaster" analizaba, en realidad, la región de La Forge entera.

Medido contra datos reales: en una muestra chica (40 ítems trackeados),
13.6% de las órdenes NO estaban en Jita 4-4, y 5 de 40 type_ids
"activos" solo tenían book completo mezclando estaciones de otras
puntas del mapa, no en Jita 4-4 específicamente. Con el sync completo de
19.111 ítems del usuario, el impacto real es casi seguro mayor.

**Esto probablemente explica una porción real de los "order books
fantasma"** investigados en sesiones anteriores -- no todos eran
troll-orders aisladas, algunas eran órdenes reales pero de otra estación
del mapa, imposibles de ejecutar convenientemente por alguien operando
específicamente en Jita.

**Arreglado**: `SQLiteMarketRepository` (v1.4) ahora filtra por
`location_id = JITA_STATION_ID (60003760)` en TODAS las queries basadas
en `market_orders` (snapshot, order_counts, volúmenes remanentes,
`get_active_type_ids`, `get_market_snapshots_bulk`). El parámetro tiene
default a Jita pero es overrideable (no hardcodeado a fuego), por si
algún día se quiere analizar otra estación sin tocar código.

**Limitación real, no arreglable**: `get_daily_volume` (y por lo tanto
el componente de liquidez) sigue siendo REGIONAL -- ESI no tiene
endpoint de historial de volumen por estación, solo por región.
Documentado explícitamente en el docstring del método. El volumen diario
puede estar levemente sobreestimado respecto al real de Jita 4-4 si hay
trading significativo del mismo ítem en otras estaciones de la región --
es una limitación de la API de ESI, no algo que este proyecto pueda
evitar.

6 tests nuevos de regresión, probando explícitamente que una orden en
otra estación de la misma región no contamina ningún resultado. 64 tests
totales, todos pasando. Medido el impacto concreto antes/después contra
la DB real del usuario (con el sync completo del usuario, el impacto
real en producción todavía no se midió -- pendiente de que corra
`get_active_type_ids` de nuevo con el fix aplicado).

**⚠️ Importante para retomar**: como `import_full_region` sigue trayendo
TODA la región (no cambió, sigue siendo barato hacerlo así), NO hace
falta correr el Smart Auto-Seed de nuevo -- los datos crudos ya están
en la base, el fix es puramente en cómo se CONSULTAN. Alcanza con
reiniciar la API para tomar el código nuevo.

---

> Este documento existe para que el trabajo NO se pierda si se corta una
> sesión por límite de tokens. Si estás retomando esto en una sesión
> nueva: leé este archivo entero antes de tocar código, contiene el
> estado real de qué está hecho, qué está en curso, y qué falta, con el
> razonamiento detrás de cada decisión (no solo la lista de tareas).

Última actualización: Fase 1 de la migración a FastAPI (ver
`ARCHITECTURE_V3_FASTAPI_MIGRATION.md`) implementada.

---

## 🟡 FASE 2 EN CURSO -- Dashboard en NiceGUI (primera porción, sin validar todavía)

Confirmada la migración de Streamlit funcionando en producción (el
usuario mandó captura real: sync corriendo, tracked items con score).
Arrancó Fase 2 (NiceGUI) con:

- `api_client.py` movido de `streamlit_app/` a `presentation/` directo
  -- compartido entre Streamlit y NiceGUI, ninguna UI depende de la otra.
- `presentation/ui/` nuevo: `main.py` (entrypoint, puerto 8502),
  `theme.py` (mismo ámbar que Streamlit), `pages/dashboard.py` (única
  página por ahora, equivalente a `streamlit_app/app.py`).
- Usa `ui.aggrid` para la tabla -- es la razón original por la que se
  eligió NiceGUI sobre Reflex en el diseño de arquitectura.

**Nivel de confianza mucho más bajo que todo lo anterior**: `nicegui`
nunca se instaló en este entorno (sin red). Verificado con un stub
hecho a mano (cero errores de import/lógica Python, ejecutado contra
datos reales de `trader.db` a través del mismo patrón de "server falso"
que se usó para Streamlit) -- pero el renderizado real en un browser NO
se probó ni una vez. Esperar más iteración acá que en cualquier otra
parte del proyecto hasta la primera corrida real.

**Siguiente paso**: el usuario corre `pip install nicegui` +
`python src\presentation\ui\main.py` con la API ya corriendo, y reporta
el primer error real (si lo hay). Recién después de esa validación
tiene sentido construir la segunda página (Tracked Items) -- no
duplicar el patrón de riesgo antes de confirmar que el primero funciona.

### ✅ Dashboard de NiceGUI CONFIRMADO funcionando (capturas reales del usuario)

Tabla AG-Grid, tarjetas de detalle, badges de recomendación (colores
correctos), desglose de score -- todo renderizando bien con datos
reales de 40 ítems trackeados. Encontrado y arreglado de paso: las
etiquetas de los sliders del sidebar quedaban debajo del control en vez
de arriba (`ui.label(...)` escrito después del `ui.slider(...)` en vez
de antes) -- cosmético, no bloqueante, ya corregido.

### 🟡 Segunda página agregada: Tracked Items (sin validar todavía)

Con el Dashboard confirmado, se agregó `pages/tracked_items.py`
(equivalente a `streamlit_app/pages/02_tracked_items.py`): listar/quitar
trackeados (individual + todos), búsqueda + track individual, botón de
Smart Auto-Seed. Se extrajo `components.py` (tarjeta de oportunidad +
badge + nav header) para que Dashboard y Tracked Items compartan el
mismo renderizado, mismo criterio que `streamlit_app/components/opportunity_table.py`.

Aplica desde el arranque las dos correcciones ya aprendidas en el
Dashboard (`apply_theme()` dentro de la función de página, sin kwargs
de `ui.run` sin verificar) -- pero es la primera corrida real de ESTA
página específicamente, así que mismo nivel de incertidumbre que tenía
el Dashboard antes de su primera validación. Verificado hasta donde se
puede sin `nicegui` real: sintaxis válida, se arma sin excepciones
contra datos reales de `trader.db` vía el mismo patrón de "server
falso" que ya usamos varias veces.

**Nuevo en `main.py`**: navegación simple entre las dos páginas
(`render_nav_header` en `components.py`) -- NiceGUI no arma un menú de
páginas automático como Streamlit, se armó a mano.

### 🐛 Primer error real de NiceGUI: versión mucho más nueva de la esperada (arreglado, parcialmente)

El usuario instaló `nicegui==3.14.0` -- bastante más nueva que la
`>=1.4` contra la que se escribió el código de memoria (sin poder
verificar contra la real). Primer error real:

```
RuntimeError: ui.page cannot be used in NiceGUI scripts when UI is
defined in the global scope. To use multiple pages, either move all UI
into page functions or use ui.sub_pages.
```

Causa: `apply_theme()` (que llama `ui.dark_mode()`, `ui.colors()`,
`ui.add_head_html()`) se llamaba a nivel de MÓDULO en `main.py`, antes
de `ui.run()` -- NiceGUI 3.x exige que toda la UI viva dentro de
funciones de página cuando se usa `@ui.page`. Arreglado moviendo la
llamada a `apply_theme()` adentro de la función `dashboard()` (dentro
del `@ui.page("/")`). De paso, saqué `dark=True` de `ui.run()` -- no
tengo certeza de que sea un kwarg válido en esta versión, y ya se
maneja el modo oscuro con `ui.dark_mode().enable()` en el theme.

**Esto probablemente NO es el último ajuste** -- la brecha de versión
(1.4 asumida vs 3.14 real) es grande, puede haber más cambios de API
(nombres de props, `on_value_change`, formato de `ui.aggrid`, etc.) sin
descubrir todavía. Pedirle al usuario el próximo error tal cual salga
antes de asumir que ya cierra.

---

### 🐛 CRÍTICO: paths relativos a la DB rompían el arranque completo (arreglado)

El usuario corrió `uvicorn --app-dir C:\...\Quartermaster\src` parado en
`C:\Users\Toto` (sin `cd` a la carpeta del proyecto primero) y explotó en
el arranque: `sqlite3.OperationalError: unable to open database file`.
Causa raíz: 7 archivos distintos (`ApiServices`, `dependencies.py`,
`SmartAutoSeedJob`, `SyncStatusRepository`, `scheduler.py`, y los dos
repos SQLite) tenían `Path("database/trader.db")` como default -- una
ruta RELATIVA. `--app-dir` de uvicorn solo agrega esa carpeta a
`sys.path` para que los imports funcionen, NO cambia el cwd del
proceso -- así que la ruta relativa se resolvía contra
`C:\Users\Toto\database\trader.db`, que no existe.

Arreglado centralizando la resolución en `shared/paths.py`
(`get_project_root()` sube directorios desde la ubicación de ESE
archivo -- estable, no depende del cwd -- hasta encontrar `database/`),
y actualizando los 7 call sites para usar `DEFAULT_DB_PATH` de ahí en
vez de un literal relativo cada uno. Mismo patrón que ya se usaba para
`sys.path` en las páginas de Streamlit (`_find_project_root`), ahora
también del lado del server.

Verificado reproduciendo el bug exacto: corrí `ApiServices()` y todo el
ciclo de arranque de `main.py` (incluidos los hooks de `@app.on_event`)
parado en un cwd completamente distinto al proyecto -- antes del fix
hubiera reventado igual que en la traza real del usuario, después no.

---

## ✅✅✅ FASE 1 COMPLETA -- Streamlit migrado a cliente de la API

Streamlit (`app.py` y `pages/02_tracked_items.py`) ya NO importa nada de
`domain.*` / `application.*` / `infrastructure.repositories.*` /
`infrastructure.esi.*`. Todo pasa por `presentation/streamlit_app/api_client.py`
(HTTP puro, `requests`).

**Excepción documentada** (no un descuido): el explorador de Categoría→Grupo
del SDE de EVE (metadata local estática, nada que ver con ESI/mercado)
sigue usando `SQLiteTypeRepository` directo -- exponerlo detrás de la
API no aportaba nada al objetivo de esta fase.

**Simplificaciones reales habilitadas por la nueva arquitectura**:
- El botón "Panorama General" (muestra aleatoria + import manual
  orquestado desde Streamlit) se volvió obsoleto: el Smart Auto-Seed ya
  cubre TODA la región de una vez. Reemplazado por un acceso directo al
  mismo botón de sync.
- El flow de "Trackear + Importar" individual pasó de un `st.status()`
  de 3 pasos bloqueando Streamlit mientras esperaba a ESI, a un POST que
  responde 202 inmediato -- el import corre en background del lado del
  server. Streamlit nunca más espera bloqueado a ESI, en ningún punto.
- Dos botones separados de refresh ("order books" / "historial") en el
  sidebar del Dashboard se consolidaron en uno solo ("Sincronizar todo
  Jita"), porque el Smart Auto-Seed siempre hace ambas cosas juntas.

**Gap conocido, dejado fuera a propósito**: la tabla de "ítems excluidos
y por qué" que tenía el Dashboard viejo (`result.skipped`) no se
migró -- `OpportunitiesPageSchema` no expone esa lista todavía. Es un
diagnóstico secundario, no bloqueante; se puede agregar después si hace
falta.

**Nuevo**: `presentation/streamlit_app/api_client.py`, con manejo
explícito de `ApiConnectionError` (mensaje accionable -- "¿corriste
uvicorn?" -- en vez de un traceback crudo de `requests`). Ambas páginas
hacen `health_check()` al arrancar y muestran instrucciones claras si la
API no responde, con `st.stop()` limpio.

**Cambio de contrato en la API, de paso**: `GET /api/tracked-items` antes
devolvía `List[int]`, ahora devuelve `List[TrackedItemSchema]` (con
nombre resuelto) -- existía el schema pero nunca se usaba. Y
`OpportunitySchema` ahora incluye `confidence` (antes vivía en
`AnalysisResult`, se perdía en el camino hacia el JSON).

**Verificación**: 58 tests (9 nuevos de `api_client`, con sesión HTTP
falsa, sin red real). Ambas páginas Streamlit corridas de punta a punta
con un "server falso" que usa `ApiServices` real (la misma lógica que
usaría uvicorn) sobre datos reales de `trader.db` -- cubre: Dashboard en
modo tracked/discovery/tabla, API caída (mensaje claro + `st.stop()`),
Tracked Items en las dos vistas, búsqueda + track individual, y el
explorador de grupo con tracking masivo. Todo sin necesitar `fastapi`
instalado (que sigue sin estar disponible en este sandbox).

**Todavía no probado con uvicorn real** (mismo caveat de siempre): la
lógica está garantizada por los tests de arriba, pero el pegamento HTTP
real (¿el JSON que devuelve FastAPI matchea exactamente lo que
`api_client.py` espera parsear?) no se puede confirmar sin correr los
dos procesos de verdad. Este es el primer punto de la migración donde
de verdad hace falta correr ambos procesos juntos para la confirmación
final.

---


## ✅ Findings de revisión manual de datos de producción reales (post Fase 1 confirmada)

El usuario pegó el JSON completo de `/api/opportunities?scope=discovery` (top 50 de 5000 evaluados). Revisión honesta:

1. **Arreglado**: `_classify_recommendation` nunca chequeaba `roi_percent > 0`
   explícitamente en el gate de BUY. En la práctica `RiskEngine` ya
   penaliza ROI bajo/negativo lo suficiente (probado con caso límite
   teórico: techo ~56 con ROI negativo, nunca llega a 65) -- pero era
   protección incidental, no garantizada. Ahora `roi_percent > 0` es
   requisito explícito. Test de regresión con caso límite adversarial.

1. **Arreglado**: `get_active_type_ids(limit=5000)` subido a `limit=30000`
   (default), expuesto como query param `discovery_limit` en
   `GET /api/opportunities` (bounded 1-50000). Medido a escala real
   (19.111 ítems sintéticos): 1.6s de punta a punta, de sobra para un
   request HTTP. De yapa: encontré que `app.py` (Streamlit, todavía sin
   migrar a la API) tenía el MISMO límite duplicado en SQL inline, pero
   en 300 -- reemplazado por una llamada al mismo método formal
   (`get_active_type_ids`), unificando el límite entre ambas capas.

3. **Arreglado (Opción B, elegida por el usuario)**: `exclude_caution`
   como query param opt-in en `GET /api/opportunities` -- saca del
   ranking cualquier ítem con `recommendation.is_caution` sin tocar el
   score (sigue siendo el mismo número auditable de siempre). De paso,
   mientras implementaba esto encontré y arreglé un bug relacionado: el
   `max_results * 3` que se usaba como margen para reordenar por un
   campo distinto a `score` era un parche heurístico, no una garantía
   -- con `exclude_caution` (o cualquier filtro que recorte bastante el
   pool) podía devolver menos de `max_results` igual. Ahora se filtra y
   ordena sobre el pool COMPLETO de evaluados (`ranked_all`), sin
   costo extra real (el use case ya calculaba todo, el corte era solo
   un slice). Tests de regresión para ambos (filtro + fix del margen).

---

## ✅ Fase 1 (FastAPI + background jobs) — IMPLEMENTADA, verificación parcial

**Importante para quien retome esto**: el entorno donde se escribió esta
fase NO tenía `fastapi`, `pydantic`, `uvicorn` ni `apscheduler`
instalados (sandbox sin red). Se validó todo lo que se pudo sin esas
libs:
- Toda la lógica real vive en `presentation/api/services.py`
  (`ApiServices`), que NO importa fastapi/pydantic -- 100% testeada con
  datos reales y con tests permanentes (`tests/presentation/api/`).
- Los routers/schemas/main.py SÍ requieren fastapi/pydantic. Se
  verificaron con stubs mínimos hechos a mano (imports limpios, rutas
  registradas correctamente, handlers llamados directamente con
  `ApiServices` real y devolviendo lo esperado) -- pero NO se corrieron
  con la librería real, ni se probó un servidor uvicorn de verdad.
- **Primer paso al retomar**: `pip install -e ".[api]"` y correr
  `uvicorn presentation.api.main:app --reload --app-dir src` de
  verdad, pegar cualquier error acá.

Lo que se construyó:
- `infrastructure/jobs/sync_status_repository.py` -- progreso de sync
  persistido (`sync_status`) + estado global (`system_state`,
  key-value, hoy solo `last_full_seed_at`). 100% testeado.
- `infrastructure/esi/market_orders_importer.py` ->
  `import_full_region()`: fetch paginado de `/markets/{region}/orders/`
  SIN `type_id`, un solo `executemany` a la DB. 100% testeado con
  cliente ESI fake (sin red).
- `infrastructure/jobs/seed_job.py` -> `SmartAutoSeedJob`: orquesta
  order book completo + historial acotado a type_ids con actividad
  real. 100% testeado (4 tests, incluyendo fallos parciales de
  historial que no abortan la corrida entera).
- `infrastructure/jobs/scheduler.py`: APScheduler, 2 jobs periódicos
  (orders cada 20 min, seed completo cada 12 hs). NO Celery/Redis --
  decisión deliberada, ver `ARCHITECTURE_V3_FASTAPI_MIGRATION.md` §4.
  NO testeado (requiere apscheduler).
- `presentation/api/`: FastAPI completo -- `main.py` (con auto-seed en
  el primer arranque + wiring del scheduler), 4 routers
  (opportunities/tracked-items/search/sync), schemas Pydantic v2. Lógica
  verificada vía `services.py`; routing/serialización NO verificados
  con la librería real.
- `database/schema.sql` + `scripts/migrate_v3_add_sync_tables.py`:
  tablas nuevas (`sync_status`, `system_state`) + WAL mode. Migración
  NO destructiva, testeada contra una copia de la DB real (los 40
  ítems trackeados sobrevivieron intactos).
- `pyproject.toml`: grupo `[project.optional-dependencies] api`.

**Streamlit NO fue tocado en esta fase.** Sigue funcionando exactamente
igual que antes, llamando a los use cases directo (no a la API nueva).
Migrar Streamlit para que consuma la API es el siguiente paso lógico,
pero se dejó pendiente a propósito hasta confirmar que la API arranca
y responde de verdad en tu máquina -- no tenía sentido migrar el
cliente antes de confirmar que el servidor funciona.

---

## ✅✅ FASE 1 CONFIRMADA FUNCIONANDO DE PUNTA A PUNTA (con datos reales, no solo tests)

El usuario corrió todo el flujo real: Smart Auto-Seed completo (415.666
órdenes, 19.111 ítems activos, historial 18.831/19.111), y
`GET /api/opportunities?scope=discovery` devolviendo oportunidades reales
de ESE universo completo -- no una muestra de 400, no una watchlist a
mano. Esto es lo que el usuario pidió explícitamente hace varios
mensajes ("que el sistema busque e indexe todas las oportunidades
buenas... de la totalidad del universo").

**Nota para quien retome esto**: lo que en un momento pareció un
"colgado" (`Invoke-RestMethod` sin volver al prompt) NO era un bug --
era PowerShell truncando la vista de tabla para objetos anidados
(comportamiento default de `Format-Table`). El fix de N+1 (bulk
queries) sigue siendo válido y medido (23x más rápido con datos
sintéticos), pero no se pudo confirmar que fuera la causa de la
percepción de "colgado" -- probablemente nunca hubo tal cuelgue.
Anotado para no sobre-explicar esto si se vuelve a preguntar.

**Siguiente paso pendiente de decidir con el usuario** (no asumir cuál
prefiere): migrar Streamlit para que consuma esta API en vez de llamar
a los use cases directo (cierra Fase 1 del todo), o saltar directo a
Fase 2 (UI en NiceGUI), o quedarse usando la API vía `/docs` (Swagger)
por ahora sin tocar más nada. Preguntar antes de arrancar cualquiera
de las tres.

## 🟢 Primera corrida real en Windows (post Fase 1) — bugs encontrados y arreglados

El usuario corrió los comandos de verdad en su máquina (Windows,
PowerShell/cmd). Encontró 4 problemas, todos de packaging/shell, NINGUNO
en la lógica de negocio (que sigue validada por los 40 tests):

1. **`pip install -e ".[api]"` fallaba** -- `pyproject.toml` no tenía
   `[tool.hatch.build.targets.wheel] packages = [...]`, y hatchling no
   puede auto-detectar qué empaquetar cuando el proyecto no tiene un
   único directorio top-level que coincida con el nombre normalizado.
   Arreglado declarando los 5 paquetes reales
   (domain/application/infrastructure/presentation/shared). PERO además
   se cambió la recomendación: no hace falta editable install para nada
   de esto, `pip install fastapi "uvicorn[standard]" apscheduler` directo
   alcanza y es más robusto.
2. **`PYTHONPATH=src comando`** es sintaxis de bash, no de Windows. Y de
   yapa, `migrate_v3_add_sync_tables.py` no necesita `PYTHONPATH` en
   absoluto (es sqlite3 puro). Instrucción simplificada en el README.
3. **`uvicorn` command not found** -- consecuencia de que el install
   falló antes. Además se cambió a `python -m uvicorn` en vez del
   comando suelto, para no depender de que el PATH tenga la carpeta
   Scripts de una instalación `--user`.
4. **`curl -X POST` en PowerShell** -- `curl` ahí es alias de
   `Invoke-WebRequest`, no soporta `-X`. README actualizado con
   `Invoke-WebRequest -Method POST` y la alternativa `curl.exe` (el
   binario real, distinto del alias).

**Todavía no confirmado**: si el Smart Auto-Seed termina sin errores
contra ESI real (fase "orders" confirmada corriendo; fase "history",
que es la más lenta, todavía no reportada).

### 🐛 Bug de concurrencia encontrado en la corrida real (arreglado)

El usuario disparó `POST /api/sync/seed` a mano justo después de
arrancar el server. El auto-seed del startup YA lo había disparado solo
(primera vez, `needs_initial_seed()=True`) -- sin guard, esto lanzaba
DOS `SmartAutoSeedJob.run()` concurrentes sobre la misma región. No
corrompía datos (SQLite en WAL serializa escrituras) pero duplicaba
requests contra ESI y hacía parpadear `sync_status` con progreso de dos
corridas entreveradas. Arreglado con un `threading.Lock` en
`ApiServices` (`_seed_lock`): `run_seed_job()` levanta `RuntimeError` si
ya hay una corrida en curso, y el router (`POST /api/sync/seed`) chequea
`is_seed_running()` ANTES de encolar, devolviendo `status:
"already_running"` en vez de fallar en silencio dentro del
BackgroundTask. Testeado con threads reales reproduciendo el escenario
exacto (no solo en teoría).

Si el usuario ya tenía el server corriendo con la versión sin este fix,
necesita reiniciarlo para tomarlo (`Ctrl+C` + volver a correr uvicorn).

### 🐛 `sync_status` se quedaba congelado durante el fetch de órdenes (arreglado)

El usuario pegó varias corridas de `GET /api/sync/status` seguidas, todas
con el mismo `updated_at` exacto -- sin forma de saber si seguía
trabajando o se había colgado. Causa: `ESIClient.get()` no tenía ningún
callback de progreso por página, así que durante el fetch completo de
la región (potencialmente cientos de páginas para Jita/The Forge), nada
se reportaba hasta que TODO terminaba. Arreglado con un parámetro
opcional `on_page(page, total_pages, items_so_far)` en `ESIClient.get()`,
conectado en `import_full_region()` y `SmartAutoSeedJob`/scheduler --
ahora `sync_status.detail` muestra "Página X/Y (Z órdenes)" actualizado
en cada página. Testeado con paginación simulada real (5 tests nuevos:
3 de `ESIClient` con `on_page`, 1 de `SmartAutoSeedJob` verificando que
`sync_status` recibe múltiples updates crecientes durante la fase
"orders", no uno solo).

Mismo caveat que el fix anterior: si el usuario ya tenía el server
corriendo, necesita reiniciarlo para ver el progreso real en la
próxima corrida.

### 🐛 N+1 de conexiones SQLite en `/api/opportunities` a escala real (arreglado)

Con el Smart Auto-Seed completo corriendo de verdad (19.111 ítems
activos, resultado real del usuario), `DetectOpportunitiesUseCase.execute()`
abría ~5-6 conexiones SQLite POR ÍTEM (nombre, snapshot, daily_volume,
order_counts, total_sell/buy_volume_remain) -- a la escala de 40 ítems
trackeados a mano esto era imperceptible (probado: 0.26s), pero a escala
real son decenas de miles de conexiones para un solo request HTTP.
Arreglado con `SQLiteMarketRepository.get_market_snapshots_bulk()` y
`SQLiteTypeRepository.get_names_bulk()`: un puñado de queries `GROUP BY
type_id` sobre TODA la región de una vez, el use case filtra en memoria.
Medido con datos sintéticos a escala real (8.000 ítems): 0.61s con el
fix, vs. ~14s extrapolado del patrón viejo en este sandbox Linux/SSD --
en Windows con SQLite+WAL la diferencia real probablemente sea mayor,
no menor. Mantiene fallback por ítem para cualquier implementación de
`MarketRepository`/`TypeRepository` que no soporte los métodos bulk
(compatibilidad con el Port abstracto). Los 46 tests existentes siguen
pasando sin cambios -- el refactor no tocó el contrato externo del use
case, solo cómo obtiene los datos.

**Todavía no confirmado si esto era la causa real de lo que vio el
usuario** -- no llegó a pegar el output de su corrida de
`/api/opportunities?scope=discovery`. Es el próximo dato que hace
falta.




1. `pip install -e ".[api]"` en tu máquina (con red real).
2. `PYTHONPATH=src python scripts/migrate_v3_add_sync_tables.py` (si
   todavía no lo corriste sobre tu `trader.db` real).
3. `uvicorn presentation.api.main:app --reload --app-dir src`
4. Pegar acá cualquier traceback que salga -- es información real de
   una librería que en la sesión de desarrollo no estaba disponible,
   así que es la primera vez que este código se ejecuta de verdad.
5. Si arranca limpio: probar `GET /docs` (Swagger autogenerado),
   `POST /api/sync/seed`, `GET /api/sync/status` en loop para ver el
   progreso, y `GET /api/opportunities?scope=discovery` una vez que
   termine.
6. Recién ahí: migrar `app.py`/`02_tracked_items.py` de Streamlit para
   que consuman la API en vez de llamar a los use cases directo (Fase
   1 completa, tal como está descripta en
   `ARCHITECTURE_V3_FASTAPI_MIGRATION.md` §6).

---

## ✅ Ya resuelto (sesiones anteriores, no repetir)

- Bug de saturación del scoring (ROI/spread log_v2).
- Bug de "order book fantasma" en LiquidityEngine (media geométrica).
- Badge de recomendación movido de la UI al dominio (`OpportunityEngine`).
- Bug de escala en `order_pressure` de CompetitionEngine (v1.1) + eliminación
  de `price_spread_percent` por señal invertida y redundante (v1.2).
- Sesgo de muestreo alfabético en bulk import (`ORDER BY name` → `RANDOM()`)
  -- OBSOLETO en la práctica desde Fase 1: `import_full_region()` ya no
  necesita muestrear nada, cubre la región completa.
- Vista de tabla ordenable (Dashboard + Tracked Items).
- `CAUTION_THIN_ORDER_BOOK`: gate que exige mínimo de órdenes por lado
  (`MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST = 2`) para confiar en un precio.
- Todas las categorías de recomendación (incluida NEUTRAL) pintan un badge
  explícito, nunca quedan sin mensaje.
- Tema visual oscuro ámbar + ícono 📡 (evoca la paleta de EVE).
- Bug de "borra de a tandas" (`untrack_all`/`untrack_many` atómicos).
- Bug de "Buscar y Agregar" en blanco (st.tabs → st.radio condicional).
- Botón "Trackear + Importar" colgado (st.status + guard de doble-click).

---

## 🟡 Discutido, análisis ya hecho, pendiente de implementar

### Fase 2 y 3 de la migración (UI en NiceGUI, apagar Streamlit)
Ver `ARCHITECTURE_V3_FASTAPI_MIGRATION.md` §6. No arrancar sin haber
completado el paso "Siguiente paso concreto" de arriba primero.

### Diversidad de recomendaciones -- calibración pendiente de confirmar
El usuario notó que la mayoría de los ejemplos que vio caían en
"liquidez baja" o "rango normal". Preguntar si quiere subir
`MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST` de 2 a un número más conservador,
y si quiere mostrar múltiples señales de precaución por ítem en vez de
una sola categoría mutuamente excluyente.

---

## Cómo retomar si se corta la sesión

1. Leer este archivo completo primero.
2. Correr los tests (`pytest`, o el runner manual si no hay pytest
   instalado en el sandbox) para confirmar que el estado actual sigue
   sano antes de tocar nada nuevo.
3. Si el pendiente es Fase 1 de FastAPI: seguir el "Siguiente paso
   concreto" de arriba, no re-diseñar nada, ya está todo decidido.
4. Para cualquier otra cosa: preguntarle al usuario qué prioriza.

