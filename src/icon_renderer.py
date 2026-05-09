"""
Tray icon image generation - rounded-rectangle with bold balance label.
"""
from PIL import Image, ImageDraw, ImageFont

from src.config import log

_ICON_OK     = (60, 105, 102, 255)  # teal
_ICON_RED    = (185, 70, 60, 255)
_ICON_GRAY   = (105, 105, 110, 255)
_ICON_RADIUS = 12

# Gray with a subtle warm tint — distinguishes "API degraded"
# from "no data" at a glance while still reading as uncertain.
_ICON_WARN   = (120, 105, 90, 255)


def _draw_rounded_rect(draw, xy, radius, **kwargs):
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, **kwargs)
    else:
        draw.rectangle(xy, **kwargs)


def create_icon_image(app):
    try:
        return _create_icon_image_impl(app)
    except Exception as e:
        log(f"Icon generation failed: {e}")
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([8, 8, 56, 56], fill=(105, 105, 110, 255))
        return img


def _create_icon_image_impl(app):
    size = 64
    radius = _ICON_RADIUS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    label = "..."
    with app._lock:
        err = app.error
        b = app.get_preferred_balance()
        st = app.service_status

    if err:
        fill = _ICON_RED
        label = "!"
    elif b is None:
        fill = _ICON_GRAY
        label = "..."
    else:
        val = int(b["total_balance"])
        api_ok = st is None or st.get("api_operational", True)
        if not api_ok:
            fill = _ICON_WARN
        elif app.is_low_balance():
            fill = _ICON_RED
        else:
            fill = _ICON_OK
        label = str(val) if val <= 99 else "OK"

    margin = 0
    _draw_rounded_rect(draw, [margin, margin, size - margin, size - margin],
                       radius=radius, fill=fill)
    _draw_rounded_rect(draw, [margin, margin, size - margin, size - margin],
                       radius=radius, outline=(255, 255, 255, 60), width=1)

    font_size = 48 if len(label) <= 1 else (44 if len(label) == 2 else 38)
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
              fill=(255, 255, 255, 255), font=font, anchor="mm")

    return img
