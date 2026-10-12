#!/usr/bin/env python3
"""Generate the social-sharing image with the official extracted logo (Pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/static/img/og.png"


def font(size):
    for name in ("C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def generate():
    logo_path = ROOT / "app/static/img/vrioscu-logo.png"
    if not logo_path.is_file():
        raise FileNotFoundError("Run scripts/prepare_report_assets.py with the supplied report first.")
    logo = Image.open(logo_path).convert("RGBA")
    social = Image.new("RGB", (1200, 630), "#080b10")
    draw = ImageDraw.Draw(social)
    draw.line((70, 74, 1130, 74), fill="#25313b", width=2)
    logo.thumbnail((95, 64), Image.Resampling.LANCZOS)
    social.paste(logo, (65, 107), logo)
    draw.text((175, 118), "VRIOSCU", font=font(30), fill="white")
    draw.text((70, 235), "Validate every endpoint.", font=font(50), fill="white")
    draw.text((70, 305), "Turn evidence into clarity.", font=font(50), fill="#54e6ef")
    draw.text((70, 438), "VALIDATE  /  CAPTURE  /  ANALYZE  /  DOCUMENT", font=font(21), fill="#a2adbe")
    draw.text((70, 535), "Endpoint Validation & Evidence Capture", font=font(24), fill="#a2adbe")
    social.save(OUT, optimize=True)
    return OUT


if __name__ == "__main__":
    print(f"Wrote {generate()}")
