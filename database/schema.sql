PRAGMA foreign_keys = ON;

-- WAL mode: permite lecturas concurrentes mientras hay una escritura en
-- curso (importante ahora que la API puede estar sirviendo requests al
-- mismo tiempo que un job en background escribe order books/historial).
-- Es un flag persistido en el archivo de la DB, no hace falta re-setearlo
-- en cada conexión una vez aplicado.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS item_types (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    group_id INTEGER,
    category_id INTEGER,
    market_group_id INTEGER,
    volume REAL,
    base_price REAL,
    published INTEGER
);

CREATE INDEX IF NOT EXISTS idx_item_name
ON item_types(name);

CREATE INDEX IF NOT EXISTS idx_group
ON item_types(group_id);


-- Catálogo de regiones de ESI (/universe/regions/). Se puebla una sola vez,
-- cambia casi nunca. Es la tabla que permite comparar "todas las regiones"
-- sin hardcodear ids sueltos en el código.
CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);


-- Serie diaria de precio/volumen por producto y por región.
-- Fuente: GET /markets/{region_id}/history/
-- Se acumula con el tiempo (a diferencia de market_orders), por eso la
-- clave primaria incluye la fecha: cada día es una fila nueva, no se pisa.
CREATE TABLE IF NOT EXISTS market_history (
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    average REAL,
    highest REAL,
    lowest REAL,
    volume INTEGER,
    order_count INTEGER,
    PRIMARY KEY (region_id, type_id, date),
    FOREIGN KEY (region_id) REFERENCES regions(id),
    FOREIGN KEY (type_id) REFERENCES item_types(id)
);

CREATE INDEX IF NOT EXISTS idx_history_type
ON market_history(type_id);

CREATE INDEX IF NOT EXISTS idx_history_region
ON market_history(region_id);


-- Foto del order book activo por región.
-- Fuente: GET /markets/{region_id}/orders/
-- A DIFERENCIA de market_history, esto NO es una serie histórica: una orden
-- que ya no existe en ESI (cancelada o completada) tiene que desaparecer de
-- acá. El importador debe borrar las órdenes viejas de una región antes de
-- insertar el snapshot nuevo (o hacer DELETE WHERE region_id=? antes del
-- INSERT), si no la tabla va a acumular basura de órdenes que ya no están
-- vigentes y el cálculo de competencia/liquidez va a quedar mal.
CREATE TABLE IF NOT EXISTS market_orders (
    order_id INTEGER PRIMARY KEY,
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    is_buy_order INTEGER NOT NULL,
    price REAL NOT NULL,
    volume_remain INTEGER NOT NULL,
    volume_total INTEGER NOT NULL,
    min_volume INTEGER,
    duration INTEGER,
    issued TEXT,
    location_id INTEGER,
    order_range TEXT,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES regions(id),
    FOREIGN KEY (type_id) REFERENCES item_types(id)
);

CREATE INDEX IF NOT EXISTS idx_orders_type_region
ON market_orders(type_id, region_id);

CREATE INDEX IF NOT EXISTS idx_orders_region
ON market_orders(region_id);


-- Watchlist: productos que de verdad queremos trackear en detalle.
-- Con ~50k types publicados x 113 regiones, importar TODO por defecto no es
-- viable ni tiene sentido (la mayoría de los items no se comercian nunca).
-- Esta tabla es la que decide el alcance real de lo que se importa: el
-- importador de history/orders debe iterar sobre tracked_types, no sobre
-- todo item_types. Arranca vacía a propósito -- se puebla a mano o desde
-- repo.search() cuando encuentres algo que quieras seguir.
-- ============================================================
-- MULTI-TENANCY (v1.0 SaaS): usuarios autenticados vía EVE SSO
-- ============================================================
-- Cada usuario se identifica por su personaje de EVE (login vía SSO
-- oficial de CCP, OAuth2). NO guardamos contraseñas -- la autenticación
-- real la hace el servidor de EVE, acá solo persistimos la identidad
-- y los tokens que EVE nos entrega para actuar en nombre del usuario
-- si en el futuro hace falta (hoy: solo para identificarlo).
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eve_character_id INTEGER NOT NULL UNIQUE,
    eve_character_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_eve_character_id
