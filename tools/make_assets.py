"""生成启动器使用的图片资源（图标、背景、默认头像）。

用法：python tools/make_assets.py
"""
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "static", "images")
os.makedirs(IMAGES, exist_ok=True)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        c = lerp(top, bottom, y / max(h - 1, 1))
        px[0, y] = c
    return img.resize((w, h), Image.BILINEAR)


def radial_glow(size, center, radius, color, strength=120):
    w, h = size
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 28
    for i in range(steps, 0, -1):
        r = radius * i / steps
        alpha = int(strength * (1 - i / steps) ** 1.7)
        d.ellipse([cx - r, cy - r * 0.85, cx + r, cy + r * 0.85], fill=alpha)
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.35))
    glow = Image.new("RGB", (w, h), color)
    out = Image.new("RGB", (w, h), (0, 0, 0))
    out.paste(glow, (0, 0), layer)
    return out


def add_glow(base, center, radius, color, strength=120):
    glow = radial_glow(base.size, center, radius, color, strength)
    return ImageChops.add(base.convert("RGB"), glow)


def star_field(img, count=220, seed=7):
    random.seed(seed)
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    for _ in range(count):
        x = random.uniform(0, w)
        y = random.uniform(0, h * 0.75)
        r = random.choice([0.6, 0.8, 1.0, 1.3, 1.8])
        a = random.randint(40, 170)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
    return img


def multi_gradient(size, stops):
    w, h = size
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                k = (t - p0) / (p1 - p0) if p1 > p0 else 0
                px[0, y] = lerp(c0, c1, k)
                break
    return img.resize((w, h), Image.BILINEAR)


def make_hero_background():
    """黄昏海岛场景，作为默认主页背景。"""
    W, H = 1920, 1080
    horizon = int(H * 0.64)
    img = multi_gradient((W, H), [
        (0.0, (14, 12, 38)),
        (0.30, (52, 30, 84)),
        (0.52, (150, 66, 112)),
        (0.62, (238, 118, 96)),
        (0.66, (255, 156, 110)),
        (1.0, (18, 14, 40)),
    ])

    # 太阳与光晕
    sun_c = (1180, int(H * 0.585))
    img = add_glow(img, sun_c, 620, (255, 138, 90), 90)
    img = add_glow(img, sun_c, 260, (255, 214, 150), 120)
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([sun_c[0] - 108, sun_c[1] - 108, sun_c[0] + 108, sun_c[1] + 108], fill=(255, 236, 196, 255))

    # 云带
    clouds = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(clouds)
    for i, (cy, cw, alpha) in enumerate([(250, 520, 26), (330, 680, 34), (430, 560, 30), (520, 760, 24)]):
        for k in range(4):
            cx = 260 + i * 180 + k * 320
            cd.ellipse([cx - cw // 2, cy - 26, cx + cw // 2, cy + 26], fill=(255, 214, 190, alpha))
    clouds = clouds.filter(ImageFilter.GaussianBlur(26))
    img = Image.alpha_composite(img.convert("RGBA"), clouds).convert("RGB")

    # 海面
    sea = multi_gradient((W, H - horizon), [
        (0.0, (250, 150, 110)),
        (0.25, (150, 74, 96)),
        (0.6, (58, 34, 74)),
        (1.0, (16, 14, 40)),
    ])
    img.paste(sea, (0, horizon))

    # 阳光在水面的倒影
    refl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(refl)
    for i in range(26):
        t = i / 25
        y = horizon + t * (H - horizon)
        w = 220 * (1 - t * 0.75) + 18
        alpha = int(90 * (1 - t) ** 1.3)
        rd.ellipse([sun_c[0] - w, y - 6, sun_c[0] + w, y + 6], fill=(255, 222, 170, alpha))
    refl = refl.filter(ImageFilter.GaussianBlur(9))
    img = Image.alpha_composite(img.convert("RGBA"), refl).convert("RGB")

    # 前景岛屿与棕榈树
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([-460, horizon + 120, 900, H + 240], fill=(11, 10, 26, 255))
    d.ellipse([1180, horizon + 180, 2300, H + 300], fill=(11, 10, 26, 255))
    d.polygon([(0, H), (0, horizon + 250), (620, horizon + 320), (760, H)], fill=(11, 10, 26, 255))
    palm(d, 330, horizon + 250, 1.65, (11, 10, 26, 255))
    palm(d, 560, horizon + 310, 1.05, (11, 10, 26, 255))
    palm(d, 1690, horizon + 300, 1.35, (11, 10, 26, 255))

    # 星点
    img = star_field(img, 130, 31)

    # 暗角
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-W * 0.25, -H * 0.3, W * 1.25, H * 1.3], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(240))
    dark = Image.new("RGB", (W, H), (4, 4, 14))
    img = Image.composite(img, dark, vignette)
    img.save(os.path.join(IMAGES, "background_0.png"))
    img.save(os.path.join(IMAGES, "background.png"))


