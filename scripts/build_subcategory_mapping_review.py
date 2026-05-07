"""Build CSV that maps distinct sub_category values → broad category_id.

Auto-suggests mapping by:
  1. Substring match: sub_category contains broad category name (e.g.
     "บานพับสแตนเลส" contains "บานพับ" → match hinge)
  2. Fallback: NULL — Put fills in or leaves blank

User-editable columns:
  - assigned_category_code: short_code of categories row (BLT, HNG, KNB, ...)
  - new_broad_category: if no existing match, write proposed broad category
  - notes: free-text

Output: sendy_erp/data/exports/subcategory_mapping_review.csv

Usage:
  python build_subcategory_mapping_review.py
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "inventory_app" / "instance" / "inventory.db"
OUT = ROOT / "data" / "exports" / "subcategory_mapping_review.csv"


# Manual seeds: key tokens → categories.code (hand-curated for top broad
# matches that don't trivially substring-match)
MANUAL_HINTS = {
    "ดจ":      "drill_bit",     # ดจ. = ดอกเจาะ
    "ดอก":     "drill_bit",
    "โฮลซอ":   "drill_bit",     # hole saw
    "พุก":     "anchor",
    "ปุ๊ก":    "anchor",
    "สมอ":     "anchor",
    "ตะปู":    "fastener",
    "น๊อต":    "fastener",
    "สกรู":    "fastener",
    "รีเวท":   "fastener",
    "บานพับ":  "hinge",
    "กลอน":    "door_bolt",
    "สลัก":    "door_bolt",
    "สายยู":   "fitting",       # hasp/loop — fits 'fitting' generic
    "ลูกบิด":  "door_knob",
    "ก๊อก":    "door_knob",
    "กุญแจ":   "lock_key",
    "แม่กุญแจ": "lock_key",
    "ค้อน":    "hammer",
    "ฆ้อน":    "hammer",
    "ไขควง":   "screwdriver",
    "กรรไกร":  "cutter",
    "มีด":     "cutter",
    "คีม":     "plier",
    "เลื่อย":   "saw",
    "ใบเลื่อย": "saw",
    "ใบตัด":   "disc",          # ใบตัดเพชร, ใบตัดเหล็ก → disc/grinding
    "แผ่นตัด": "disc",
    "แผ่นขัด": "disc",
    "กาว":     "glue",
    "ซิลิโคน":  "glue",
    "สีสเปรย์": "paint_brush",
    "สีน้ำมัน": "paint_brush",
    "สีฝุ่น":   "paint_brush",
    "ลูกกลิ้ง": "paint_brush",  # paint roller
    "แปรง":    "paint_brush",
    "มือจับ":   "handle",
    "หูเหล็ก":  "handle",
    "ประแจ":   "wrench",        # NEW broad
    "กิ๊ป":     "fitting",       # NEW broad — กิ๊ปรัด, กิ๊ปหางปลา
    "จารบี":   "chemical",      # grease falls under chemical
    "น้ำยา":    "chemical",
    "ลูกดิ่ง":  "measuring",
    "ตลับเมตร": "measuring",
    "ฉาก":     "measuring",
    "เทป":     "tape_gypsum",
    "ผ้ายิป":  "tape_gypsum",
    "ก๊อก":    "faucet",
    "เกียง":   "trowel",
    "สลิง":    "wire_cable",
    "ลวด":     "wire_cable",
    "สาย":     "wire_cable",
    "กระดาษทราย": "sandpaper",
    "ผ้าทราย":   "sandpaper",
    "ถุงหิ้ว":  "other",
    "ถุงมือ":  "safety",
    "หน้ากาก": "safety",
    "แว่น":    "safety",
    "พู่กัน":   "paint_brush",
    "ฝักบัว":  "faucet",
    "ขอสับ":   "fitting",
    "ระดับน้ำ": "measuring",
    "สิ่ว":     "cutter",         # chisel — broadly cutting
    "ถ่าน":    "other",
    "ชุดเซ็ตประตู":  "door_bolt",  # door set — broadly door hardware
    "ชุดเซ็ตหน้าต่าง": "door_bolt",
    "เลส":     "fitting",         # stainless misc
    "อ๊อก":    "safety",          # welding / oxidation
    "หินเจียร": "disc",
    "หิน":     "disc",
    # Spelling variants
    "ใบเจียร": "disc",
    "กิ๊บ":     "fitting",         # alt spelling of กิ๊ป
    "ทราย":    "sandpaper",
    "น็อต":    "fastener",        # alt spelling of น๊อต (different tone mark)
    "เกลียว":   "fastener",
    "ถุง":     "other",            # generic bags
    # Round-2 broad cats (mig 041)
    "กรอบจตุคาม": "amulet",
    "พระเครื่อง":   "amulet",
    "ขอแขวน":      "hook",
    "ตะขอแขวน":    "hook",
    "ตะขอ":        "hook",
    "ถังปูน":      "cement_bucket",
    "บักเต้า":     "chalk_line",
    "ปากกาเคมี":   "pen",
    "ปากกา":      "pen",
    "ลังนอก":      "box",
    "กล่องนอก":    "box",
    "กล่อง":      "box",            # was 'other', now box
    "ลัง":        "box",
    "ตะไบ":       "file_tool",
}


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cats = conn.execute(
        "SELECT id, code, name_th, short_code FROM categories ORDER BY id"
    ).fetchall()
    code_to_cat = {c["code"]: dict(c) for c in cats}

    # Distinct sub_categories with count
    rows = conn.execute("""
        SELECT sub_category, COUNT(*) AS n
          FROM products
         WHERE sub_category IS NOT NULL AND sub_category != ''
         GROUP BY sub_category
         ORDER BY n DESC
    """).fetchall()

    output = []
    for r in rows:
        sub = r["sub_category"]
        n = r["n"]

        # Try manual hints first (substring match in sub_category)
        proposed = ""
        confidence = ""
        for hint, code in MANUAL_HINTS.items():
            if hint in sub:
                proposed = code
                confidence = "auto-hint"
                break

        # If no manual hint, try direct substring match against categories.name_th
        if not proposed:
            for c in cats:
                # name_th may have ' / ' alternates: "ลูกบิด / ก๊อกประตู"
                for variant in (c["name_th"] or "").split("/"):
                    v = variant.strip()
                    if v and v in sub:
                        proposed = c["code"]
                        confidence = "substring"
                        break
                if proposed:
                    break

        output.append({
            "sub_category":          sub,
            "sku_count":             n,
            "proposed_category_code": proposed,
            "proposed_category_th":  code_to_cat[proposed]["name_th"] if proposed else "",
            "confidence":            confidence,
            "user_override_code":    "",   # Put fills if proposed is wrong
            "new_broad_category_code":  "",   # Put fills to add new category
            "new_broad_category_name_th": "",
            "notes":                 "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(output[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(output)

    # Summary stats
    auto = sum(1 for r in output if r["confidence"])
    no_match = sum(1 for r in output if not r["confidence"])
    sku_covered = sum(r["sku_count"] for r in output if r["confidence"])
    sku_uncovered = sum(r["sku_count"] for r in output if not r["confidence"])
    print(f"Distinct sub_categories: {len(output)}")
    print(f"  auto-matched:    {auto:>4}  ({sku_covered} SKUs covered)")
    print(f"  no match:        {no_match:>4}  ({sku_uncovered} SKUs uncovered)")
    print(f"\nOutput: {OUT.relative_to(ROOT)}")
    print()
    print("Top 10 unmatched (Put fills user_override_code or new_broad_category_*):")
    for r in [r for r in output if not r["confidence"]][:10]:
        print(f"  {r['sku_count']:>4}  {r['sub_category']}")


if __name__ == "__main__":
    main()