ON users(eve_character_id);


-- Tokens OAuth2 de EVE SSO, CIFRADOS en reposo (ver
-- infrastructure/security/token_encryption.py -- nunca texto plano).
-- Uno por usuario: si vuelve a loguearse, se pisa (no se acumulan
-- tokens viejos sin usar dando vueltas en la base).
CREATE TABLE IF NOT EXISTS oauth_tokens (
    user_id INTEGER PRIMARY KEY,
    access_token_encrypted BLOB NOT NULL,
    refresh_token_encrypted BLOB NOT NULL,
    expires_at TEXT NOT NULL,
    scopes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);


-- Watchlist personal -- ahora con dueño. type_id ya NO es la clave
-- primaria por sí solo (antes solo existía UN usuario implícito para
-- todo el sistema); ahora la clave es (user_id, type_id), porque dos
-- usuarios distintos pueden trackear el mismo ítem sin pisarse.
-- v3 (modularización multi-hub): un mismo type_id (ej. "Tritanium") se
-- comercia en TODOS los hubs simultáneamente con precios distintos --
-- trackearlo sin especificar hub era ambiguo. region_id ahora forma
-- parte de la clave: (user_id, type_id, region_id), no (user_id, type_id).
CREATE TABLE IF NOT EXISTS tracked_types (
    user_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (user_id, type_id, region_id),
    FOREIGN KEY (type_id) REFERENCES item_types(id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracked_types_user
ON tracked_types(user_id);


-- ============================================================
-- TABLAS DEL SDE DE EVE (categorías y grupos reales)
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    published INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    published INTEGER DEFAULT 1,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE INDEX IF NOT EXISTS idx_groups_category ON groups(category_id);
CREATE INDEX IF NOT EXISTS idx_groups_name ON groups(name);


-- Snapshot diario AGREGADO de competencia/liquidez del order book, por
-- región y producto. No es un dump de cada orden en cada fecha -- guardar
-- cada order_id de cada día multiplicaría el tamaño de la base sin agregar
-- información útil para Market DNA (no nos importa la orden #12345 en sí,
-- nos importa "cuánta competencia había ese día"). Por eso esta tabla
-- resume lo que market_orders (la foto del momento) tiene en un instante
-- dado, y se acumula día a día para poder ver la evolución.
CREATE TABLE IF NOT EXISTS market_order_snapshots (
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    buy_order_count INTEGER NOT NULL,
    sell_order_count INTEGER NOT NULL,
    best_buy_price REAL,
    best_sell_price REAL,
    total_volume_remain INTEGER,
    PRIMARY KEY (region_id, type_id, snapshot_date),
    FOREIGN KEY (region_id) REFERENCES regions(id),
    FOREIGN KEY (type_id) REFERENCES item_types(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_type
ON market_order_snapshots(type_id);


-- ============================================================
-- FASE 1 (migración a FastAPI + background jobs): estado de sync
-- ============================================================
-- Ver docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md

-- Progreso del job de sync en curso, para que la API pueda reportarlo
-- sin bloquear (polling a GET /api/sync/status). Una sola fila viva por
-- región -- se pisa (UPSERT), no se acumula historial acá.
CREATE TABLE IF NOT EXISTS sync_status (
    region_id INTEGER PRIMARY KEY,
    phase TEXT NOT NULL,           -- 'idle' | 'orders' | 'history' | 'completed' | 'error'
    detail TEXT,
    total INTEGER,
    done INTEGER,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(id)
);

-- Estado global del sistema, key-value genérico y extensible (evita tener
-- que migrar el schema cada vez que se necesita guardar un flag nuevo).
-- Hoy solo se usa 'last_full_seed_at' -- si es NULL/ausente, el Smart
-- Auto-Seed se dispara solo al arrancar (ver infrastructure/jobs/seed_job.py).
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
