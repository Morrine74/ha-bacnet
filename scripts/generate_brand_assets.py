"""Generate the BACnet brand assets (icon/logo PNGs).

Run with the project virtualenv:

    .venv\\Scripts\\python.exe scripts/generate_brand_assets.py

Produces, under ``brands/custom_integrations/bacnet/``:
    icon.png       256x256
    icon@2x.png    512x512
    logo.png       <=256 tall, trimmed
    logo@2x.png    2x of logo.png

The design is a soft pastel rounded badge showing a small "device bus" (three
nodes connected on a line) — a nod to a BACnet network — matching the palette
used by the Lovelace schedule card.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "brands", "custom_integrations", "bacnet"
)

# Pastel palette (matches the schedule card).
MINT = (191, 227, 192)
BLUE = (174, 223, 247)
INK = (44, 62, 80)
WHITE = (255, 255, 255)


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _gradient(size):
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        color = _lerp(MINT, BLUE, y / max(1, size - 1))
        for x in range(size):
            px[x, y] = color
    return grad


def make_icon(size: int) -> Image.Image:
    """Draw the square badge icon at the requested size."""
    radius = round(size * 0.22)
    base = _gradient(size)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(base, (0, 0), _rounded_mask(size, radius))

    draw = ImageDraw.Draw(icon)

    # Bus line with three nodes, centred.
    cy = round(size * 0.56)
    margin = round(size * 0.22)
    x0, x1 = margin, size - margin
    line_w = max(2, round(size * 0.035))
    draw.line([(x0, cy), (x1, cy), ], fill=INK + (255,), width=line_w)

    node_r = round(size * 0.075)
    for x in (x0, (x0 + x1) // 2, x1):
        draw.ellipse(
            [x - node_r, cy - node_r, x + node_r, cy + node_r],
            fill=WHITE + (255,),
            outline=INK + (255,),
            width=line_w,
        )

    # A small "building" block above the centre node to evoke automation.
    bw = round(size * 0.16)
    bh = round(size * 0.20)
    bx = (x0 + x1) // 2 - bw // 2
    by = round(size * 0.20)
    draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=round(size * 0.03),
        fill=WHITE + (235,),
        outline=INK + (255,),
        width=max(1, round(size * 0.02)),
    )
    # Windows.
    win = round(size * 0.03)
    gap = round(size * 0.045)
    for row in range(2):
        for col in range(2):
            wx = bx + gap + col * (win + gap // 2)
            wy = by + gap + row * (win + gap // 2)
            draw.rectangle([wx, wy, wx + win, wy + win], fill=INK + (255,))

    return icon


def make_logo(height: int) -> Image.Image:
    """Draw a horizontal logo: badge + 'BACnet' wordmark."""
    badge = make_icon(height)
    text = "BACnet"

    font = _load_font(round(height * 0.62))
    tmp = Image.new("RGBA", (10, 10))
    tdraw = ImageDraw.Draw(tmp)
    bbox = tdraw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    gap = round(height * 0.18)
    width = height + gap + tw
    logo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    logo.paste(badge, (0, 0), badge)

    draw = ImageDraw.Draw(logo)
    ty = (height - th) // 2 - bbox[1]
    draw.text((height + gap, ty), text, font=font, fill=INK + (255,))
    return logo


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    make_icon(256).save(os.path.join(OUT_DIR, "icon.png"))
    make_icon(512).save(os.path.join(OUT_DIR, "icon@2x.png"))

    logo = make_logo(128)
    logo.save(os.path.join(OUT_DIR, "logo.png"))
    make_logo(256).save(os.path.join(OUT_DIR, "logo@2x.png"))

    print(f"Brand assets written to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
