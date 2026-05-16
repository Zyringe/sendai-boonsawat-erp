"""Import curated customer Google-Map locations into the `customers` table.

Source = the per-region customer_map CSVs (อีสาน first; north/south/east/west
later). Rows are matched to existing customers by `code` (exact). The CSV
template may change over time, so column resolution is header-driven and
tolerant: known headers are matched via a case-insensitive alias table, and
`--map HEADER=field` lets you override/add a mapping without code changes.

Writes: lat, lng, geocoded_at (existing columns) + plus_code, gmap_name,
gmap_address (migration 053). The CSV is the curated source of truth, so by
default existing values are overwritten; pass --only-empty to skip customers
that already have a lat.

Default mode is DRY-RUN. Use --apply to commit.

    python scripts/import_customer_geomap.py "<file.csv>"            # preview
    python scripts/import_customer_geomap.py "<file.csv>" --apply    # write
    python scripts/import_customer_geomap.py "<file.csv>" --only-empty --apply
    python scripts/import_customer_geomap.py "<file.csv>" --map "ละติจูด=lat"
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "inventory_app" / "instance" / "inventory.db"

# db_field -> acceptable header names (normalised: lower, stripped, spaces and
# underscores collapsed to a single '_').
ALIASES = {
    "code":         {"code"},
    "lat":          {"latitude", "lat"},
    "lng":          {"longitude", "lng", "lon", "long"},
    "plus_code":    {"plus_code", "pluscode"},
    "gmap_name":    {"name_google_map", "google_map_name", "gmap_name"},
    "gmap_address": {"address_google_map", "google_map_address", "gmap_address"},
}
REQUIRED = ("code", "lat", "lng")
OPTIONAL = ("plus_code", "gmap_name", "gmap_address")


def _norm(h: str) -> str:
    """Normalise a header for matching: lower, strip, spaces/underscores -> _."""
    out = h.strip().lower()
    for ch in (" ", "-", "."):
        out = out.replace(ch, "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def build_field_map(headers, overrides=None):
    """Resolve {db_field: actual_csv_header} from a CSV header list.

    `overrides` is a list of "CSV_HEADER=db_field" strings (exact CSV header).
    Raises ValueError listing the headers seen if any REQUIRED field is absent.
    """
    norm_to_actual = {}
    for h in headers:
        if h is None:
            continue
        norm_to_actual.setdefault(_norm(h), h)

    field_map = {}
    for db_field, names in ALIASES.items():
        for n in names:
            if n in norm_to_actual:
                field_map[db_field] = norm_to_actual[n]
                break

    for ov in overrides or []:
        if "=" not in ov:
            raise ValueError(f"--map expects HEADER=field, got: {ov!r}")
        csv_header, db_field = ov.split("=", 1)
        csv_header, db_field = csv_header.strip(), db_field.strip()
        if db_field not in ALIASES:
            raise ValueError(
                f"--map target {db_field!r} unknown; valid: {sorted(ALIASES)}"
            )
        field_map[db_field] = csv_header

    missing = [f for f in REQUIRED if f not in field_map]
    if missing:
        raise ValueError(
            f"CSV is missing required column(s) {missing}. "
            f"Headers seen: {list(headers)}. "
            f"Use --map 'YourHeader={missing[0]}' to map it."
        )
    return field_map


def parse_rows(csv_path, overrides=None):
    """Yield (rownum, {db_field: value}) for each data row.

    Returns (rows, field_map). Rows with unparseable lat/lng are still yielded
    with lat/lng=None so the caller can report them as skipped.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        field_map = build_field_map(reader.fieldnames or [], overrides)
        rows = []
        for i, raw in enumerate(reader, start=2):  # row 1 = header
            rec = {}
            for db_field, header in field_map.items():
                val = (raw.get(header) or "").strip()
                rec[db_field] = val if val != "" else None
            for k in ("lat", "lng"):
                try:
                    rec[k] = float(rec[k]) if rec[k] is not None else None
                except (TypeError, ValueError):
                    rec[k] = None
            rows.append((i, rec))
    return rows, field_map


def run(csv_path, db_path=DB_PATH, apply=False, only_empty=False,
        overrides=None, verbose=True):
    """Match CSV rows to customers.code and update geo fields.

    Returns a summary dict (counts) — used by tests and the CLI."""
    rows, field_map = parse_rows(csv_path, overrides)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            r["code"]: r["lat"]
            for r in conn.execute("SELECT code, lat FROM customers")
        }
        present_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(customers)")
        }
    finally:
        pass

    writable = ["lat", "lng"] + [
        c for c in OPTIONAL if c in field_map and c in present_cols
    ]

    to_update, not_found, skipped, bad_coord = [], [], [], []
    for rownum, rec in rows:
        code = rec.get("code")
        if not code:
            bad_coord.append((rownum, "blank code"))
            continue
        if code not in existing:
            not_found.append(code)
            continue
        if rec["lat"] is None or rec["lng"] is None:
            bad_coord.append((rownum, code))
            continue
        if only_empty and existing[code] is not None:
            skipped.append(code)
            continue
        to_update.append(rec)

    summary = {
        "csv_rows": len(rows),
        "matched": len(to_update),
        "not_in_customers": len(not_found),
        "not_in_customers_codes": not_found,
        "skipped_only_empty": len(skipped),
        "bad_or_blank": len(bad_coord),
        "writable_columns": writable,
        "applied": False,
    }

    if verbose:
        print(f"CSV: {csv_path}")
        print(f"  field map     : {field_map}")
        print(f"  writable cols : {writable}")
        print(f"  csv rows      : {summary['csv_rows']}")
        print(f"  matched code  : {summary['matched']}")
        print(f"  NOT in customers: {summary['not_in_customers']}"
              + (f" -> {not_found}" if not_found else ""))
        print(f"  skipped (only-empty): {summary['skipped_only_empty']}")
        print(f"  bad/blank rows: {summary['bad_or_blank']}"
              + (f" -> {bad_coord}" if bad_coord else ""))

    if not apply:
        if verbose:
            print("\nDRY-RUN. Back up first (scripts/backup_db.sh), "
                  "then re-run with --apply to commit.")
        conn.close()
        return summary

    set_clause = ", ".join(f"{c}=?" for c in writable)
    set_clause += ", geocoded_at=datetime('now','localtime')"
    sql = f"UPDATE customers SET {set_clause} WHERE code=?"
    n = 0
    for rec in to_update:
        params = [rec.get(c) for c in writable] + [rec["code"]]
        conn.execute(sql, params)
        n += 1
    conn.commit()
    conn.close()
    summary["applied"] = True
    summary["updated"] = n
    if verbose:
        print(f"\nAPPLIED: {n} customer rows updated "
              f"(geocoded_at set to now).")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_path", type=Path, help="customer_map CSV file")
    p.add_argument("--db", type=Path, default=DB_PATH,
                   help="DB path (default: live inventory.db)")
    p.add_argument("--apply", action="store_true",
                   help="commit changes (default: dry-run)")
    p.add_argument("--only-empty", action="store_true",
                   help="skip customers that already have a lat")
    p.add_argument("--map", action="append", default=[], metavar="HEADER=field",
                   help="override column mapping; repeatable")
    args = p.parse_args(argv)

    if not args.csv_path.exists():
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        return 2
    try:
        run(args.csv_path, db_path=args.db, apply=args.apply,
            only_empty=args.only_empty, overrides=args.map)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
