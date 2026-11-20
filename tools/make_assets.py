import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "static", "images")
os.makedirs(IMAGES, exist_ok=True)

CREAM = (232, 223, 205)
SAND = (203, 180, 141)
SEA = (125, 154, 143)
DARK = (36, 44, 40)
TERRA = (185, 106, 54)
INK = (27, 30, 35)


def palm(draw, cx, cy, scale, color):
    pts_l, pts_r = [], []
    for i in range(18):
        t = i / 17
        x = cx + math.sin(t * 1.15) * 22 * scale
        y = cy - t * 190 * scale
        w = (9 - 5 * t) * scale
        pts_l.append((x - w, y))
        pts_r.append((x + w, y))
    draw.polygon(pts_l + list(reversed(pts_r)), fill=color)
    top_x = cx + math.sin(1.15) * 22 * scale
    top_y = cy - 190 * scale
    for angle, droop, length in [(-176, .55, 120), (-146, .75, 140), (-112, .95, 150), (-78, .85, 145), (-44, .65, 132), (-8, .45, 118), (164, .5, 108)]:
        a = math.radians(angle)
        spine = []
        for k in range(14):
            t = k / 13
            spine.append((top_x + math.cos(a) * length * scale * t,
                          top_y + math.sin(a) * length * scale * t * .45 + droop * 80 * scale * t ** 2.2))
        upper, lower = [], []
        for k, (x, y) in enumerate(spine):
            t = k / 13
            if k == 0:
                dx, dy = spine[1][0] - x, spine[1][1] - y
            elif k == 13:
                dx, dy = x - spine[k - 1][0], y - spine[k - 1][1]
            else:
                dx, dy = spine[k + 1][0] - spine[k - 1][0], spine[k + 1][1] - spine[k - 1][1]
            norm = math.hypot(dx, dy) or 1
            nx, ny = -dy / norm, dx / norm
            w = max(.8, (math.sin(math.pi * min(t * 1.2, 1)) ** .7) * 11) * scale
            upper.append((x + nx * w, y + ny * w))
            lower.append((x - nx * w, y - ny * w))
        draw.polygon(upper + list(reversed(lower)), fill=color)


def grain(img, amount=10):
    noise = Image.effect_noise(img.size, 24).convert("L")
    noise = noise.point(lambda v: 128 + int((v - 128) * amount / 60))
    return Image.blend(img, Image.merge("RGB", (noise, noise, noise)), .05)


