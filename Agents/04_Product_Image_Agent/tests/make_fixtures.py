#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 04 模块的测试夹具（TikTok Shop 泰国站阈值）。

  python make_fixtures.py            # 在脚本所在目录生成 5 张合成图

每张图埋一个已知的合规项 / 违规项，配合 check_main_image.py --platform tiktok_th 使用。
阈值依据 references/platform-tiktok-th.md：
  1:1 / ≥600px（推荐 1000+）/ 主体 ≥60%（甜区 80–95%）/ 白底推荐 / ≤5MB
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
WHITE = (255, 255, 255)


def _subject(img: Image.Image, ratio: float, color=(46, 96, 168)) -> Image.Image:
    """在图上画一个边长占 ratio 的方块（模拟商品主体）。"""
    d = ImageDraw.Draw(img)
    w, h = img.size
    side = int(min(w, h) * ratio)
    x0, y0 = (w - side) // 2, (h - side) // 2
    d.rounded_rectangle([x0, y0, x0 + side, y0 + side], radius=side // 12, fill=color)
    return img


def build(out_dir: Path = OUT) -> None:
    # ① 完全合规：1200 纯白底，主体 85%
    img = Image.new("RGB", (1200, 1200), WHITE)
    _subject(img, 0.85).save(out_dir / "th_pass.png")

    # ② 主体过小：1200 纯白底，主体 45%（< 60% 下限）
    img = Image.new("RGB", (1200, 1200), WHITE)
    _subject(img, 0.45).save(out_dir / "th_coverage_fail.png")

    # ③ 非正方形：1100×1000，主体 85%
    img = Image.new("RGB", (1100, 1000), WHITE)
    _subject(img, 0.85).save(out_dir / "th_square_fail.png")

    # ④ 待修复：900 米白底 + 主体 55%（尺寸、背景、占比三项都不达标）
    img = Image.new("RGB", (900, 900), (250, 248, 240))
    _subject(img, 0.55).save(out_dir / "th_fix.png")

    # ⑤ 背景杂乱：1000×1000，边缘散布噪声块
    img = Image.new("RGB", (1000, 1000), WHITE)
    d = ImageDraw.Draw(img)
    for i in range(0, 1000, 40):
        d.rectangle([i, 0, i + 20, 30], fill=(120, 120, 120))
        d.rectangle([i, 970, i + 20, 1000], fill=(90, 90, 90))
        d.rectangle([0, i, 30, i + 20], fill=(160, 160, 160))
        d.rectangle([970, i, 1000, i + 20], fill=(140, 140, 140))
    _subject(img, 0.80, (46, 96, 168)).save(out_dir / "th_chaotic.png")

    print(f"已生成 5 张夹具 → {out_dir}")


if __name__ == "__main__":
    build()
