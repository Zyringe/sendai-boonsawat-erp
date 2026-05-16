"""Tests for migration 053 + scripts/import_customer_geomap.py.

Covers: the new customers gmap columns exist after migrations; the
header-driven column resolver (aliases, overrides, required-check); and the
match-by-code importer in dry-run / apply / only-empty modes.
"""
import os
import sqlite3
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import import_customer_geomap as icg  # noqa: E402

MIG_053 = os.path.join(REPO_ROOT, "data", "migrations",
                       "053_add_customer_gmap_fields.sql")


def _apply_053(db_path):
    """Apply migration 053 to a DB copy if not already present (idempotent).

    Uses tmp_db (copy of live DB) rather than the empty_db fixture because the
    full from-scratch migration chain (014_commission) does not build cleanly
    on a fresh DB — a pre-existing limitation unrelated to this change.
    """
    c = sqlite3.connect(db_path)
    cols = {r[1] for r in c.execute("PRAGMA table_info(customers)")}
    if "plus_code" not in cols:
        with open(MIG_053, encoding="utf-8") as f:
            c.executescript(f.read())
        c.commit()
    c.close()


# ── 1. migration 053 ─────────────────────────────────────────────────────────

def test_migration_053_adds_columns(tmp_db):
    _apply_053(tmp_db)
    c = sqlite3.connect(tmp_db)
    cols = {r[1] for r in c.execute("PRAGMA table_info(customers)")}
    c.close()
    assert {"plus_code", "gmap_name", "gmap_address"} <= cols
    # existing geo columns must still be present (reused, not duplicated)
    assert {"lat", "lng", "geocoded_at"} <= cols


def test_migration_053_does_not_self_record():
    """Regression guard: run_pending_migrations records every migration it
    executes (database.py); a self-insert into applied_migrations causes a
    duplicate-key crash on boot. 053 must NOT self-record."""
    with open(MIG_053, encoding="utf-8") as f:
        # ignore -- comment lines (the file documents the rule in a comment)
        code = "\n".join(
            ln for ln in f if not ln.lstrip().startswith("--")
        ).lower()
    assert "insert into applied_migrations" not in code


# ── 2. header resolver ───────────────────────────────────────────────────────

def test_header_alias_resolves_csv_template():
    headers = ["code", "name", "name_google_map", "plus_code",
               "Latitude", "Longitude", "address_google_map", "province"]
    fm = icg.build_field_map(headers)
    assert fm["code"] == "code"
    assert fm["lat"] == "Latitude"
    assert fm["lng"] == "Longitude"
    assert fm["plus_code"] == "plus_code"
    assert fm["gmap_name"] == "name_google_map"
    assert fm["gmap_address"] == "address_google_map"


def test_missing_required_header_raises_with_seen_headers():
    with pytest.raises(ValueError) as e:
        icg.build_field_map(["code", "name", "foo"])  # no lat/lng
    msg = str(e.value)
    assert "lat" in msg and "foo" in msg  # names the missing field + seen headers


def test_map_override_for_changed_template():
    # Future template renames the coord columns to Thai
    headers = ["code", "ละติจูด", "ลองจิจูด"]
    fm = icg.build_field_map(headers, overrides=["ละติจูด=lat", "ลองจิจูด=lng"])
    assert fm["lat"] == "ละติจูด" and fm["lng"] == "ลองจิจูด"


# ── 3. importer: match by code, dry-run then apply ───────────────────────────

def _seed_customer(db_path, code, name="ทดสอบ", lat=None, lng=None):
    c = sqlite3.connect(db_path)
    if lat is None:
        c.execute("INSERT INTO customers(code, name) VALUES(?,?)", (code, name))
    else:
        c.execute("INSERT INTO customers(code, name, lat, lng) VALUES(?,?,?,?)",
                  (code, name, lat, lng))
    c.commit()
    c.close()


def _write_csv(tmp_path, rows):
    p = tmp_path / "map.csv"
    lines = ["code,name,name_google_map,plus_code,Latitude,Longitude,"
             "address_google_map,province"]
    lines += rows
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_import_dryrun_then_apply(tmp_db, tmp_path):
    _apply_053(tmp_db)
    _seed_customer(tmp_db, "ZGEO_TH1")  # synthetic code, no geo yet
    csv = _write_csv(tmp_path, [
        "ZGEO_TH1,ร้านมาลี,ร้านมาลี,7P66WCF2+5X,14.9229385,104.4024194,หมู่3,ศรีสะเกษ",
        "NOPE_ZZ9,ไม่มีจริง,x,7P00+00,15.0,104.0,-,ศรีสะเกษ",
    ])

    dry = icg.run(csv, db_path=tmp_db, apply=False, verbose=False)
    assert dry["matched"] == 1
    assert dry["not_in_customers"] == 1
    assert dry["not_in_customers_codes"] == ["NOPE_ZZ9"]
    assert dry["applied"] is False
    c = sqlite3.connect(tmp_db)
    assert c.execute("SELECT lat FROM customers WHERE code='ZGEO_TH1'").fetchone()[0] is None
    assert c.execute("SELECT COUNT(*) FROM customers WHERE code='NOPE_ZZ9'").fetchone()[0] == 0
    c.close()

    res = icg.run(csv, db_path=tmp_db, apply=True, verbose=False)
    assert res["applied"] is True and res["updated"] == 1
    c = sqlite3.connect(tmp_db)
    row = c.execute(
        "SELECT lat,lng,plus_code,gmap_name,gmap_address,geocoded_at "
        "FROM customers WHERE code='ZGEO_TH1'"
    ).fetchone()
    c.close()
    assert abs(row[0] - 14.9229385) < 1e-6 and abs(row[1] - 104.4024194) < 1e-6
    assert row[2] == "7P66WCF2+5X"
    assert row[3] == "ร้านมาลี" and row[4] == "หมู่3"
    assert row[5] is not None  # geocoded_at stamped


def test_only_empty_preserves_existing_lat(tmp_db, tmp_path):
    _apply_053(tmp_db)
    _seed_customer(tmp_db, "ZGEO_C1", lat=1.0, lng=2.0)  # already geocoded
    csv = _write_csv(tmp_path, [
        "ZGEO_C1,ร้าน,ร้าน,PC+1,13.5,100.5,addr,กท",
    ])

    skip = icg.run(csv, db_path=tmp_db, apply=True, only_empty=True, verbose=False)
    assert skip["matched"] == 0 and skip["skipped_only_empty"] == 1
    c = sqlite3.connect(tmp_db)
    assert c.execute("SELECT lat FROM customers WHERE code='ZGEO_C1'").fetchone()[0] == 1.0
    c.close()

    over = icg.run(csv, db_path=tmp_db, apply=True, only_empty=False, verbose=False)
    assert over["updated"] == 1
    c = sqlite3.connect(tmp_db)
    assert c.execute("SELECT lat FROM customers WHERE code='ZGEO_C1'").fetchone()[0] == 13.5
    c.close()
