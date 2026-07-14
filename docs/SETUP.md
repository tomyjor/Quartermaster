# Setup completo

## 1. Variables de entorno

**Automático (recomendado)**: corré
```bash
python scripts/setup_env.py
```
Crea `.env` si no existe, y genera + escribe directo las 4 claves que
se pueden generar solas (`QUARTERMASTER_SESSION_SECRET`,
`QUARTERMASTER_ENCRYPTION_KEY`, `QUARTERMASTER_ADMIN_KEY`,
`QUARTERMASTER_UI_STORAGE_SECRET`) -- cero copy-paste manual. El `.bat`
de Windows ya lo corre solo antes de arrancar todo, así que si usás
ese launcher no hace falta correrlo aparte.

Ninguna de estas variables es obligatoria para correr en modo Discovery
sin login -- solo hacen falta si querés habilitar el login con EVE.

**Manual (si preferís hacerlo a mano)**: copiá `.env.example` a `.env`
y completá:

| Variable | Para qué | Cómo generarla |
|---|---|---|
| `QUARTERMASTER_SESSION_SECRET` | Firma los tokens de sesión propios | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `QUARTERMASTER_ENCRYPTION_KEY` | Cifra los tokens de EVE SSO en la base | `python -c "from infrastructure.security.token_encryption import generate_key; print(generate_key())"` |
| `EVE_SSO_CLIENT_ID` | Habilita el login con EVE | Ver paso 2 abajo |
| `EVE_SSO_CLIENT_SECRET` | Habilita el login con EVE | Ver paso 2 abajo |
| `QUARTERMASTER_ADMIN_KEY` | Protege `/api/admin/stats` | Cualquier string secreto, elegido a mano |
| `QUARTERMASTER_UI_STORAGE_SECRET` | Persistencia de sesión en NiceGUI | Cualquier string secreto, elegido a mano |

⚠️ Si copiás un valor generado a mano, prestá atención a no cortar el
`=` final del base64 (pasa fácil con doble-click para copiar, que no
toma signos de puntuación como parte de la "palabra") -- es la causa
real de un bug que costó bastante diagnosticar. El script automático
de arriba no tiene este problema porque nunca pasa por copy-paste.

En cualquiera de los dos casos, `EVE_SSO_CLIENT_ID`/`EVE_SSO_CLIENT_SECRET`
siguen necesitando completarse a mano -- no hay forma de generarlos
localmente, salen de developers.eveonline.com (paso 2).

## 2. Registrar una aplicación en EVE SSO (solo si querés login)

1. Entrá a [developers.eveonline.com](https://developers.eveonline.com) con
   tu cuenta de EVE.
2. Creá una aplicación nueva ("Create New Application").
3. Nombre: el que quieras (ej. "Quartermaster local").
4. **Connection Type**: elegí "Authentication Only" -- no hace falta pedir
   ningún scope de ESI, el login solo usa la identidad del personaje.
5. **Callback URL**: tiene que coincidir EXACTO con lo que espera la API.
   Por default, corriendo todo en tu máquina:
   ```
   http://127.0.0.1:8000/api/auth/callback
   ```
6. Guardá. CCP te va a mostrar un `Client ID` y un `Secret Key` -- esos van
   en `EVE_SSO_CLIENT_ID` / `EVE_SSO_CLIENT_SECRET` en tu `.env`.

⚠️ Si en algún momento corrés la API en otro host o puerto, la Callback URL
en developers.eveonline.com tiene que actualizarse para que coincida --
CCP la valida estricto, no acepta coincidencias parciales.

## 3. Catálogo de ítems (OBLIGATORIO en una instalación nueva)

Un clon nuevo del proyecto arranca con `item_types` vacía -- el Smart
Auto-Seed trae order books y volumen, pero NO nombres de ítems. Sin este
paso, todo se ve como "Type-1234" en vez de "Tritanium".

1. Bajate el SDE (Static Data Export) de CCP en formato JSONL desde
   [developers.eveonline.com/docs/services/sde](https://developers.eveonline.com/docs/services/sde/).
2. Poné los archivos (`types.jsonl` o `invTypes.jsonl`, `categories.jsonl`,
   `groups.jsonl`) en una carpeta `sde/` dentro del proyecto.
3. Corré, en este orden:
   ```bash
   PYTHONPATH=src python scripts/setup_database.py
   python scripts/import_sde_categories_groups.py
   python scripts/import_sde_types.py
   ```

Esto es un paso único -- el catálogo de ítems cambia poco (solo cuando CCP
agrega contenido nuevo al juego), no hace falta repetirlo salvo que quieras
actualizar a un SDE más reciente.

## 4. Primera sincronización de mercado

Con la API corriendo, andá a cualquiera de las dos UIs y apretá
"Sincronizar todo Jita" en la barra lateral. La primera vez trae el order
book completo de la región (puede tardar varios minutos) y después el
historial de volumen de los ítems con actividad real. Es normal ver pocos
u ningún resultado en Discovery mientras esto corre -- no está colgado.

## 5. Verificar que todo esté bien

```bash
pytest
```

Deberías ver ~130 tests pasando. Si algo falla, es la primera señal de que
falta una dependencia o algo quedó mal configurado.