def make_icon(size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * .2)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=CREAM)
    d.ellipse([size * .58, size * .14, size * .86, size * .42], fill=TERRA)
    d.rectangle([0, size * .72, size, size], fill=SEA)
    d.pieslice([0, size * .72, size, size], 0, 180, fill=SEA)
    d.ellipse([size * .1, size * .62, size * .78, size * .84], fill=DARK)
    palm(d, size * .38, size * .74, size / 512, DARK)
    img.save(os.path.join(IMAGES, "icon.png"))
    img.save(os.path.join(IMAGES, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(logo)
    ld.ellipse([0, 0, size - 1, size - 1], fill=CREAM)
    ld.ellipse([size * .58, size * .14, size * .86, size * .42], fill=TERRA)
    ld.pieslice([0, size * .72, size, size], 0, 180, fill=SEA)
    ld.ellipse([size * .1, size * .62, size * .78, size * .84], fill=DARK)
    palm(ld, size * .38, size * .74, size / 512, DARK)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    logo.putalpha(mask)
    logo.save(os.path.join(IMAGES, "logo.png"))


def scene_pines(w, h):
    img = Image.new("RGB", (w, h), (185, 192, 184))
    d = ImageDraw.Draw(img)
    d.polygon([(0, h * .58), (w * .28, h * .34), (w * .52, h * .52), (w * .74, h * .3), (w, h * .55), (w, h), (0, h)], fill=(126, 138, 128))
    d.polygon([(0, h * .72), (w * .34, h * .5), (w * .62, h * .72), (w, h * .6), (w, h), (0, h)], fill=(63, 76, 67))
    random.seed(3)
    for i in range(70):
        x = random.uniform(-40, w + 40)
        base = random.uniform(h * .62, h * .95)
        height = random.uniform(90, 240)
        color = (32, 42, 37) if base > h * .78 else (45, 57, 50)
        for k in range(3):
            spread = height * (.32 - k * .07)
            y0 = base - height * (.35 + k * .22)
            d.polygon([(x, y0 - height * .22), (x - spread, y0 + height * .18), (x + spread, y0 + height * .18)], fill=color)
        d.rectangle([x - 4, base - 6, x + 4, base + 30], fill=(28, 34, 30))
    d.rectangle([0, h * .9, w, h], fill=(28, 34, 30))
    return grain(img)


def scene_coast(w, h):
    img = Image.new("RGB", (w, h), (216, 210, 196))
    d = ImageDraw.Draw(img)
    d.rectangle([0, h * .58, w, h], fill=(127, 149, 160))
    d.rectangle([0, h * .58, w, h * .6], fill=(156, 175, 182))
    for i in range(5):
        y = h * (.62 + i * .07)
        d.rectangle([0, y, w, y + 6], fill=(142, 163, 172))
    d.polygon([(w * .55, h * .58), (w * .72, h * .3), (w * .9, h * .58)], fill=(58, 67, 74))
    d.polygon([(w * .62, h * .58), (w * .72, h * .38), (w * .84, h * .58)], fill=(74, 84, 90))
    d.rectangle([0, h * .74, w * .46, h], fill=(58, 67, 74))
    d.polygon([(0, h * .74), (w * .22, h * .66), (w * .46, h * .74), (w * .46, h)], fill=(47, 55, 61))
    return grain(img)


def scene_dunes(w, h):
    img = Image.new("RGB", (w, h), (221, 201, 168))
    d = ImageDraw.Draw(img)
    d.pieslice([-w * .2, -h * .3, w * .5, h * .7], 0, 360, fill=(207, 176, 128))
    layers = [(.46, (196, 163, 112)), (.56, (180, 145, 96)), (.68, (160, 126, 80)), (.8, (138, 106, 66))]
    for y, color in layers:
        d.polygon([(0, h * y), (w * .22, h * (y - .05)), (w * .5, h * (y + .02)), (w * .78, h * (y - .04)), (w, h * y), (w, h), (0, h)], fill=color)
    d.ellipse([w * .12, h * .18, w * .2, h * .26], fill=(240, 228, 205))
    return grain(img)


def scene_lake(w, h):
    img = Image.new("RGB", (w, h), (31, 40, 48))
    d = ImageDraw.Draw(img)
    d.ellipse([w * .68, h * .12, w * .82, h * .26], fill=(230, 224, 207))
    d.rectangle([0, h * .6, w, h], fill=(23, 33, 42))
    random.seed(9)
    for i in range(50):
        x = random.uniform(0, w)
        base = random.uniform(h * .58, h * .62)
        height = random.uniform(50, 150)
        color = (14, 21, 27)
        for k in range(3):
            spread = height * (.3 - k * .06)
            y0 = base - height * (.4 + k * .2)
            d.polygon([(x, y0 - height * .2), (x - spread, y0 + height * .15), (x + spread, y0 + height * .15)], fill=color)
    d.rectangle([0, h * .6, w, h * .61], fill=(46, 60, 70))
    return grain(img)


def make_backgrounds():
    w, h = 1600, 900
    scene_pines(w, h).save(os.path.join(IMAGES, "background_0.png"))
    scene_coast(w, h).save(os.path.join(IMAGES, "background_1.png"))
    scene_dunes(w, h).save(os.path.join(IMAGES, "background_2.png"))
    scene_lake(w, h).save(os.path.join(IMAGES, "background_3.png"))
    scene_pines(w, h).save(os.path.join(IMAGES, "background.png"))


def make_avatar():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cell = size // 8
    hair = (43, 27, 18, 255)
    skin = (198, 156, 109, 255)
    white = (245, 245, 245, 255)
    eye = (59, 93, 201, 255)
    mouth = (139, 90, 66, 255)
    rows = [
        [hair] * 8, [hair] * 8, [skin] * 8,
        [skin, skin, white, eye, skin, white, eye, skin],
        [skin] * 8,
        [skin, skin, skin, mouth, mouth, skin, skin, skin],
        [skin] * 8, [skin] * 8,
    ]
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            d.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1], fill=c)
    img.save(os.path.join(IMAGES, "avatar.png"))


def make_splash():
    w, h = 640, 360
    img = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 3, w, h], fill=(43, 47, 54))
    d.rectangle([0, h - 3, int(w * .35), h], fill=(201, 138, 63))
    logo = Image.open(os.path.join(IMAGES, "logo.png")).resize((96, 96), Image.LANCZOS)
    img.paste(logo, (44, 96), logo)
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        f1 = ImageFont.truetype(os.path.join(fonts, "segoeuib.ttf"), 30)
        f2 = ImageFont.truetype(os.path.join(fonts, "segoeui.ttf"), 13)
        f3 = ImageFont.truetype(os.path.join(fonts, "segoeui.ttf"), 12)
    except OSError:
        f1 = f2 = f3 = ImageFont.load_default()
    d.text((162, 112), "Paradise Island", font=f1, fill=(232, 235, 240))
    d.text((164, 154), "MINECRAFT LAUNCHER", font=f2, fill=(139, 146, 156))
    d.text((44, h - 40), "v3.0", font=f3, fill=(139, 146, 156))
    img.save(os.path.join(IMAGES, "splash.png"))


if __name__ == "__main__":
    make_icon()
    make_backgrounds()
    make_avatar()
    make_splash()
