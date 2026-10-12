"""Render unmodified report pages and recover the official embedded logo.

Development only: pip install pymupdf Pillow
Usage: python scripts/prepare_report_assets.py path/to/report.pdf
"""
import argparse
import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/static/img"
PAGES = {1: "cover", 3: "summary", 4: "endpoint", 10: "review", 11: "ai", 19: "ai-unavailable"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    (OUT / "reports").mkdir(parents=True, exist_ok=True)
    with pymupdf.open(args.report) as doc:
        for page_number, name in PAGES.items():
            page = doc[page_number - 1]
            for width, suffix in [(900, ""), (1800, "-large")]:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(width / page.rect.width, width / page.rect.width), alpha=False)
                Image.open(io.BytesIO(pix.tobytes("png"))).save(OUT / "reports" / f"{name}{suffix}.webp", quality=88, method=6)
        capture_info = next(img for img in doc[3].get_images() if img[2:4] == (2732, 1536))
        capture = Image.open(io.BytesIO(pymupdf.Pixmap(doc, capture_info[0]).tobytes("png")))
        capture.resize((900, 506), Image.Resampling.LANCZOS).save(OUT / "reports/capture.webp", quality=90)
        # The supplied report embeds the same 1536 x 1024 official brand asset.
        logo_info = next(img for img in doc[0].get_images() if img[2:4] == (1536, 1024))
        pix = pymupdf.Pixmap(doc, logo_info[0])
        if logo_info[1]:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, logo_info[1]))
        logo = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
        logo.save(OUT / "vrioscu-logo.png", optimize=True)
        logo.resize((384, 256), Image.Resampling.LANCZOS).save(OUT / "vrioscu-logo.webp", quality=94)
        favicon = Image.new("RGBA", (64, 64))
        small = logo.copy()
        small.thumbnail((64, 64), Image.Resampling.LANCZOS)
        favicon.alpha_composite(small, ((64-small.width)//2, (64-small.height)//2))
        favicon.save(OUT / "favicon.png")
    social = Image.new("RGB", (1200, 630), "#080b10")
    draw = ImageDraw.Draw(social)
    def face(size):
        for name in ("C:/Windows/Fonts/segoeuib.ttf", "DejaVuSans.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)
    draw.line((70, 74, 1130, 74), fill="#25313b", width=2)
    brand = logo.copy()
    brand.thumbnail((95, 64))
    social.paste(brand, (65, 107), brand)
    draw.text((175, 118), "VRIOSCU", font=face(30), fill="white")
    draw.text((70, 235), "Validate every endpoint.", font=face(50), fill="white")
    draw.text((70, 305), "Turn evidence into clarity.", font=face(50), fill="#54e6ef")
    draw.text((70, 438), "VALIDATE  /  CAPTURE  /  ANALYZE  /  DOCUMENT", font=face(21), fill="#a2adbe")
    draw.text((70, 535), "Endpoint Validation & Evidence Capture", font=face(24), fill="#a2adbe")
    social.save(OUT / "og.png", optimize=True)
    print("Rendered report pages 1, 3, 4, 10, 11, 19; extracted official logo; generated favicon and social image.")


if __name__ == "__main__":
    main()