def make_backgrounds():
    W, H = 1920, 1080

    # 1 极光
    aurora = Image.new("RGB", (W, H), (6, 20, 26))
    d = ImageDraw.Draw(aurora, "RGBA")
    for i in range(9):
        color = [(34, 211, 238, 60), (16, 185, 129, 55), (99, 102, 241, 50), (45, 212, 191, 45)][i % 4]
        base_y = 260 + i * 70
        points = []
        for x in range(0, W + 20, 20):
            y = base_y + math.sin(x / 220 + i) * 120 + math.sin(x / 70 + i * 2) * 18
            points.append((x, y))
        for k in range(len(points) - 1):
            x1, y1 = points[k]
            x2, y2 = points[k + 1]
            d.polygon([(x1, y1), (x2, y2), (x2, y2 + 170), (x1, y1 + 170)], fill=color)
    aurora = aurora.filter(ImageFilter.GaussianBlur(26))
    base = vertical_gradient((W, H), (4, 12, 18), (8, 24, 30))
    aurora = Image.blend(base, aurora, 0.85)
    aurora = star_field(aurora, 160, 23)
    aurora.save(os.path.join(IMAGES, "background_1.png"))

    # 2 日落海岛
    img = vertical_gradient((W, H), (36, 16, 66), (255, 126, 95))
    img = add_glow(img, (960, 760), 560, (255, 190, 120), 150)
    img = add_glow(img, (960, 760), 260, (255, 236, 190), 190)
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([760, 620, 1160, 780], fill=(255, 226, 168, 235))
    d.ellipse([-200, 900, 1100, 1400], fill=(24, 18, 46, 255))
    d.ellipse([900, 940, 2300, 1500], fill=(18, 14, 38, 255))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(os.path.join(IMAGES, "background_2.png"))

    # 3 深海
    img = vertical_gradient((W, H), (5, 20, 40), (10, 63, 92))
    img = add_glow(img, (500, 180), 700, (56, 189, 248), 70)
    img = add_glow(img, (1400, 900), 800, (14, 116, 144), 60)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(7):
        x = 120 + i * 300
        d.polygon([(x, 0), (x + 90, 0), (x - 260, H), (x - 420, H)], fill=(120, 220, 255, 8))
    img.save(os.path.join(IMAGES, "background_3.png"))

    # 兼容旧命名
    img0 = Image.open(os.path.join(IMAGES, "background_0.png"))
    img0.save(os.path.join(IMAGES, "background.png"))


def palm(draw, cx, cy, scale, color):
    """在 (cx, cy) 处画一棵棕榈树剪影（cy 为树根位置）。"""
    pts_l, pts_r = [], []
    for i in range(21):
        t = i / 20
        x = cx + math.sin(t * 1.2) * 26 * scale
        y = cy - t * 205 * scale
        w = (11 - 6 * t) * scale
        pts_l.append((x - w, y))
        pts_r.append((x + w, y))
    draw.polygon(pts_l + list(reversed(pts_r)), fill=color)

    top_x = cx + math.sin(1.2) * 26 * scale
    top_y = cy - 205 * scale
    leaves = [
        (-178, 0.55, 150), (-150, 0.78, 170), (-118, 0.95, 182), (-86, 0.9, 178),
        (-54, 0.7, 164), (-22, 0.5, 146), (6, 0.35, 128), (168, 0.45, 132),
    ]
    for angle_deg, droop, length in leaves:
        a = math.radians(angle_deg)
        spine = []
        steps = 18
        for k in range(steps):
            t = k / (steps - 1)
            x = top_x + math.cos(a) * length * scale * t
            y = top_y + math.sin(a) * length * scale * t * 0.45 + droop * 105 * scale * (t ** 2.2)
            spine.append((x, y))
        upper, lower = [], []
        for k, (x, y) in enumerate(spine):
            t = k / (steps - 1)
            if k == 0:
                dx, dy = spine[1][0] - x, spine[1][1] - y
            elif k == steps - 1:
                dx, dy = x - spine[k - 1][0], y - spine[k - 1][1]
            else:
                dx, dy = spine[k + 1][0] - spine[k - 1][0], spine[k + 1][1] - spine[k - 1][1]
            norm = math.hypot(dx, dy) or 1
            nx, ny = -dy / norm, dx / norm
            w = max(0.9, (math.sin(math.pi * min(t * 1.22, 1.0)) ** 0.65) * 14) * scale
            upper.append((x + nx * w, y + ny * w))
            lower.append((x - nx * w, y - ny * w))
        draw.polygon(upper + list(reversed(lower)), fill=color)


