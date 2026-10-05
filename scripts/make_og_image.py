#!/usr/bin/env python3
"""Generate app/static/img/og.png (1200x630 social share image). Requires Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "og.png"
W, H = 1200, 630


def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf"] if bold
             else ["DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


img = Image.new("RGB", (W, H), "#16202a")
d = ImageDraw.Draw(img)

# Mark: viewfinder corners + check
x, y, s, c = 90, 96, 64, "#8db6f2"
for pts in [[(x, y + 20), (x, y), (x + 20, y)], [(x + s - 20, y), (x + s, y), (x + s, y + 20)],
            [(x + s, y + s - 20), (x + s, y + s), (x + s - 20, y + s)], [(x + 20, y + s), (x, y + s), (x, y + s - 20)]]:
    d.line(pts, fill=c, width=6, joint="curve")
d.line([(x + 17, y + 34), (x + 28, y + 45), (x + 48, y + 22)], fill="white", width=7, joint="curve")
d.text((x + 90, y + 10), "V R I O S C U", font=font(40, True), fill="white")

big = font(92, True)
for i, t in enumerate(["Validate.", "Capture.", "Document."]):
    d.text((90, 215 + i * 100), t, font=big, fill="white")
d.text((90, 555), "Endpoint Validation & Evidence Capture", font=font(30), fill="#a3b1bd")

# Blank report sheet
d.rectangle([840, 170, 1110, 552], fill="white")
d.rectangle([840, 170, 1110, 232], fill="#223040")
d.text((862, 188), "VRIOSCU", font=font(22, True), fill="white")
d.text((862, 260), "Endpoint", font=font(28, True), fill="#16202a")
d.text((862, 294), "Validation Report", font=font(28, True), fill="#16202a")
for i in range(4):
    yy = 410 + i * 30
    d.line([(960, yy), (1088, yy)], fill="#b4bec7", width=2)
    d.rectangle([862, yy - 12, 930, yy - 4], fill="#e6eaee")

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, optimize=True)
print(f"Wrote {OUT}")
