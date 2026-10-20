#!/usr/bin/env python3
"""像素级商品主图合规校验（TikTok Shop 泰国站）。

  python check_main_image.py 图.png --platform tiktok_th
  python check_main_image.py 图.png --platform tiktok_th --fix 修复后.png
  python check_main_image.py 图.png --platform tiktok_th --json

只依赖 Pillow。校验阈值来自 references/platform-tiktok-th.md 规则卡，不是拍脑袋。

检查项
  size_min        : 短边像素（TikTok 官方下限 600，推荐 1000+）
  square          : 宽高比 1:1（±1%，非正方形会被平台自动裁切）
  coverage        : 主体包围盒最长边 ÷ 图边（官方下限 60%，实战甜区 80–95%）
  white_bg        : 边缘 2% 带内近白像素占比（TikTok 推荐白底，纯色可接受 → 软提示）
  bg_uniformity   : 边缘带主色占比（背景是否干净）
  file_size       : 平台单图上限（TikTok 5MB）

--fix 自动修复：近白像素拉到纯白、补成正方形、按目标占比重排画布。
  （实景背景的"清理"需要抠图，脚本不做，会明确提示换纯色底。）
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

# 平台阈值（来源：references/platform-tiktok-th.md 规则卡）
PLATFORMS = {
    "tiktok_th": dict(
        min_px=600, rec_px=1000, cover_min=0.60, cover_lo=0.80, cover_hi=0.95,
        white_fail=None, white_warn=0.95, white_target=True,
        uniform_info=0.90, max_mb=5, fix_target=0.85,
    ),
}


def _min_channel(img):
    """每像素取 RGB 最小通道：dist = 255 - 该值，0 = 纯白。纯 Pillow 实现。"""
    r, g, b = img.convert("RGB").split()
    return ImageChops.darker(ImageChops.darker(r, g), b)


def _edge_strips(img, band_pct=0.02):
    """四条边缘带，用于估背景色与判背景是否干净。"""
    w, h = img.size
    band = max(2, round(min(w, h) * band_pct))
    return [img.crop((0, 0, w, band)), img.crop((0, h - band, w, h)),
            img.crop((0, 0, band, h)), img.crop((w - band, 0, w, h))]


def _bg_color(img, band_pct=0.02):
    """背景基准色 = 四条边缘带各自均色的中位数。

    为什么不直接用「近白」当背景：米白/浅灰/纯色底都会被误判成主体，
    导致主体占比恒为 100%、--fix 无从下手。用边缘色当基准，换任何纯色底都成立。
    """
    px = []
    for s in _edge_strips(img, band_pct):
        px.append(s.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0)))
    return tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))


def _product_bbox(img, bg, tol=18):
    """与背景基准色差异 > tol 的像素包围盒（无差异返回 None）。"""
    diff = ImageChops.difference(img.convert("RGB"),
                                 Image.new("RGB", img.size, bg)).convert("L")
    return diff.point([255 if v > tol else 0 for v in range(256)]).getbbox()


def _near_white_ratio(mc_img, tol):
    """近白像素占比（min channel >= 255-tol）。histogram 是 C 级实现，快。"""
    h = mc_img.histogram()
    total = sum(h)
    if not total:
        return 0.0
    return sum(h[256 - tol:]) / total


def analyse(img, plt_name, tol=3, product_thr=12, band_pct=0.02):
    p = PLATFORMS[plt_name]
    w, h = img.size
    mc = _min_channel(img)
    hist = mc.histogram()
    total = w * h

    # 主体包围盒：与边缘基准色差异明显（> product_thr）的像素
    bgc = _bg_color(img)
    bbox = _product_bbox(img, bgc, tol=product_thr)
    if bbox is None:
        return dict(width=w, height=h, coverage=0.0, bbox=None,
                    white_background=1.0, exact_ffffff=1.0, bg_uniformity=1.0)

    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    coverage = max(bw / w, bh / h)

    # 边缘 2% 带（四条），分别算近白占比与主色占比
    strips = _edge_strips(img, band_pct)
    mc_strips = [_min_channel(s) for s in strips]
    white_bg = sum(_near_white_ratio(m, tol) for m in mc_strips) / len(mc_strips)

    uni = []
    for s in strips:
        q = s.convert("RGB").quantize(colors=8)
        cols = q.getcolors(maxcolors=256) or []
        tot = sum(c for c, _ in cols)
        uni.append((max(c for c, _ in cols) / tot) if tot else 0.0)
    bg_uniformity = sum(uni) / len(uni)

    # 纯白占背景像素比（informational）
    product_px = sum(hist[:256 - product_thr])
    bg_px = total - product_px
    exact = (hist[255] / bg_px) if bg_px else 0.0

    return dict(width=w, height=h, coverage=round(coverage, 4), bbox=list(bbox),
                white_background=round(white_bg, 4), exact_ffffff=round(exact, 4),
                bg_uniformity=round(bg_uniformity, 4), bg_color=list(bgc))


def check(img, path, plt_name, args):
    p = PLATFORMS[plt_name]
    m = analyse(img, plt_name, tol=args.tolerance)
    res = []          # (级别, 检查项, 说明)

    def add(level, name, detail):
        res.append((level, name, detail))

    # 尺寸
    mn = min(m["width"], m["height"])
    if mn < p["min_px"]:
        add("FAIL", "size_min", f"{mn}px < 平台最低 {p['min_px']}px")
    elif mn < p["rec_px"]:
        add("WARN", "size_min", f"{mn}px 达最低但低于推荐 {p['rec_px']}px（缩放功能受限）")
    else:
        add("PASS", "size_min", f"{mn}px ≥ 推荐 {p['rec_px']}px")

    # 正方形
    ratio = abs(m["width"] - m["height"]) / max(m["width"], m["height"])
    if ratio > 0.01:
        add("FAIL", "square", f"{m['width']}×{m['height']} 非正方形（会被平台自动裁切）")
    else:
        add("PASS", "square", "1:1")

    # 主体占比
    c = m["coverage"]
    if c < p["cover_min"]:
        add("FAIL", "coverage", f"{c:.0%} < 平台下限 {p['cover_min']:.0%}")
    elif c < p["cover_lo"] or c > p["cover_hi"]:
        add("WARN", "coverage", f"{c:.0%} 超出甜区 {p['cover_lo']:.0%}–{p['cover_hi']:.0%}")
    else:
        add("PASS", "coverage", f"{c:.0%}")

    # 背景纯白（TikTok：推荐白底，纯色可接受 → 不给 FAIL）
    if p["white_fail"] is not None:
        wb = m["white_background"]
        if wb < p["white_fail"]:
            add("FAIL", "white_bg", f"边缘带近白 {wb:.1%} < {p['white_fail']:.0%}")
        elif wb < p["white_warn"]:
            add("WARN", "white_bg", f"边缘带近白 {wb:.1%}（接近但未达 {p['white_warn']:.0%}，常见于灰底/米底）")
        else:
            add("PASS", "white_bg", f"{wb:.1%}")
    elif p.get("white_target"):
        wb = m["white_background"]
        if wb < p["white_warn"]:
            add("WARN", "white_bg",
                f"边缘带近白 {wb:.1%} < {p['white_warn']:.0%} —— TikTok 推荐白底"
                f"（纯色可接受，但白底搜索表现更稳）")
        else:
            add("PASS", "white_bg", f"{wb:.1%} —— 白底")
    else:
        add("INFO", "white_bg", "该平台不校验背景色，跳过")

    # 背景均匀度（背景是否干净）
    u = m["bg_uniformity"]
    if u < 0.60:
        add("WARN", "bg_uniformity", f"边缘带主色仅 {u:.0%} —— 背景可能杂乱，换纯色底")
    elif u < p["uniform_info"]:
        add("WARN", "bg_uniformity", f"边缘带主色 {u:.0%}，背景略花")
    else:
        add("PASS", "bg_uniformity", f"{u:.0%} —— 背景干净")

    # 文件大小
    mb = os.path.getsize(path) / 1048576 if os.path.exists(path) else 0
    if mb > p["max_mb"]:
        add("FAIL", "file_size", f"{mb:.2f} MB > 上限 {p['max_mb']} MB")
    else:
        add("PASS", "file_size", f"{mb:.2f} MB ≤ {p['max_mb']} MB")

    # 无法自动检测的项 → 人工确认
    add("MANUAL", "cover_text", "首图禁文字/贴纸/促销角标/水印/第三方 Logo/边框 —— 人工确认")
    add("MANUAL", "sku_match", "图中颜色/款式必须与所售 SKU 一致（图文不符会判违规）—— 人工确认")

    ok = not any(lv == "FAIL" for lv, _, _ in res)
    return dict(platform=plt_name, ok=ok, metrics=m, checks=res)


def fix(img, plt_name, out_path, args):
    p = PLATFORMS[plt_name]
    target = p["fix_target"]
    w, h = img.size
    mc = _min_channel(img)

    # 1) 近白拉纯白（白底 / 推荐白底的平台）
    if p["white_fail"] is not None or p.get("white_target"):
        snap_tol = max(8, args.tolerance + 5)
        mask = mc.point([255 if v >= 255 - snap_tol else 0 for v in range(256)])
        white = Image.new("RGB", img.size, (255, 255, 255))
        img = Image.composite(white, img.convert("RGB"), mask)

    # 2) 按主体包围盒重排画布到目标占比
    bbox = _product_bbox(img, _bg_color(img), tol=max(12, args.tolerance + 9))
    if bbox:
        product = img.crop(bbox)
        pw, ph = product.size
        side = int(max(pw, ph) / target)
        canvas_bg = ((255, 255, 255)
                     if (p["white_fail"] is not None or p.get("white_target"))
                     else _dominant_bg(img, bbox))
        canvas = Image.new("RGB", (side, side), canvas_bg)
        canvas.paste(product, ((side - pw) // 2, (side - ph) // 2))
        img = canvas

    # 3) 放大到推荐尺寸
    rec = p["rec_px"]
    if img.size[0] < rec:
        img = img.resize((rec, rec), Image.LANCZOS)

    img.save(out_path, quality=92)
    return img


def _dominant_bg(img, bbox):
    """取包围盒外的主色，作为画布底色（保持原背景感）。"""
    w, h = img.size
    x0, y0, x1, y1 = bbox
    strips = [img.crop((0, 0, w, max(1, y0))), img.crop((0, y1, w, h)),
              img.crop((0, 0, max(1, x0), h)), img.crop((x1, 0, w, h))]
    strips = [s for s in strips if s.size[0] > 0 and s.size[1] > 0]
    if not strips:
        return (255, 255, 255)
    best, best_n = (255, 255, 255), -1
    for s in strips:
        q = s.convert("RGB").quantize(colors=4)
        pal = q.getpalette() or []
        for cnt, idx in (q.getcolors(maxcolors=8) or []):
            if cnt > best_n:
                best_n = cnt
                best = tuple(pal[idx * 3: idx * 3 + 3])
    return best


def main():
    ap = argparse.ArgumentParser(description="商品主图像素级合规校验")
    ap.add_argument("image")
    ap.add_argument("--platform", required=True, choices=list(PLATFORMS),
                    help="tiktok_th（TikTok Shop 泰国站）")
    ap.add_argument("--tolerance", type=int, default=3, help="近白判定容差（默认 3）")
    ap.add_argument("--fix", metavar="OUT", help="自动修复并保存到指定路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if not os.path.exists(args.image):
        sys.exit(f"[ERROR] 文件不存在：{args.image}")
    img = Image.open(args.image)

    report = check(img, args.image, args.platform, args)

    if args.fix:
        fixed = fix(img, args.platform, args.fix, args)
        re_report = check(fixed, args.fix, args.platform, args)
        report["fixed_to"] = args.fix
        report["after_fix_ok"] = re_report["ok"]
        report["after_fix_checks"] = re_report["checks"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ ", "MANUAL": "👤"}
        print(f"\n平台: {args.platform}   尺寸: {report['metrics']['width']}×"
              f"{report['metrics']['height']}   总判定: {'✅ 通过' if report['ok'] else '❌ 未通过'}\n")
        for lv, name, detail in report["checks"]:
            print(f"  {icon[lv]} {name:<16} {detail}")
        if args.fix:
            print(f"\n已修复 → {args.fix}   修复后判定: "
                  f"{'✅ 通过' if report.get('after_fix_ok') else '❌ 仍有 FAIL 项'}")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
