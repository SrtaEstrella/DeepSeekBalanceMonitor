"""
Tray icon image generation - rounded-rectangle with bold balance label.
"""
from PIL import Image, ImageDraw, ImageFont

from src.core.config import log, get_api_by_id
from src.platforms.registry import get_platform

_RADIUS = 12

THEMES = {
    "default": {
        "ok":       (60, 105, 102, 255),
        "low":      (185, 70, 60, 255),
        "fast":     (230, 145, 40, 255),
        "degraded": (120, 105, 90, 255),
        "nodata":   (105, 105, 110, 255),
    },
    "contrast": {
        "ok":       (45, 128, 116, 255),
        "low":      (212, 52, 46, 255),
        "fast":     (245, 140, 20, 255),
        "degraded": (139, 105, 20, 255),
        "nodata":   (85, 85, 85, 255),
    },
    "bright": {
        "ok":       (200, 235, 230, 255),
        "low":      (245, 210, 205, 255),
        "fast":     (250, 195, 130, 255),
        "degraded": (235, 220, 205, 255),
        "nodata":   (215, 215, 220, 255),
    },
    "dark_mode": {
        "ok":       (80, 155, 148, 255),
        "low":      (215, 100, 90, 255),
        "fast":     (235, 160, 70, 255),
        "degraded": (155, 140, 115, 255),
        "nodata":   (125, 125, 130, 255),
    },
    "mono": {
        "ok":       (85, 85, 85, 255),
        "low":      (34, 34, 34, 255),
        "fast":     (190, 190, 190, 255),
        "degraded": (119, 119, 119, 255),
        "nodata":   (153, 153, 153, 255),
    },
}


def _text_color(rgb):
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return (0, 0, 0, 255) if lum > 170 else (255, 255, 255, 255)


def _hex_to_rgba(hex_str):
    v = int(hex_str.strip("#"), 16)
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF, 255)


def _get_colors(config):
    theme = config.get("theme", "default")
    if theme == "custom":
        custom = config.get("icon_colors", {})
        def _c(k):
            h = custom.get(k, "")
            return _hex_to_rgba(h) if len(h) == 6 else THEMES["default"][k]
        return {k: _c(k) for k in ("ok", "low", "fast", "degraded", "nodata")}
    return THEMES.get(theme, THEMES["default"])


def _draw_rounded_rect(draw, xy, radius, **kwargs):
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, **kwargs)
    else:
        draw.rectangle(xy, **kwargs)


def create_icon_image(app):
    try:
        return _create_icon_image_impl(app, 256)
    except Exception as e:
        log(f"Icon generation failed: {e}")
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([32, 32, 224, 224], fill=(105, 105, 110, 255))
        return img


def _create_icon_image_impl(app, size=256):
    scale = size / 64.0
    radius = int(_RADIUS * scale)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    label = "..."
    with app._lock:
        err = app.error
        b = app.get_preferred_balance()
        st = app.service_status
        pd = app.package_data

    colors = _get_colors(app.config)

    if pd:
        # Package mode: show remaining % for preferred billing_period
        billing_period = ""
        try:
            pref_api_id = app.config.get("preferred_api_id")
            if pref_api_id:
                pref_api = get_api_by_id(pref_api_id)
                if pref_api:
                    billing_period = pref_api.get("billing_period") or ""
                    if not billing_period:
                        pmeta = get_platform(pref_api.get("platform", ""))
                        billing_period = pmeta.default_billing_period if pmeta else "monthly"
        except Exception:
            pass
        col_map = {"5h": pd.get("5h") or pd.get("rolling"), "weekly": pd.get("weekly"), "monthly": pd.get("monthly")}
        mp = col_map.get(billing_period)
        if mp:
            remaining = max(0, int(mp.get("percent_remaining", 100 - mp.get("usage_percent", 0))))
            label = str(remaining)
            if app.is_low_balance():
                fill = colors["low"]
            elif app.is_daily_spend_fast():
                fill = colors["fast"]
            else:
                fill = colors["ok"]
    elif err:
        fill = colors["low"]
        label = "!"
    elif b is None:
        fill = colors["nodata"]
        label = "..."
    else:
        val = int(b["total_balance"])
        api_ok = st is None or st.get("api_operational", True)
        if not api_ok:
            fill = colors["degraded"]
        elif app.is_low_balance():
            fill = colors["low"]
        elif app.is_daily_spend_fast():
            fill = colors["fast"]
        else:
            fill = colors["ok"]
        label = str(val) if val <= 99 else "OK"

    text_fill = _text_color(fill)

    margin = 0
    _draw_rounded_rect(draw, [margin, margin, size - margin, size - margin],
                       radius=radius, fill=fill)
    if app.config.get("icon_stroke", False):
        stroke = text_fill[:3] + (180,)
        _draw_rounded_rect(draw, [margin, margin, size - margin, size - margin],
                           radius=radius, outline=stroke, width=max(1, int(5 * scale)))

    font_size = (48 if len(label) <= 1 else (44 if len(label) == 2 else 38))
    font_size = int(font_size * scale)
    try:
        font = ImageFont.truetype("segoeuib.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("segoeui.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("arialbd.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except Exception:
                    font = ImageFont.load_default()

    draw.text((size / 2, size / 2), label,
              fill=text_fill, font=font, anchor="mm")

    return img
