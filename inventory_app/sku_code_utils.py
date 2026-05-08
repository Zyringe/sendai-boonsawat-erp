"""sku_code generation logic — shared between bulk script and Flask routes.

Format: <CAT>-<BRAND>-<MODEL>-<SIZE>[-<SERIES>]-<COLOR>-<PKG>[-<pack_variant>]
        Fallback: INT-<sku> when nothing structured is available
"""
from __future__ import annotations

import hashlib
import re


# Packaging Thai → 2-3 char English code (Option D, 2026-05-08).
# Hardcoded here since packaging is a TEXT column on products (no FK table).
# Add new mappings here as packaging values are added (must align with
# the products_packaging_check_* CHECK trigger in DB).
PACKAGING_SHORT = {
    "ตัว":         "UN",   # Unit
    "แผง":         "PN",   # Panel
    "ถุง":         "BG",   # Bag
    "ซอง":         "SC",   # Sachet
    "แพ็ค":        "PK",   # Pack
    "โหล":         "DZ",   # Dozen
    "แพ็คหัว":     "HP",   # Hanging-Pack
    "แพ็คถุง":     "PP",   # Pouch-Pack
    "แบบหลอด":     "TB",   # Tube
    "อัดแผง":      "SP",   # Strip-Pack
    "1กลมี60ใบ":   "C60",  # Carton-60
}


def _norm_segment(s: str) -> str:
    """Strip leading '#', whitespace; collapse internal spaces."""
    if not s:
        return ""
    s = s.strip().lstrip("#").strip()
    s = re.sub(r"\s+", "", s)
    return s


def _series_segment(s: str) -> str:
    """Convert series value to a sku_code-safe segment.
    ASCII: cleaned + uppercase (DOME, BRUSHNO.98, CSK).
    Thai/mixed: 'S' + 4-hex hash (stable across runs, ASCII-safe).
    """
    if not s:
        return ""
    s = s.strip()
    if s.isascii():
        return re.sub(r"\s+", "", s).upper()
    return "S" + hashlib.md5(s.encode("utf-8")).hexdigest()[:4].upper()


def build_sku_code(p: dict) -> str:
    """Build sku_code from a dict-like row.
    Required keys: sku
    Optional keys (segments included when truthy):
      cat_short_code, brand_short_code, model, size, series,
      color_code, packaging (Thai value, looked up via PACKAGING_SHORT),
      pack_variant
    """
    parts = []
    if p.get("cat_short_code"):
        parts.append(p["cat_short_code"])
    if p.get("brand_short_code"):
        parts.append(p["brand_short_code"])
    if p.get("model"):
        parts.append(_norm_segment(p["model"]))
    if p.get("size"):
        parts.append(_norm_segment(p["size"]))
    if p.get("series"):
        seg = _series_segment(p["series"])
        if seg:
            parts.append(seg)
    if p.get("color_code"):
        parts.append(p["color_code"])
    if p.get("packaging"):
        pkg_code = PACKAGING_SHORT.get(p["packaging"])
        if pkg_code:
            parts.append(pkg_code)
    if p.get("pack_variant"):
        parts.append(str(p["pack_variant"]))

    if not parts:
        return f"INT-{p['sku']}"
    return "-".join(parts)


def regenerate_for_product(conn, product_id: int) -> tuple:
    """Recompute sku_code for one product. Returns (old, new).
    Caller is responsible for COMMIT and for honoring sku_code_locked
    (this helper does NOT check the lock — invoke at higher level).
    """
    row = conn.execute("""
        SELECT p.id, p.sku, p.sku_code, p.model, p.size, p.series,
               p.color_code, p.packaging, p.pack_variant,
               b.short_code AS brand_short_code,
               c.short_code AS cat_short_code
          FROM products p
          LEFT JOIN brands b     ON b.id = p.brand_id
          LEFT JOIN categories c ON c.id = p.category_id
         WHERE p.id = ?
    """, (product_id,)).fetchone()
    if not row:
        return None, None

    old_code = row["sku_code"] if "sku_code" in row.keys() else row[2]
    new_code = build_sku_code(dict(row))

    # Collision check — append -<sku> if collision (unless same product)
    collision = conn.execute(
        "SELECT id FROM products WHERE sku_code = ? AND id != ?",
        (new_code, product_id),
    ).fetchone()
    if collision:
        new_code = f"{new_code}-{row['sku']}"

    if new_code != old_code:
        conn.execute(
            "UPDATE products SET sku_code = ? WHERE id = ?",
            (new_code, product_id)
        )
    return old_code, new_code
