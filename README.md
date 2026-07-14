# Quartermaster

**Inteligencia de mercado para trading en EVE Online (Jita).**

Quartermaster analiza el order book de Jita en tiempo real y calcula, para
cada ítem, un score transparente de 0 a 100 basado en ROI, liquidez, riesgo,
competencia y tiempo estimado de salida — con una explicación en lenguaje
natural de por qué cada ítem sacó ese score, no solo el número.

No es un visor de precios. Es una herramienta de decisión.

---

## Qué hace

- **Sincroniza el order book completo de Jita** de una sola vez (Smart
  Auto-Seed) — no hace falta trackear ítems uno por uno a mano.
- **Score explicable**: cada componente del cálculo es auditable — la suma
  de las contribuciones siempre coincide con el score final.
- **Explicaciones en lenguaje natural**, construidas con los números reales
  de cada ítem, no plantillas genéricas.
- **Watchlist personal** por usuario, con login vía EVE SSO (opcional — sin
  login, igual podés ver todo el mercado en modo Discovery).
- **Dos interfaces**: Streamlit (estable) y NiceGUI (en desarrollo activo,
  mejor soporte para tablas grandes).

## Qué NO hace (todavía)

- No lee tu wallet ni tus órdenes personales de EVE — solo usa datos
  públicos de mercado (ESI).
- No ejecuta operaciones por vos. Las decisiones son tuyas.
- El "tiempo estimado de venta" es sobre una posición de referencia
  (100 unidades), no tu posición real — todavía no hay tracking de
  portfolio.

## Requisitos

- Python 3.11+
- Una cuenta de EVE Online (para el login opcional — necesitás registrar
  una aplicación en [developers.eveonline.com](https://developers.eveonline.com)
  si querés usar login, ver `docs/SETUP.md`)

## Instalación rápida

```bash
git clone <este-repo>
cd Quartermaster
pip install -e ".[api]"
```

## Configuración

Copiá `.env.example` a `.env` y completá las variables (ver el archivo para
instrucciones de cómo generar cada una). Como mínimo, para correr sin login,
no necesitás tocar nada — el login es opcional.

## Cómo correrlo

Tres procesos, tres terminales:

```bash
# Terminal 1 — API (siempre primero)
python -m uvicorn presentation.api.main:app --reload --app-dir src

# Terminal 2 — Streamlit
python -m streamlit run src/presentation/streamlit_app/app.py

# Terminal 3 (opcional) — NiceGUI
python src/presentation/ui/main.py
```

La primera vez, sincronizá el mercado desde el botón "Sincronizar todo
Jita" en la barra lateral — tarda unos minutos, es normal.

## Arquitectura

Clean Architecture + DDD. Cinco motores de dominio puros (ROI, Liquidez,
Riesgo, Competencia, Tiempo de Salida) componen un score único y
explicable. Ver `docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md` y
`docs/ARCHITECTURE_V4_GENERIC_PLATFORM.md` para el detalle de diseño.

```
src/
├── domain/          ← lógica de negocio pura, sin dependencias externas
├── application/      ← casos de uso
├── infrastructure/   ← ESI, SQLite, auth, jobs
├── presentation/      ← API (FastAPI) + dos clientes (Streamlit, NiceGUI)
└── shared/            ← utilidades transversales
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Licencia

Ver `LICENSE`. En resumen: podés correrlo, modificarlo y usarlo para vos o
tu comunidad libremente. No podés revenderlo ni redistribuirlo como
producto comercial propio sin permiso.

## Estado del proyecto

Activo, en desarrollo. Ver `docs/ROADMAP_Y_PENDIENTES.md` para el historial
completo de decisiones y qué falta. Si encontrás un bug o tenés una idea,
abrí un issue.
