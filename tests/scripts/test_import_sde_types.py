"""
Tests para scripts/import_sde_types.py -- importador del catálogo
completo de ítems, necesario para que un clon nuevo del proyecto tenga
nombres reales en vez de "Type-1234".
"""

import sqlite3
import sys
import tempfile
import importlib.util
from pathlib import Path
from _winsafe import safe_unlink

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "import_sde_types.py"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("import_sde_types", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    conn.close()
    return tmp_path


def _make_jsonl(tmp_dir: Path, filename: str, lines: list) -> Path:
    import json
    path = tmp_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


def test_import_types_parses_valid_lines_and_skips_invalid_ones():
    mod = _load_script_module()
    db_path = _make_db()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        jsonl_path = _make_jsonl(tmp_dir, "types.jsonl", [
            {"_key": 34, "name": {"en": "Tritanium"}, "groupID": 18, "published": True},
            {"_key": 35, "name": {"en": "Pyerite"}, "groupID": 18, "published": True},
            {"_key": 999, "name": None, "groupID": 18},  # inválido, debe saltearse
        ])

        conn = sqlite3.connect(db_path)
        count = mod.import_types(conn, jsonl_path)
        conn.close()

        assert count == 2

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM item_types WHERE id = 34").fetchone()
        conn.close()
        assert row["name"] == "Tritanium"
    finally:
        safe_unlink(db_path)


def test_backfill_category_id_resolves_via_groups_join():
    mod = _load_script_module()
    db_path = _make_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO categories (id, name, published) VALUES (4, 'Material', 1)")
        conn.execute("INSERT INTO groups (id, category_id, name, published) VALUES (18, 4, 'Mineral', 1)")
        conn.execute(
            "INSERT INTO item_types (id, name, group_id, published) VALUES (34, 'Tritanium', 18, 1)"
        )
        conn.commit()

        mod._backfill_category_id(conn)
        conn.commit()

        row = conn.execute("SELECT category_id FROM item_types WHERE id = 34").fetchone()
        conn.close()
        assert row[0] == 4
    finally:
        safe_unlink(db_path)


def test_backfill_does_not_crash_when_groups_is_empty():
    """Si todavía no se corrió import_sde_categories_groups.py, no debe romper -- category_id queda NULL."""
    mod = _load_script_module()
    db_path = _make_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO item_types (id, name, group_id, published) VALUES (34, 'Tritanium', 18, 1)"
        )
        conn.commit()

        mod._backfill_category_id(conn)  # no debería lanzar excepción
        conn.commit()

        row = conn.execute("SELECT category_id FROM item_types WHERE id = 34").fetchone()
        conn.close()
        assert row[0] is None
    finally:
        safe_unlink(db_path)


def test_find_jsonl_file_accepts_both_naming_conventions():
    mod = _load_script_module()
    tmp_dir = Path(tempfile.mkdtemp())
    (tmp_dir / "invTypes.jsonl").write_text("")

    found = mod.find_jsonl_file(tmp_dir, ["types.jsonl", "invTypes.jsonl"])

    assert found == tmp_dir / "invTypes.jsonl"
