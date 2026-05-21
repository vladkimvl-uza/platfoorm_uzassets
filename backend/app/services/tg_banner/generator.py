"""Premium / enterprise banner renderer (Pack 149 — Phase B upgrade).

Output: 1280×400 PNG, cinematic 16:5 ratio. Telegram caps photo+caption at
1024 chars total, so the banner does the heavy visual work and the caption
carries the actionable copy.

Composition:
  • Multi-stop mesh gradient background (3 stops with radial bloom)
  • Subtle dot-grid texture overlay (premium pattern, ~12 alpha)
  • Top accent bar in severity color (instant priority readout)
  • Brand mark top-left: UA monogram + UzAssets wordmark + tagline
  • Center-left: large module icon glyph drawn from Pillow primitives
    with soft glow halo for depth
  • Right side: severity pill + XL module label, right-aligned
  • Footer line: brand domain + timestamp + thin separator

Cyrillic-safe: bundles Noto Sans (Regular + Bold) in `./assets/`. Falls back
to system DejaVu, then PIL bitmap.
"""
from __future__ import annotations

import io
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import cache as _cache
from .templates import (
    ALLOWED_MODULES,
    ALLOWED_SEVERITIES,
    module_spec_for,
    palette_for,
    resolve_module,
    resolve_severity,
)

log = logging.getLogger(__name__)

# Bump to invalidate cache after any visual change
BANNER_VERSION = "3"

BANNER_W = 1280
BANNER_H = 400

ASSETS_DIR = Path(__file__).parent / "assets"

