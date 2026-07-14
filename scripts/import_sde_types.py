#!/usr/bin/env python3
"""
Importa el catálogo COMPLETO de ítems (invTypes) del SDE de EVE Online.

Sin esto, un clon nuevo del proyecto tiene `item_types` vacía -- nada
tiene nombre real (Discovery, búsqueda, watchlist muestran "Type-1234"
en vez de "Tritanium"). El Smart Auto-Seed NO llena esta tabla -- solo
trae order books y volumen, asume que el catálogo de nombres ya existe.
Este script es el que falta para que alguien clonando el proyecto desde
cero pueda arrancar con un sistema realmente usable, no solo con
tablas vacías.

Dónde conseguir el archivo: CCP publica el SDE (Static Data Export) en
https://developers.eveonline.com/docs/services/sde/ -- bajate el export
en formato JSONL, buscá el archivo de tipos (`types.jsonl` o
`invTypes.jsonl` según la versión del export).

Uso:
    python scripts/import_sde_types.py /ruta/a/carpeta_con_los_jsonl

Mismo patrón que scripts/import_sde_categories_groups.py -- si no se
pasa ruta, busca en la carpeta `sde/` del proyecto.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def find_jsonl_file(base_dir: Path, possible_names: list[str]) -> Optional[Path]:
    for name in possible_names:
        p = base_dir / name
        if p.exists():
            return p
    for name in possible_names:
        matches = list(base_dir.rglob(name))
        if matches:
            return matches[0]
    return None


def import_types(conn: sqlite3.Connection, jsonl_path: Path) -> int:
    print(f"Importando ítems desde: {jsonl_path}")
    count = 0
    skipped = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                type_id = obj.get("_key") or obj.get("id") or obj.get("typeID")
                name = obj.get("name", {}).get("en") if isinstance(obj.get("name"), dict) else obj.get("name")
                group_id = obj.get("groupID") or obj.get("group_id")
                market_group_id = obj.get("marketGroupID") or obj.get("market_group_id")
                volume = obj.get("volume")
                base_price = obj.get("basePrice") or obj.get("base_price")
                published = obj.get("published", 1)

                if not type_id or not name:
                    skipped += 1
                    continue

                # category_id no viene directo en invTypes -- se resuelve
                # vía groups (ya importado por import_sde_categories_groups.py)
                # en el momento de leer, no acá -- evita depender del
                # orden en que se corran los dos scripts.
                conn.execute(
                    """INSERT OR REPLACE INTO item_types
                       (id, name, group_id, market_group_id, volume, base_price, published)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (int(type_id), str(name), group_id, market_group_id, volume, base_price, int(published)),
                )
                count += 1
            except Exception as e:
                print(f"  Error en línea: {e}")
                skipped += 1

    conn.commit()
    print(f"  → {count} ítems importados/actualizados ({skipped} líneas sin datos suficientes, salteadas).")
    return count


def _backfill_category_id(conn: sqlite3.Connection) -> None:
    """
    category_id no viene en invTypes -- se deriva de `groups.category_id`
    (JOIN), si la tabla `groups` ya está poblada (ver
    import_sde_categories_groups.py). Si `groups` está vacía todavía,
    esto no rompe nada -- category_id simplemente queda NULL hasta que
    se corra ese otro script.
    """
    conn.execute("""
        UPDATE item_types
        SET category_id = (
            SELECT category_id FROM groups WHERE groups.id = item_types.group_id
        )
        WHERE group_id IS NOT NULL
    """)
    conn.commit()


def main():
    project_root = Path(__file__).resolve().parents[1]
    default_sde_dir = project_root / "sde"

    if len(sys.argv) > 1:
        base_dir = Path(sys.argv[1]).expanduser().resolve()
    else:
        base_dir = default_sde_dir
        print(f"📁 Usando carpeta SDE por defecto del proyecto: {base_dir}")

    if not base_dir.exists():
        print(f"ERROR: La carpeta SDE no existe: {base_dir}")
        print(
            "Descargá el SDE de https://developers.eveonline.com/docs/services/sde/ "
            "y poné el archivo de tipos dentro de la carpeta 'sde/' del proyecto."
        )
        sys.exit(1)

    types_file = find_jsonl_file(base_dir, ["types.jsonl", "invTypes.jsonl"])
    if not types_file:
        print("ERROR: No se encontró types.jsonl ni invTypes.jsonl")
        sys.exit(1)

    db_path = project_root / "database" / "trader.db"
    print(f"Base de datos: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    import_types(conn, types_file)
    _backfill_category_id(conn)

    conn.close()
    print("\n✅ Importación del catálogo de ítems completada.")
    print("Corré también import_sde_categories_groups.py si todavía no lo hiciste --")
    print("category_id necesita la tabla 'groups' para resolverse.")


if __name__ == "__main__":
    main()
