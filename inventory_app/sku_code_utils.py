"""sku_code generation logic — shared between bulk script and Flask routes.

Format: <CAT>-<BRAND>-<MODEL>-<SIZE>-<COLOR>[-<pack_variant>]
        Fallback: INT-<sku> when nothing structured is available
"""
from __future__ import annotations

import re


def _norm_segment(s: str) -> str:
    """Strip leading '#', whitespace; collapse internal spaces."""
    if not s:
        return ""
    s = s.strip().lstrip("#").strip()
    s = re.sub(r"\s+", "", s)
    return s


def build_sku_code(p: dict) -> str:
    """Build sku_code from a dict-like row.
    Required keys: sku
    Optional keys (segments included when truthy):
      cat_short_code, brand_short_code, model, size, color_code, pack_variant
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
    if p.get("color_code"):
        parts.append(p["color_code"])
    if p.get("pack_variant"):
        parts.append(p["pack_variant"])

    if not parts:
        return f"INT-{p['sku']}"
    return "-".join(parts)


def regenerate_for_product(conn, product_id: int) -> tuple:
    """Recompute sku_code for one product. Returns (old, new).
    Caller is responsible for COMMIT and for honoring sku_code_locked
    (this helper does NOT check the lock — invoke at higher level).
    """
    row = conn.execute("""
        SELECT p.id, p.sku, p.sku_code, p.model, p.size, p.color_code,
               p.pack_variant,
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