def make_splash():
    W, H = 640, 360
    img = multi_gradient((W, H), [
        (0.0, (10, 16, 30)),
        (0.55, (18, 28, 52)),
        (1.0, (9, 13, 26)),
    ])
    img = add_glow(img, (120, 70), 320, (99, 102, 241), 70)
    img = add_glow(img, (560, 320), 300, (34, 211, 238), 40)
    img = img.convert("RGBA")
    logo = Image.open(os.path.join(IMAGES, "logo.png")).resize((104, 104), Image.LANCZOS)
    img.alpha_composite(logo, (52, 74))

    from PIL import ImageFont
    font_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    bold = os.path.join(font_dir, "segoeuib.ttf")
    regular = os.path.join(font_dir, "segoeui.ttf")
    try:
        f_title = ImageFont.truetype(bold, 34)
        f_sub = ImageFont.truetype(bold, 13)
        f_small = ImageFont.truetype(regular, 12)
    except OSError:
        f_title = f_sub = f_small = ImageFont.load_default()

    d = ImageDraw.Draw(img)
    d.text((184, 92), "Paradise Island", font=f_title, fill=(240, 244, 252, 255))
    d.text((186, 138), "L  A  U  N  C  H  E  R", font=f_sub, fill=(148, 163, 184, 255))
    d.text((186, 160), "v2.3", font=f_small, fill=(107, 124, 150, 255))
    # 底部等待提示与进度条
    d.rounded_rectangle([52, 268, 588, 274], radius=3, fill=(30, 41, 60, 255))
    d.rounded_rectangle([52, 268, 300, 274], radius=3, fill=(99, 102, 241, 255))
    d.text((52, 292), "Starting, please wait...", font=f_small, fill=(148, 163, 184, 255))
    img.convert("RGB").save(os.path.join(IMAGES, "splash.png"))


def make_icon(size=512):
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 圆角方形渐变底
    bg = vertical_gradient((S, S), (56, 189, 248), (79, 70, 229))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.235), fill=255)
    img.paste(bg, (0, 0), mask)
    # 顶部高光
    highlight = radial_glow((S, S), (int(S * 0.28), int(S * 0.16)), int(S * 0.55), (255, 255, 255), 70)
    img = ImageChops.add(img.convert("RGB"), highlight).convert("RGBA")
    img.putalpha(mask)
    d = ImageDraw.Draw(img, "RGBA")
    # 太阳
    d.ellipse([S * 0.58, S * 0.16, S * 0.86, S * 0.44], fill=(253, 230, 138, 255))
    d.ellipse([S * 0.60, S * 0.18, S * 0.84, S * 0.42], fill=(254, 240, 190, 255))
    # 海水
    d.ellipse([-S * 0.25, S * 0.62, S * 1.25, S * 1.18], fill=(37, 99, 235, 210))
    # 小岛
    d.ellipse([S * 0.16, S * 0.58, S * 0.72, S * 0.80], fill=(15, 23, 42, 255))
    # 棕榈树
    palm(d, S * 0.44, S * 0.70, S / 512, (15, 23, 42, 255))
    img.save(os.path.join(IMAGES, "icon.png"))

    # ICO（多尺寸）
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(os.path.join(IMAGES, "icon.ico"), sizes=sizes)

    # 透明 Logo（仅图形）
    logo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo, "RGBA")
    d.ellipse([S * 0.06, S * 0.06, S * 0.94, S * 0.94], fill=(56, 189, 248, 255))
    d.ellipse([S * 0.58, S * 0.16, S * 0.86, S * 0.44], fill=(253, 230, 138, 255))
    d.ellipse([-S * 0.25, S * 0.62, S * 1.25, S * 1.18], fill=(37, 99, 235, 255))
    d.ellipse([S * 0.16, S * 0.58, S * 0.72, S * 0.80], fill=(15, 23, 42, 255))
    palm(d, S * 0.42, S * 0.70, S / 512, (15, 23, 42, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, S - 1, S - 1], fill=255)
    logo.putalpha(mask)
    logo.save(os.path.join(IMAGES, "logo.png"))
    return img


def make_avatar():
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cell = S // 8
    hair = (43, 27, 18, 255)
    skin = (198, 156, 109, 255)
    white = (245, 245, 245, 255)
    eye = (59, 93, 201, 255)
    mouth = (139, 90, 66, 255)
    rows = [
        [hair] * 8,
        [hair] * 8,
        [skin] * 8,
        [skin, skin, white, eye, skin, white, eye, skin],
        [skin, skin, skin, skin, skin, skin, skin, skin],
        [skin, skin, skin, mouth, mouth, skin, skin, skin],
        [skin] * 8,
        [skin] * 8,
    ]
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            d.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1], fill=c)
    img.save(os.path.join(IMAGES, "avatar.png"))


if __name__ == "__main__":
    make_hero_background()
    make_backgrounds()
    make_icon()
    make_avatar()
    make_splash()
    print("assets generated in", IMAGES)
