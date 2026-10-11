"""Render Provok's mark as PNGs for the Android app and the Play Store listing.

Usage (from apps/android): python tools/make_icons.py app/src/main/res play-store
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

BG, FOR, AGAINST, TEXT = (10, 10, 11, 255), (255, 90, 31, 255), (76, 111, 255, 255), (242, 239, 233, 255)
SS = 4  # supersampling factor


def mark(draw, cx, cy, radius, gap):
    """Two half circles (FOR left, AGAINST right) with a vertical gap."""
    box = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.pieslice(box, 90, 270, fill=FOR)
    draw.pieslice(box, 270, 90, fill=AGAINST)
    draw.rectangle([cx - gap / 2, cy - radius - 2, cx + gap / 2, cy + radius + 2], fill=(0, 0, 0, 0))


def icon(size, rounded=True, transparent_bg=False):
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not transparent_bg:
        if rounded:
            d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 112 / 512), fill=BG)
        else:
            d.rectangle([0, 0, s, s], fill=BG)
    # Cut the gap through to the background colour (or transparency for the splash).
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mark(ImageDraw.Draw(layer), s / 2, s / 2, s * 150 / 512, s * 22 / 512)
    img.alpha_composite(layer)
    return img.resize((size, size), Image.LANCZOS)


def feature_graphic(path):
    w, h = 1024 * SS // 2, 500 * SS // 2  # 2x is plenty for flat shapes
    img = Image.new("RGBA", (w, h), BG)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mark(ImageDraw.Draw(layer), w * 0.22, h / 2, h * 0.30, h * 0.03)
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    font_path = next((p for p in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(p)), None)
    big = ImageFont.truetype(font_path, int(h * 0.20)) if font_path else ImageFont.load_default()
    small = ImageFont.truetype(font_path.replace("b.ttf", ".ttf") if font_path else "", int(h * 0.075)) if font_path else big
    x, max_w = w * 0.40, w * 0.94 - w * 0.40
    lines = ["Debate humans and AI.", "The crowd votes. An AI judge decides."]
    size = int(h * 0.075)
    while font_path and max(d.textlength(t, font=small) for t in lines) > max_w:
        size -= 2
        small = ImageFont.truetype(font_path.replace("b.ttf", ".ttf"), size)
    d.text((x, h * 0.30), "PROVOK", font=big, fill=TEXT)
    d.text((x, h * 0.58), lines[0], font=small, fill=TEXT)
    d.text((x, h * 0.58 + size * 1.5), lines[1], font=small, fill=(201, 197, 188, 255))
    img.convert("RGB").resize((1024, 500), Image.LANCZOS).save(path)


def main(res_dir, store_dir):
    for density, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        out = os.path.join(res_dir, f"mipmap-{density}")
        os.makedirs(out, exist_ok=True)
        icon(px).save(os.path.join(out, "ic_launcher.png"))
    icon(288, transparent_bg=True).save(os.path.join(res_dir, "drawable", "splash.png"))
    os.makedirs(store_dir, exist_ok=True)
    icon(512, rounded=False).convert("RGB").save(os.path.join(store_dir, "icon-512.png"))  # Play applies its own mask
    feature_graphic(os.path.join(store_dir, "feature-graphic-1024x500.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
