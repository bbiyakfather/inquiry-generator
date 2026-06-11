# -*- coding: utf-8 -*-
"""앱 아이콘 생성 — 견적서 모티프 (둥근 타일 + 문서 + 직인).

브랜드 그라데이션(#3B5BFE→#7C5CFC) 타일 위에 모서리가 접힌 흰 견적서,
텍스트 라인 3개 + 금액 강조 라인, 우하단 빨간 직인 링.
1024px로 그려 다운샘플 → assets/icon.ico (256~16 멀티사이즈).
"""
import os

from PIL import Image, ImageDraw, ImageFilter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ICO = os.path.join(BASE, "assets", "icon.ico")
OUT_PNG = os.path.join(BASE, "assets", "icon_256.png")  # 미리보기/문서용

S = 1024                      # 마스터 해상도
BRAND = (59, 91, 254)         # #3B5BFE
VIOLET = (124, 92, 252)       # #7C5CFC
PAPER = (255, 255, 255)
FOLD = (223, 229, 255)        # 접힌 면
LINE = (201, 212, 242)        # 본문 라인
LINE_DARK = (148, 163, 216)   # 제목 라인
STAMP = (228, 77, 84)         # 직인 레드


def diagonal_gradient(size, c1, c2):
    """좌상→우하 대각 그라데이션 (저해상도 보간 후 확대 — 의존성 없음)."""
    n = 64
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
    return g.resize((size, size), Image.BICUBIC)


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=radius, fill=255)
    return m


def main():
    os.makedirs(os.path.dirname(OUT_ICO), exist_ok=True)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ── 배경 타일 (둥근 사각 + 브랜드 그라데이션)
    tile = diagonal_gradient(S, BRAND, VIOLET).convert("RGBA")
    img.paste(tile, (0, 0), rounded_mask(S, int(S * 0.225)))

    # ── 문서 좌표 (중앙, 약간 위)
    dw, dh = int(S * 0.50), int(S * 0.62)
    dx, dy = (S - dw) // 2, int(S * 0.165)
    fold = int(dw * 0.30)             # 접힌 모서리 크기
    r = int(S * 0.035)                # 문서 모서리 라운드

    # ── 그림자 (부드럽게)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [dx, dy + int(S * 0.018), dx + dw, dy + dh + int(S * 0.018)],
        radius=r, fill=(20, 30, 90, 110))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(S * 0.022)))

    d = ImageDraw.Draw(img)

    # ── 문서 본체 (우상단 모서리는 접힘 — 폴리곤으로 따냄)
    d.rounded_rectangle([dx, dy, dx + dw, dy + dh], radius=r, fill=PAPER)
    # 접힘 영역을 배경색으로 되돌린 뒤 접힌 삼각형을 얹음
    bg_patch = tile.crop((dx + dw - fold, dy, dx + dw, dy + fold))
    img.paste(bg_patch, (dx + dw - fold, dy))
    d = ImageDraw.Draw(img)
    d.polygon([(dx + dw - fold, dy), (dx + dw, dy + fold),
               (dx + dw - fold, dy + fold)], fill=PAPER)          # 본체 쪽
    d.polygon([(dx + dw - fold, dy), (dx + dw - fold, dy + fold),
               (dx + dw, dy + fold)], fill=FOLD)                  # 접힌 면
    # 접힌 면 경계 미세 라운딩 느낌의 사선 하이라이트
    d.line([(dx + dw - fold, dy), (dx + dw, dy + fold)],
           fill=(180, 192, 240), width=max(2, S // 256))

    # ── 텍스트 라인 (제목 1 + 본문 2 + 금액 강조 1)
    lx = dx + int(dw * 0.14)
    lw_full = int(dw * 0.72)
    lh = int(S * 0.030)
    gap = int(S * 0.072)
    ly = dy + int(dh * 0.20)
    d.rounded_rectangle([lx, ly, lx + int(lw_full * 0.55), ly + lh],
                        radius=lh // 2, fill=LINE_DARK)            # 제목(짧고 진함)
    for i in (1, 2):
        y = ly + gap * i
        d.rounded_rectangle([lx, y, lx + lw_full, y + lh],
                            radius=lh // 2, fill=LINE)
    # 금액 라인 (브랜드 컬러, 굵게)
    ay = ly + gap * 3 + int(S * 0.012)
    ah = int(lh * 1.5)
    d.rounded_rectangle([lx, ay, lx + int(lw_full * 0.62), ay + ah],
                        radius=ah // 2, fill=BRAND)

    # ── 직인 링 (우하단, 문서에 살짝 걸침)
    cx, cy = dx + dw - int(dw * 0.16), dy + dh - int(dh * 0.13)
    rad = int(S * 0.085)
    ring_w = int(S * 0.020)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
              outline=STAMP + (235,), width=ring_w)
    d.ellipse([cx - int(rad * 0.45), cy - int(rad * 0.45),
               cx + int(rad * 0.45), cy + int(rad * 0.45)],
              fill=STAMP + (215,))

    # ── 출력
    img256 = img.resize((256, 256), Image.LANCZOS)
    img256.save(OUT_PNG)
    img256.save(OUT_ICO, format="ICO",
                sizes=[(256, 256), (128, 128), (64, 64),
                       (48, 48), (32, 32), (16, 16)])
    print(f"OK → {OUT_ICO} ({os.path.getsize(OUT_ICO):,} bytes)")
    print(f"OK → {OUT_PNG}")


if __name__ == "__main__":
    main()
