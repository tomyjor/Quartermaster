"""
Tests para ApiServices.list_categories / list_groups_by_category /
list_types_in_group -- superficie nueva expuesta vía HTTP para el
explorador de Categoría → Grupo en NiceGUI (antes solo Streamlit lo
usaba, con acceso directo a la base).
"""

import sqlite3
import tempfile
from pathlib import Path

from presentation.api.services import ApiServices
from _winsafe import safe_unlink

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"


def _make_db_with_catalog() -> Path:
    tmp_path = Path(tempfile.mkstemp(suffix=".db")[1])
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_PATH.read_text())

    conn.execute("INSERT INTO categories (id, name, published) VALUES (6, 'Ship', 1)")
    conn.execute("INSERT INTO groups (id, category_id, name, published) VALUES (25, 6, 'Frigate', 1)")
    conn.execute("INSERT INTO groups (id, category_id, name, published) VALUES (26, 6, 'Cruiser', 1)")
    conn.execute(
        "INSERT INTO item_types (id, name, group_id, category_id, published) "
        "VALUES (587, 'Rifter', 25, 6, 1)"
    )
    conn.execute(
        "INSERT INTO item_types (id, name, group_id, category_id, published) "
        "VALUES (588, 'Slasher', 25, 6, 1)"
    )
    conn.execute(
        "INSERT INTO item_types (id, name, group_id, category_id, published) "
        "VALUES (620, 'Caracal', 26, 6, 1)"
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_list_categories_returns_real_categories_with_item_counts():
    db_path = _make_db_with_catalog()
    try:
        svc = ApiServices(db_path=db_path)
        categories = svc.list_categories()

        assert len(categories) == 1
        assert categories[0]["category_id"] == 6
        assert categories[0]["name"] == "Ship"
        assert categories[0]["item_count"] == 3
    finally:
        safe_unlink(db_path)


def test_list_groups_by_category_returns_only_groups_in_that_category():
    db_path = _make_db_with_catalog()
    try:
        svc = ApiServices(db_path=db_path)
        groups = svc.list_groups_by_category(6)

        group_ids = {g["group_id"] for g in groups}
        assert group_ids == {25, 26}
        frigate = next(g for g in groups if g["group_id"] == 25)
        assert frigate["item_count"] == 2
    finally:
        safe_unlink(db_path)


def test_list_groups_by_category_empty_for_unknown_category():
    db_path = _make_db_with_catalog()
    try:
        svc = ApiServices(db_path=db_path)
        groups = svc.list_groups_by_category(999999)
        assert groups == []
    finally:
        safe_unlink(db_path)


def test_list_types_in_group_returns_correct_items():
    db_path = _make_db_with_catalog()
    try:
        svc = ApiServices(db_path=db_path)
        types = svc.list_types_in_group(25)

        names = {t["name"] for t in types}
        assert names == {"Rifter", "Slasher"}
    finally:
        safe_unlink(db_path)


def test_list_types_in_group_respects_limit():
    db_path = _make_db_with_catalog()
    try:
        svc = ApiServices(db_path=db_path)
        types = svc.list_types_in_group(25, limit=1)
        assert len(types) == 1
    finally:
        safe_unlink(db_path)
