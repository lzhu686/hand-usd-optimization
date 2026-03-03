#!/usr/bin/env python3
"""
Generate placeholder logo texture for Wuji Hand USD.

Creates a 1024x1024 RGBA PNG with red "舞肌" + "WUJI" text
on transparent background. Replace with real logo later.

Usage:
    C:\\Python312\\python.exe scripts/generate_logo_texture.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_logo(output_path: Path, size: int = 1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    red = (204, 13, 13, 255)

    # Try Windows Chinese font, fall back to default
    try:
        font_cn = ImageFont.truetype("msyh.ttc", size // 4)
    except OSError:
        print("WARNING: msyh.ttc not found, using default font")
        font_cn = ImageFont.load_default()

    try:
        font_en = ImageFont.truetype("arial.ttf", size // 8)
    except OSError:
        font_en = ImageFont.load_default()

    # "舞肌" centered upper area
    draw.text((size // 2, size // 3), "舞肌", fill=red, font=font_cn, anchor="mm")
    # "WUJI" centered below
    draw.text(
        (size // 2, size // 2 + size // 8), "WUJI", fill=red, font=font_en, anchor="mm"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))
    print(f"Logo texture saved: {output_path} ({size}x{size})")


def main():
    base = Path(__file__).parent.parent
    output = base / "textures" / "logo" / "wuji_logo_placeholder.png"
    generate_logo(output)


if __name__ == "__main__":
    main()
