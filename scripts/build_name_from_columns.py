"""Rebuild proposed_name from user-edited structured columns.

Reads a CSV that has the parsed columns (category, series, brand, model,
size, color_th, color_code, packaging, condition, pack_variant) and rebuilds
the `proposed_name` column following the rule template:

    [category][series?] [Brand] [#Model][-size] [color_th] [(color_code)] [(packaging)] [(condition)]

Series attaches to category WITHOUT space (per Rule 1).
Brand omitted if empty. Color_code shown in parens after color_th.
Packaging + condition each in their own parens at the end.

Usage:
    python build_name_from_columns.py <input.csv> [--output <out.csv>]

Defaults output to <input>.rebuilt.csv next to input.
Also writes a diff CSV showing rows where proposed_name changed.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "inventory_app" / "instance" / "inventory.db"


def load_color_lookup(db_path: Path) -> dict:
    """Return name_th → code mapping from color_finish_codes."""
    if not db_path.exists():
        return {}
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT code, name_th FROM color_finish_codes"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    return {name_th: code for code, name_th in rows}


def load_code_to_name(db_path: Path) -> dict:
    """Return code → name_th mapping from color_finish_codes (reverse lookup)."""
    if not db_path.exists():
        return {}
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT code, name_th FROM color_finish_codes"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    return {code: name_th for code, name_th in rows}


REQUIRED_COLS = [
    "sku", "product_name", "category", "series", "brand", "model",
    "size", "color_th", "color_code", "packaging", "condition",
    "pack_variant", "proposed_name",
]


def build(row: dict, color_lookup: dict | None = None,
          code_to_name: dict | None = None) -> str:
    cat = row["category"].strip()
    series = row["series"].strip()
    brand = row["brand"].strip()
    model = row["model"].strip()
    size = row["size"].strip()
    color_th = row["color_th"].strip()
    color_code = row["color_code"].strip()
    packaging = row["packaging"].strip()
    condition = row["condition"].strip()
    pack_variant = row["pack_variant"].strip()

    # Reverse-lookup color_th from color_code if code is known —
    # color_finish_codes is the source of truth, so any CSV color_th
    # mismatch gets auto-corrected.
    if color_code and code_to_name and color_code in code_to_name:
        color_th = code_to_name[color_code]

    # Auto-fill color_code if color_th matches a known color name in DB.
    # Idempotent — only fills when code is missing.
    if color_th and not color_code and color_lookup:
        if color_th in color_lookup:
            color_code = color_lookup[color_th]

    parts: list[str] = []

    # 1) category + series
    # Series joining rule (decided 2026-05-06):
    #   - Thai-starting series  → attach with NO space (e.g. บานพับใบโพธิ์ทอง)
    #   - ASCII/digit-starting  → join with SPACE (e.g. กันชนสแตนเลส DOME, สายยู 3 ตอน)
    head = cat
    if series:
        first = series[0]
        if first.isascii() and (first.isalpha() or first.isdigit()):
            head = f"{cat} {series}" if cat else series
        else:
            head = f"{cat}{series}"
    if head:
        parts.append(head)

    # 2) brand (skip if empty)
    if brand:
        parts.append(brand)

    # 3) model + size
    if model and size:
        parts.append(f"{model}-{size}")
    elif model:
        parts.append(model)
    elif size:
        parts.append(size)

    # 4) color_th + (color_code)
    if color_th and color_code:
        parts.append(f"{color_th} ({color_code})")
    elif color_th:
        parts.append(color_th)
    elif color_code:
        parts.append(f"({color_code})")

    # 5) (packaging)
    if packaging:
        parts.append(f"({packaging})")

    # 6) (condition)
    if condition:
        parts.append(f"({condition})")

    # 7) pack_variant — bare numeric suffix at end (matches existing convention,
    #    e.g. "กลอนมะยม Sendai #230-4in สีรมดำ (AC) (ตัว) 1")
    if pack_variant:
        parts.append(pack_variant)

    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="input CSV path")
    ap.add_argument("--output", help="output CSV path (default: <input>.rebuilt.csv)")
    ap.add_argument("--db", help="DB path for color lookup (default: sendy_erp/inventory_app/instance/inventory.db)")
    ap.add_argument("--no-color-fill", action="store_true",
                    help="skip auto-filling color_code from color_th lookup")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 1

    out_path = Path(args.output) if args.output else in_path.with_suffix(".rebuilt.csv")
    diff_path = in_path.with_suffix(".diff.csv")

    rows: list[dict] = []
    with in_path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLS if c not in rdr.fieldnames]
        if missing:
            print(f"missing columns: {missing}", file=sys.stderr)
            return 2
        rows = list(rdr)

    color_lookup: dict = {}
    code_to_name: dict = {}
    if not args.no_color_fill:
        db_path = Path(args.db) if args.db else DEFAULT_DB
        color_lookup = load_color_lookup(db_path)
        code_to_name = load_code_to_name(db_path)
        if color_lookup:
            print(f"Loaded {len(color_lookup)} color codes from {db_path}")

    # Build new proposed_name + collect diffs + count auto-filled color_codes
    diffs: list[tuple[str, str, str, str]] = []  # sku, old_name, new_name, source_name
    color_filled = 0
    for r in rows:
        old = r["proposed_name"].strip()
        old_code = r["color_code"].strip()
        new = build(r, color_lookup, code_to_name)
        # Detect if color_code was just filled by lookup
        if not old_code and color_lookup:
            ct = r["color_th"].strip()
            if ct in color_lookup:
                r["color_code"] = color_lookup[ct]
                color_filled += 1
        # Reverse-fill color_th from code so CSV stays in sync
        if r["color_code"].strip() and code_to_name:
            canonical = code_to_name.get(r["color_code"].strip())
            if canonical:
                r["color_th"] = canonical
        if old != new:
            diffs.append((r["sku"], old, new, r["product_name"]))
        r["proposed_name"] = new

    # Write output
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REQUIRED_COLS)
        w.writeheader()
        w.writerows(rows)

    # Write diff CSV
    with diff_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "product_name (current DB)", "proposed_name (old)", "proposed_name (new)"])
        for sku, old, new, src in diffs:
            w.writerow([sku, src, old, new])

    print(f"Rows total:        {len(rows)}")
    print(f"Rows changed:      {len(diffs)}")
    print(f"Rows same:         {len(rows) - len(diffs)}")
    if color_lookup:
        print(f"color_code filled: {color_filled} (from color_th lookup)")
    print(f"Output:            {out_path}")
    print(f"Diff:              {diff_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