_FONT_CACHE: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Cached font loader. Bundled Noto Sans (Cyrillic) first, system DejaVu next."""
    key = (bold, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if bold:
        candidates = [
            ASSETS_DIR / "NotoSans-Bold.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ASSETS_DIR / "NotoSans-Regular.ttf",
        ]
    else:
        candidates = [
            ASSETS_DIR / "NotoSans-Regular.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    for p in candidates:
        try:
            if p.exists():
                f = ImageFont.truetype(str(p), size=size)
                _FONT_CACHE[key] = f
                return f
        except (OSError, ValueError):
            continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex_to_rgba(h: str, alpha: int = 255):
    r, g, b = _hex_to_rgb(h)
    return r, g, b, alpha


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _paint_mesh_gradient(img: Image.Image, palette):
    """Diagonal base gradient + radial accent bloom + corner vignette."""
    bg_from = _hex_to_rgb(palette["bg_from"])
    bg_to = _hex_to_rgb(palette["bg_to"])
    accent = _hex_to_rgb(palette["accent"])

    w, h = img.size
    px = img.load()
    norm = w * 0.55 + h * 0.45

    # Diagonal base
    for y in range(h):
        for x in range(w):
            t = (x * 0.55 + y * 0.45) / norm
            px[x, y] = _mix(bg_from, bg_to, t)

    # Radial accent bloom (right-center)
    bloom_cx, bloom_cy, bloom_r = w * 0.82, h * 0.45, h * 1.2
    bloom_r_sq = bloom_r * bloom_r
    for y in range(h):
        for x in range(w):
            dx, dy = x - bloom_cx, y - bloom_cy
            d_sq = dx * dx + dy * dy
            if d_sq > bloom_r_sq:
                continue
            t = (1.0 - math.sqrt(d_sq) / bloom_r) ** 2 * 0.22
            r, g, b = px[x, y]
            r = min(255, int(r + (accent[0] - r) * t))
            g = min(255, int(g + (accent[1] - g) * t))
            b = min(255, int(b + (accent[2] - b) * t))
            px[x, y] = (r, g, b)

    # Corner vignette (bottom-left)
    vc_x, vc_y, vc_r = w * 0.05, h * 1.0, h * 0.95
    vc_r_sq = vc_r * vc_r
    for y in range(h):
        for x in range(w):
            dx, dy = x - vc_x, y - vc_y
            d_sq = dx * dx + dy * dy
            if d_sq > vc_r_sq:
                continue
            t = (1.0 - math.sqrt(d_sq) / vc_r) ** 2 * 0.18
            r, g, b = px[x, y]
            px[x, y] = (int(r * (1 - t)), int(g * (1 - t)), int(b * (1 - t)))


def _paint_dot_grid(img: Image.Image, color_hex: str, alpha: int = 12):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    fg = (*_hex_to_rgb(color_hex), alpha)
    spacing = 14
    r = 1
    for y in range(spacing, img.height - spacing, spacing):
        for x in range(spacing, img.width - spacing, spacing):
            od.ellipse((x - r, y - r, x + r, y + r), fill=fg)
    img.alpha_composite(overlay)


def _draw_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int,
               module: str, fg_hex: str):
    """Module-specific glyph drawn from primitives (no SVG asset required)."""
    fg = _hex_to_rgba(fg_hex)
    cx, cy = x + size // 2, y + size // 2
    line_w = max(3, size // 16)

    if module == "kpi":
        bw = size // 5
        gap = size // 8
        total_w = bw * 3 + gap * 2
        ox = cx - total_w // 2
        oy = cy + size // 3
        for i, hf in enumerate([0.45, 0.70, 1.0]):
            bh = int(size * 0.65 * hf)
            draw.rectangle((ox + i * (bw + gap), oy - bh,
                            ox + i * (bw + gap) + bw, oy), fill=fg)
    elif module in ("bp", "tasks"):
        m = size // 8
        draw.rounded_rectangle((x + m, y + m, x + size - m, y + size - m),
                               radius=size // 14, outline=fg, width=line_w)
        for ly in (0.38, 0.52, 0.66):
            inset = m * 3 if ly == 0.66 else m * 2
            draw.line((x + size * 0.22, y + size * ly,
                       x + size - inset, y + size * ly),
                      fill=fg, width=max(2, line_w - 1))
    elif module in ("credit", "loan"):
        m = size // 10
        draw.ellipse((x + m, y + m, x + size - m, y + size - m),
                     outline=fg, width=line_w)
        font = _load_font(int(size * 0.55), bold=True)
        text = "$"
        tw, th = _text_size(draw, text, font)
        draw.text((cx - tw // 2, cy - th // 2 - size // 22), text,
                  font=font, fill=fg)
    elif module == "procurement":
        m = size // 7
        draw.line((x + m, y + m * 1.5, x + size - m * 2, y + m * 1.5),
                  fill=fg, width=line_w)
        draw.line((x + m * 2, y + m * 1.5, int(x + m * 2.8), int(y + size - m * 2)),
                  fill=fg, width=line_w)
        draw.line((int(x + m * 2.8), int(y + size - m * 2),
                   x + size - int(m * 1.5), y + size - m * 2),
                  fill=fg, width=line_w)
        wheel_r = max(3, size // 18)
        for wx in (x + m * 3, x + size - m * 2):
            draw.ellipse((wx - wheel_r, y + size - m // 2,
                          wx + wheel_r, y + size - m // 2 + wheel_r * 2), fill=fg)
    elif module == "deadline":
        m = size // 10
        draw.ellipse((x + m, y + m, x + size - m, y + size - m),
                     outline=fg, width=line_w)
        draw.line((cx, cy, cx + int(size * 0.22), cy - int(size * 0.18)),
                  fill=fg, width=line_w)
        draw.line((cx, cy, cx - int(size * 0.05), cy - int(size * 0.30)),
                  fill=fg, width=line_w)
    elif module == "moderation":
        m = size // 9
        draw.polygon([
            (cx, y + m), (x + size - m, y + m + size // 6),
            (x + size - m, y + size // 2),
            (cx, y + size - m),
            (x + m, y + size // 2),
            (x + m, y + m + size // 6),
        ], outline=fg, width=line_w)
        draw.line((cx - size // 6, cy, cx - 2, cy + size // 6),
                  fill=fg, width=line_w + 1)
        draw.line((cx - 2, cy + size // 6, cx + size // 4, cy - size // 6),
                  fill=fg, width=line_w + 1)
    elif module == "mfa":
        m = size // 7
        draw.arc((x + int(m * 1.5), y + m, x + size - int(m * 1.5),
                  int(y + size * 0.55)),
                 start=180, end=360, fill=fg, width=line_w)
        draw.rounded_rectangle(
            (x + m, int(y + size * 0.42), x + size - m, y + size - m),
            radius=size // 16, outline=fg, width=line_w)
        draw.ellipse((cx - 5, cy + 4, cx + 5, cy + 16), outline=fg, width=line_w)
    elif module in ("auth", "rbac"):
        m = size // 6
        draw.ellipse((cx - size // 6, y + m, cx + size // 6, y + m + size // 3),
                     outline=fg, width=line_w)
        draw.arc((x + m, cy, x + size - m, y + size + size // 4),
                 start=180, end=360, fill=fg, width=line_w)
    elif module == "audit":
        r = size // 3
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=fg, width=line_w)
        draw.line((int(cx + r * 0.7), int(cy + r * 0.7),
                   x + size - size // 8, y + size - size // 8),
                  fill=fg, width=line_w + 1)
    elif module == "esg":
        m = size // 7
        draw.polygon([
            (cx, y + m), (x + size - m, cy),
            (cx, y + size - m), (x + m, cy),
        ], outline=fg, width=line_w)
        draw.line((x + m, y + size - m, x + size - m, y + m),
                  fill=fg, width=max(2, line_w - 1))
    elif module == "governance":
        m = size // 7
        draw.polygon([
            (x + m // 2, y + m + size // 6),
            (cx, y + m),
            (x + size - m // 2, y + m + size // 6),
        ], fill=fg)
        draw.rectangle((x + m // 2, y + size - m,
                        x + size - m // 2, y + size - m + line_w), fill=fg)
        col_w = max(3, line_w)
        for i in range(3):
            cx_col = int(x + m + (size - m * 2) * (i / 2))
            draw.rectangle((cx_col, y + m + size // 5,
                            cx_col + col_w, y + size - m), fill=fg)
    else:
        # Bell (system / fallback)
        m = size // 7
        draw.polygon([
            (cx, y + m),
            (x + size - m, int(y + size - m * 1.5)),
            (x + m, int(y + size - m * 1.5)),
        ], outline=fg, width=line_w)
        draw.rectangle((int(x + m * 1.2), int(y + size - m * 1.8),
                        int(x + size - m * 1.2), int(y + size - m * 1.2)),
                       outline=fg, width=line_w)
        draw.ellipse((cx - 4, int(y + size - m * 1.05), cx + 4,
                      int(y + size - m * 0.4)), fill=fg)


# Brandmark removed per user request — banners now lead with module identity.


# ── Per-module decorative pattern (subtle BG ornament) ──────────────────

def _paint_module_pattern(img: Image.Image, module: str, fg_hex: str):
    """Draw a low-alpha geometric pattern unique per module — gives each
    notification a recognisable visual fingerprint independent of label.
    Painted right-side, low alpha so it never competes with content.
    """
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    fg = (*_hex_to_rgb(fg_hex), 28)
    band_fg = (*_hex_to_rgb(fg_hex), 22)

    if module == "kpi":
        # Ascending zig-zag (chart-line motif)
        path = [(int(w * 0.55) + i * 30, int(h * 0.78 - (i % 2) * 28))
                for i in range(20)]
        if len(path) > 1:
            od.line(path, fill=fg, width=3)
    elif module in ("bp", "tasks"):
        # Faint stacked horizontal bars (document lines)
        for i in range(6):
            y = int(h * 0.22) + i * 26
            od.rectangle((int(w * 0.55), y, int(w * 0.93), y + 3), fill=band_fg)
    elif module in ("credit", "loan"):
        # Concentric circles (coin echo)
        cx, cy = int(w * 0.78), int(h * 0.50)
        for r in (200, 150, 100, 60):
            od.ellipse((cx - r, cy - r, cx + r, cy + r), outline=band_fg, width=2)
    elif module == "procurement":
        # Diagonal stripes
        for i in range(-2, 12):
            x0 = int(w * 0.55) + i * 50
            od.line((x0, h, x0 + 80, 0), fill=band_fg, width=3)
    elif module == "deadline":
        # Hour-glass ticks around right circle
        cx, cy, r = int(w * 0.78), int(h * 0.50), 130
        for i in range(12):
            ang = math.radians(i * 30 - 90)
            x1 = cx + int(math.cos(ang) * (r - 10))
            y1 = cy + int(math.sin(ang) * (r - 10))
            x2 = cx + int(math.cos(ang) * r)
            y2 = cy + int(math.sin(ang) * r)
            od.line((x1, y1, x2, y2), fill=fg, width=3)
    elif module == "moderation":
        # Stylized shield outlines, repeated faded
        for offset in (0, 30, 60):
            cx, cy = int(w * 0.75 + offset), int(h * 0.50 + offset // 3)
            od.polygon([
                (cx, cy - 80), (cx + 70, cy - 50), (cx + 70, cy + 30),
                (cx, cy + 80), (cx - 70, cy + 30), (cx - 70, cy - 50),
            ], outline=band_fg, width=2)
    elif module == "mfa":
        # Hex grid (security tech feel)
        for row in range(-1, 5):
            for col in range(-1, 6):
                cx = int(w * 0.55) + col * 60 + (30 if row % 2 else 0)
                cy = int(h * 0.20) + row * 52
                pts = [(cx + 18, cy), (cx + 9, cy + 16), (cx - 9, cy + 16),
                       (cx - 18, cy), (cx - 9, cy - 16), (cx + 9, cy - 16)]
                od.polygon(pts, outline=band_fg, width=1)
    elif module in ("auth", "rbac"):
        # Concentric dots (access ring)
        cx, cy = int(w * 0.78), int(h * 0.50)
        for r in (170, 140, 110, 80, 50):
            for ang_deg in range(0, 360, 22):
                ang = math.radians(ang_deg)
                px = cx + int(math.cos(ang) * r)
                py = cy + int(math.sin(ang) * r)
                od.ellipse((px - 3, py - 3, px + 3, py + 3), fill=band_fg)
    elif module == "audit":
        # Crosshair grid
        for i in range(int(w * 0.55), w, 50):
            od.line((i, 0, i, h), fill=band_fg, width=1)
        for i in range(0, h, 50):
            od.line((int(w * 0.55), i, w, i), fill=band_fg, width=1)
    elif module == "esg":
        # Leaf veins
        cx, cy = int(w * 0.78), int(h * 0.50)
        for ang_deg in (30, 60, 90, 120, 150):
            ang = math.radians(ang_deg)
            x1 = cx - int(math.cos(ang) * 140)
            y1 = cy - int(math.sin(ang) * 140)
            x2 = cx + int(math.cos(ang) * 140)
            y2 = cy + int(math.sin(ang) * 140)
            od.line((x1, y1, x2, y2), fill=band_fg, width=2)
    elif module == "governance":
        # Column tops
        for i in range(8):
            x0 = int(w * 0.55) + i * 70
            od.rectangle((x0, int(h * 0.35), x0 + 24, int(h * 0.75)),
                         outline=band_fg, width=2)
    else:
        # Dots constellation (system fallback)
        for i in range(80):
            x = int(w * 0.55) + (i * 79) % int(w * 0.40)
            y = (i * 51) % h
            od.ellipse((x - 2, y - 2, x + 2, y + 2), fill=band_fg)

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=1))
    img.alpha_composite(overlay)


def _severity_label_ru(severity: str) -> str:
    return {
        "info":     "Уведомление",
        "success":  "Готово",
        "warning":  "Требует внимания",
        "critical": "Критично",
    }.get(severity, "Уведомление")


def render(module: str, severity: str, *,
           headline_metric: Optional[str] = None) -> bytes:
    """Render the premium banner.

    Optional `headline_metric` (e.g. `"$12.4M"`, `"7 дней"`, `"85%"`) is
    rendered as a giant focal number under the module label — the killer
    visual hook for finance/deadline/KPI notifications.
    """
    module = resolve_module(module)
    severity = resolve_severity(severity)

    cache_key_extra = f"m={headline_metric or ''}"
    cached = _cache.get(module, severity, BANNER_VERSION + "|" + cache_key_extra)
    if cached is not None:
        return cached

    pal = palette_for(severity)
    spec = module_spec_for(module)

    # 1. Canvas + mesh gradient
    base = Image.new("RGB", (BANNER_W, BANNER_H), (0, 0, 0))
    _paint_mesh_gradient(base, pal)
    img = base.convert("RGBA")

    # 2. Dot-grid texture + module-specific decorative pattern
    _paint_dot_grid(img, pal["fg"], alpha=12)
    _paint_module_pattern(img, module, pal["fg"])

    draw = ImageDraw.Draw(img, "RGBA")

    # 3. Top severity accent bar
    draw.rectangle((0, 0, BANNER_W, 6), fill=_hex_to_rgba(pal["accent"]))

    # 4. Icon with soft glow halo (left side, slightly elevated since
    #    brand mark is removed)
    icon_size = 200
    icon_x = 90
    icon_y = 100
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse(
        (icon_x - 60, icon_y - 60, icon_x + icon_size + 60, icon_y + icon_size + 60),
        fill=(*_hex_to_rgb(pal["accent"]), 70),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(radius=40))
    img.alpha_composite(halo)
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_icon(draw, icon_x, icon_y, icon_size, module, pal["fg"])

    # 5. Right-side cluster — severity pill + module label + optional metric
    label_text = spec.get("label_ru", module.title())
    label_font = _load_font(56, bold=True)
    label_w, label_h = _text_size(draw, label_text, label_font)
    right_anchor_x = BANNER_W - 60

    sev_text = _severity_label_ru(severity).upper()
    sev_font = _load_font(16, bold=True)
    sev_w, sev_h = _text_size(draw, sev_text, sev_font)
    pill_pad_x, pill_pad_y = 14, 7
    pill_w = sev_w + pill_pad_x * 2
    pill_h = sev_h + pill_pad_y * 2
    pill_x = right_anchor_x - pill_w
    pill_y = 70
    draw.rounded_rectangle(
        (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
        radius=pill_h // 2,
        fill=_hex_to_rgba(pal["accent"], 235),
    )
    draw.text((pill_x + pill_pad_x, pill_y + pill_pad_y - 2),
              sev_text, font=sev_font, fill=_hex_to_rgba("#1E2A4A"))

    label_x = right_anchor_x - label_w
    label_y = pill_y + pill_h + 14
    draw.text((label_x, label_y), label_text,
              font=label_font, fill=_hex_to_rgba(pal["fg"]))

    # 6. Big headline metric (e.g. "7 дней", "$12.4M", "85%") — killer hook
    if headline_metric:
        metric_font = _load_font(96, bold=True)
        m_w, m_h = _text_size(draw, headline_metric, metric_font)
        # Right-aligned just below label, with accent color highlight
        metric_x = right_anchor_x - m_w
        metric_y = label_y + label_h + 14

        # Faint backdrop glow for metric
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.rectangle((metric_x - 30, metric_y - 8,
                      metric_x + m_w + 30, metric_y + m_h + 20),
                     fill=(*_hex_to_rgb(pal["accent"]), 30))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=20))
        img.alpha_composite(glow)
        draw = ImageDraw.Draw(img, "RGBA")

        # Vertical accent bar to the left of the metric
        draw.rectangle((metric_x - 16, metric_y + 8,
                        metric_x - 10, metric_y + m_h + 4),
                       fill=_hex_to_rgba(pal["accent"], 255))
        draw.text((metric_x, metric_y), headline_metric,
                  font=metric_font, fill=_hex_to_rgba(pal["fg"]))

    # 7. Footer (domain + timestamp + separator)
    foot_font = _load_font(14)
    foot_color = (*_hex_to_rgb(pal["fg"]), 160)
    now_str = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y · %H:%M")
    foot_left = "platform.uz-assets.uz"
    fr_w, _ = _text_size(draw, now_str, foot_font)
    foot_y = BANNER_H - 36
    draw.text((44, foot_y), foot_left, font=foot_font, fill=foot_color)
    draw.text((BANNER_W - 60 - fr_w, foot_y), now_str,
              font=foot_font, fill=foot_color)
    draw.line((44, foot_y - 10, BANNER_W - 60, foot_y - 10),
              fill=(*_hex_to_rgb(pal["fg"]), 35), width=1)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True, compress_level=6)
    data = buf.getvalue()

    _cache.put(module, severity, BANNER_VERSION + "|" + cache_key_extra, data)
    return data


def get_banner_bytes(module: str, severity: str, *,
                     headline_metric: Optional[str] = None) -> bytes:
    return render(module, severity, headline_metric=headline_metric)


def get_banner_url(base_url: str, module: str, severity: str, *,
                   headline_metric: Optional[str] = None) -> str:
    module = resolve_module(module)
    severity = resolve_severity(severity)
    q = f"v={BANNER_VERSION}"
    if headline_metric:
        # URL-encode the metric for safe transport
        from urllib.parse import quote
        q += f"&m={quote(headline_metric)}"
    return f"{base_url.rstrip('/')}/tg-banners/{module}/{severity}.png?{q}"


def list_modules() -> list[str]:
    return sorted(ALLOWED_MODULES)


def list_severities() -> list[str]:
    return sorted(ALLOWED_SEVERITIES)
