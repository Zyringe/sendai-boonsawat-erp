"""Scan product photos in source folder, match each to a family/SKU in
the DB, and COPY (not move) to organized destination structure:

    Design/Catalog/photos/products/
      {category_code}/
        {family_code}/
          info.md
          {family_code}_auto_NN.jpg          (shared family images)
          {sku_code}_auto_NN.jpg             (variant-specific, when filename
                                              clearly identifies one SKU)

Matching strategy (per photo):
  1. Extract tokens from filename: model digits (#NNN, NNN-N), size
     (4in/4นิ้ว), color codes (AC/SS/JBB/...), Thai color words (สีดำ etc.).
  2. Hint from source folder name: 'กลอน' → category door_bolt, etc.
  3. Score candidate products: model match (high), size match (med), color
     (med). Pick best.
  4. If ambiguous (multiple equal-score), choose the family-level placement
     and let user disambiguate later.

Output:
  CSV: data/exports/photo_match_log.csv     — what matched what
  CSV: data/exports/photo_unmatched.csv     — files we couldn't place
  info.md per family with display_name + sku list

Default mode is dry-run (just emits CSVs). Use --apply to copy files.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "inventory_app" / "instance" / "inventory.db"
WORKSPACE = ROOT.parent  # Sendai-Boonsawat
SRC_DIR = Path("/Volumes/ZYRINGE/Job BSN/Picture BSN")
DEST_ROOT = WORKSPACE / "Design" / "Catalog" / "photos" / "products"
LOG_OUT = ROOT / "data" / "exports" / "photo_match_log.csv"
UNMATCHED_OUT = ROOT / "data" / "exports" / "photo_unmatched.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Folder name (Thai) → category code hint. Folders not in this map don't
# constrain category, just contribute filename tokens.
FOLDER_HINTS = {
    "กลอน":         "door_bolt",
    "บานพับ":       "hinge",
    "มือจับ":       "handle",
    "ลูกบิด":       "door_knob",
    "KNOB":         "door_knob",
    "กุญแจ":        "lock_key",
    "ค้อน":         "hammer",
    "ฆ้อน":         "hammer",
    "ไขควง":        "screwdriver",
    "กรรไกร":       "cutter",
    "คีม":          "plier",
    "เลื่อย":        "saw",
    "ใบเลื่อย":      "saw",
    "ตะปู":         "fastener",
    "พุก":          "anchor",
    "ปุ๊ก":         "anchor",
    "กาว":          "glue",
    "สี":           "paint_brush",
    "แปรง":         "paint_brush",
    "เครื่องเหล็ก":   "drill_bit",
    "แผ่นตัด":       "disc",
    "โป้้ว":         "trowel",
    "โป้ว":         "trowel",
    "ขอสับ":        "fitting",
    "ขอแขวน":       "hook",
    "สายยู":        "fitting",
    "กันชน":        "fitting",
    "ชุดเซ็ต":       "door_bolt",
    "แผง":          "door_bolt",
    "ห้องน้ำ":       "faucet",
    "แบบประตู":      "door_bolt",
}


def _tokenize_filename(name: str) -> dict:
    """Extract structured tokens: model digits, size, color codes."""
    base = Path(name).stem
    out = {"model_tokens": [], "size_tokens": [], "color_tokens": []}

    # Model: bare 3-5 digit numbers OR # prefix
    for m in re.finditer(r"#?(\d{3,5})(?!\.\d)", base):
        out["model_tokens"].append(m.group(1))

    # Size: digit + unit (4in/4นิ้ว/4mm)
    for m in re.finditer(r"\d+(?:\.\d+|/\d+)?\s*(?:in|นิ้ว|mm|cm)\b", base, re.IGNORECASE):
        out["size_tokens"].append(re.sub(r"\s+", "", m.group(0).lower())
                                    .replace("นิ้ว", "in"))

    # Bare size like "4-4" or "1/16" without unit
    for m in re.finditer(r"\b\d+/\d+\b|\b\d+-\d+\b", base):
        out["size_tokens"].append(m.group(0))

    return out, base


def _score_product(p, tokens, folder_hint, color_codes_set):
    """Score how well a product matches the tokens. Higher = better."""
    score = 0
    name_low = (p["product_name"] or "").lower()
    model = (p["model"] or "").lstrip("#").lower()
    size = (p["size"] or "").lower()
    color = (p["color_code"] or "").upper()

    # Folder-hint category match
    if folder_hint and p["cat_code"] == folder_hint:
        score += 30

    # Model match
    if model:
        for tok in tokens["model_tokens"]:
            if tok == model or model in tok or tok in model:
                score += 50
                break

    # Size match
    if size:
        for tok in tokens["size_tokens"]:
            if tok == size or tok.replace(" ", "") == size:
                score += 25
                break

    # Color code in filename
    for cc in color_codes_set:
        if cc and re.search(rf"\b{re.escape(cc)}\b", tokens.get("raw_base", ""), re.IGNORECASE):
            if cc.upper() == color:
                score += 25
                break

    return score


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="Actually copy files (default: dry-run, just write CSVs)")
    p.add_argument("--limit", type=int, help="Process only N files (testing)")
    args = p.parse_args()

    if not SRC_DIR.exists():
        raise SystemExit(f"source not found (mount drive?): {SRC_DIR}")

    # Load DB context
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    products = conn.execute("""
        SELECT p.id, p.sku, p.sku_code, p.product_name, p.model, p.size,
               p.color_code, p.family_id,
               c.code AS cat_code, c.short_code AS cat_short,
               b.short_code AS brand_short,
               pf.family_code, pf.display_name AS family_name
          FROM products p
          LEFT JOIN categories c ON c.id = p.category_id
          LEFT JOIN brands b ON b.id = p.brand_id
          LEFT JOIN product_families pf ON pf.id = p.family_id
         WHERE p.is_active = 1
    """).fetchall()
    products = [dict(r) for r in products]

    color_codes = {
        r[0] for r in conn.execute("SELECT code FROM color_finish_codes")
    }

    # Walk source dir — ONLY photos under whitelisted product folders.
    # AW (artwork), LOGO, Line, PO, customer-named folders typically contain
    # banners/screenshots/business assets, not product photos.
    PRODUCT_FOLDERS = set(FOLDER_HINTS.keys())
    photos = []
    skipped_non_product = 0
    for path in SRC_DIR.rglob("*"):
        if not (path.is_file() and path.suffix.lower() in IMAGE_EXTS):
            continue
        rel = path.relative_to(SRC_DIR)
        if not any(part in PRODUCT_FOLDERS for part in rel.parts):
            skipped_non_product += 1
            continue
        photos.append(path)
    print(f"Found {len(photos)} photos in product folders (skipped {skipped_non_product} non-product).")
    if args.limit:
        photos = photos[: args.limit]
        print(f"Limited to first {args.limit}.")

    # Pre-index products by model digit token (for fast lookup)
    by_model_token = defaultdict(list)
    for p_row in products:
        m = (p_row["model"] or "").lstrip("#")
        digits = re.findall(r"\d{3,5}", m)
        for d in digits:
            by_model_token[d].append(p_row)
        # Also index by sub_category for products without model
        if not m and p_row.get("cat_code"):
            by_model_token[f"_cat_{p_row['cat_code']}"].append(p_row)

    matched = []
    unmatched = []
    family_seq = defaultdict(int)  # family_code → next image #
    sku_seq = defaultdict(int)     # sku_code → next image #

    for ph in photos:
        # folder hint = first ancestor folder name in FOLDER_HINTS
        rel = ph.relative_to(SRC_DIR)
        folder_hint = None
        for part in rel.parts[:-1]:
            if part in FOLDER_HINTS:
                folder_hint = FOLDER_HINTS[part]
                break

        tokens, base = _tokenize_filename(ph.name)
        tokens["raw_base"] = base

        # Build candidate set from model tokens + folder-hint products
        cand_set = set()
        for tok in tokens["model_tokens"]:
            for p_row in by_model_token.get(tok, []):
                cand_set.add(p_row["id"])
        # Also include cat-only products if folder hint present
        if folder_hint:
            for p_row in by_model_token.get(f"_cat_{folder_hint}", []):
                cand_set.add(p_row["id"])

        if not cand_set:
            unmatched.append({
                "source_path": str(rel),
                "tokens": str(tokens),
                "folder_hint": folder_hint or "",
                "best_score": 0,
                "best_match_sku": "",
            })
            continue

        # Score only candidates
        prod_by_id = {p["id"]: p for p in products}
        scored = []
        for pid in cand_set:
            p_row = prod_by_id[pid]
            s = _score_product(p_row, tokens, folder_hint, color_codes)
            if s > 0:
                scored.append((s, p_row))
        scored.sort(key=lambda x: -x[0])

        # Score < 50 = only folder-hint matched (no model/size/color in
        # filename) → too unreliable; mark unmatched so user can review.
        if not scored or scored[0][0] < 50:
            unmatched.append({
                "source_path": str(rel),
                "tokens": str(tokens),
                "folder_hint": folder_hint or "",
                "best_score": scored[0][0] if scored else 0,
                "best_match_sku": scored[0][1]["sku"] if scored else "",
            })
            continue

        # Best match: pick family-level placement; if all top-tied scores
        # are same family, sku-specific. If single SKU best score, use that.
        best_score = scored[0][0]
        top = [t for t in scored if t[0] == best_score]
        # Sanitize codes for filesystem (replace '/' which appears in some
        # color combos like BN/AC, SB/PB) — use '_' instead.
        def _safe(s):
            return (s or "").replace("/", "_")

        # Determine destination
        family_codes = {t[1]["family_code"] for t in top if t[1]["family_code"]}
        if len(family_codes) == 1 and len(top) > 1:
            # Family-level (shared image)
            family_code = list(family_codes)[0]
            cat_short = top[0][1]["cat_short"] or "OTH"
            cat_code = top[0][1]["cat_code"] or "other"
            family_seq[family_code] += 1
            n = family_seq[family_code]
            dest_dir = DEST_ROOT / cat_code / _safe(family_code)
            new_name = f"{_safe(family_code)}_auto_{n:02d}{ph.suffix.lower()}"
            level = "family"
            target_sku = ""
            target_family = family_code
        else:
            # SKU-specific match
            best_p = top[0][1]
            sku_code = best_p["sku_code"] or f"INT-{best_p['sku']}"
            cat_short = best_p["cat_short"] or "OTH"
            cat_code = best_p["cat_code"] or "other"
            family_code = best_p["family_code"] or sku_code
            sku_seq[sku_code] += 1
            n = sku_seq[sku_code]
            dest_dir = DEST_ROOT / cat_code / _safe(family_code)
            new_name = f"{_safe(sku_code)}_auto_{n:02d}{ph.suffix.lower()}"
            level = "sku"
            target_sku = sku_code
            target_family = family_code

        matched.append({
            "source_path":   str(rel),
            "best_score":    best_score,
            "level":         level,
            "target_family": target_family,
            "target_sku":    target_sku,
            "category_code": cat_code,
            "dest_path":     str(dest_dir.relative_to(WORKSPACE) / new_name),
            "alternatives":  ",".join(str(t[1]["sku"]) for t in top[:3]),
        })

        if args.apply:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ph, dest_dir / new_name)

    # Write CSVs
    LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    if matched:
        with open(LOG_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(matched[0].keys()))
            w.writeheader()
            w.writerows(matched)
    if unmatched:
        with open(UNMATCHED_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(unmatched[0].keys()))
            w.writeheader()
            w.writerows(unmatched)

    # Generate info.md per family that received images
    if args.apply:
        family_to_skus = defaultdict(list)
        for m in matched:
            family_to_skus[m["target_family"]].append(m)
        for family_code, items in family_to_skus.items():
            cat_code = items[0]["category_code"]
            family_dir = DEST_ROOT / cat_code / family_code
            family_dir.mkdir(parents=True, exist_ok=True)
            # Family details from DB
            row = conn.execute(
                "SELECT pf.display_name, pf.display_format, "
                "       (SELECT GROUP_CONCAT(sku_code, ',') FROM products p WHERE p.family_id = pf.id) AS skus "
                "  FROM product_families pf WHERE pf.family_code = ?",
                (family_code,)
            ).fetchone()
            display_name = row["display_name"] if row else family_code
            display_format = row["display_format"] if row else "single"
            skus = row["skus"] if row else ""
            info = (family_dir / "info.md")
            info.write_text(
                f"# {display_name}\n\n"
                f"- family_code: `{family_code}`\n"
                f"- display_format: `{display_format}`\n"
                f"- SKUs: {skus or '(singleton)'}\n\n"
                f"## Images ({len(items)} matched)\n\n"
                + "\n".join(f"- `{Path(m['dest_path']).name}` (level={m['level']}, score={m['best_score']})"
                            for m in items)
                + "\n",
                encoding="utf-8"
            )

    # Summary
    print(f"\nMatched:    {len(matched)}")
    print(f"Unmatched:  {len(unmatched)}")
    print(f"Match log:  {LOG_OUT.relative_to(ROOT)}")
    print(f"Unmatched:  {UNMATCHED_OUT.relative_to(ROOT)}")
    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply to copy files.")
    else:
        print(f"\nCopied to:  {DEST_ROOT.relative_to(WORKSPACE)}")


if __name__ == "__main__":
    main()
