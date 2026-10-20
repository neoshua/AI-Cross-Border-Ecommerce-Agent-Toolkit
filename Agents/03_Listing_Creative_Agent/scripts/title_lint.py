#!/usr/bin/env python3
"""标题合规校验（TikTok Shop 泰国站）—— 字符数是实测值，不是估算。

  python title_lint.py "标题文本" --platform tiktok_th
  python title_lint.py 标题.txt --platform tiktok_th --forbidden iPhone,Samsung
  python title_lint.py "标题" --platform tiktok_th --keywords กระเป๋า,กันน้ำ

检查项（阈值来自 references/platform-title-rules.md 规则卡，口径见 TikTok Shop Academy）：
  length        : 25–255 字符（字符数，非字节数；低于 25 也是不达标）
  visible40     : 移动端首屏可见段（供人工确认主关键词是否前置）
  forbidden     : 禁用词命中（未授权品牌词、绝对化用语等）
  keywords      : 核心关键词覆盖（缺了哪些词）
  emoji         : 表情/非常规符号（TikTok 禁特殊字符）
  all_caps      : 全大写单词（禁堆砌大写）
  promo_words   : 促销/免运/折扣词 → FAIL；畅销/独家等绝对化 → WARN
  variant_stock : 变体数量/库存状态表述（官方列为标题质量问题）
  duplicates    : 同一词语重复 ≥4 次（官方口径，不是 3 次）
  second_hand   : 泰国站二手商品标题必须以 [Second-hand] 开头
  locale        : 中文字符混入 → FAIL；整条无泰文字符 → WARN
"""
import argparse
import json
import re
import sys

PLATFORMS = {
    "tiktok_th": dict(limit=255, min_len=25, visible_n=40, promo="fail"),
    "tiktok": dict(limit=255, min_len=25, visible_n=40, promo="fail"),
}

# 促销 / 免运 / 折扣 —— TikTok 明确不允许出现在标题
PROMO_HARD = [
    "ส่งฟรี", "ฟรีส่ง", "ฟรีค่าส่ง", "โปรโมชั่น", "โปรโมชัน", "ลดราคา",
    "ราคาพิเศษ", "ของแถม", "แถมฟรี", "ลดล้างสต็อก", "flash sale",
    "free shipping", "promotion", "discount", "sale", "包邮", "免费", "促销", "特价",
]

# 绝对化 / 畅销宣称 —— 官方列为「标题党式表达」，降权风险
PROMO_SOFT = [
    "ถูกที่สุด", "ดีที่สุด", "ขายดีที่สุด", "ขายดี", "อันดับ 1", "อันดับ1",
    "no.1", "number one", "best seller", "bestseller", "cheapest", "hot item",
    "全网最低", "最好", "第一",
]

# 变体数量 / 库存状态 —— 官方明确列为标题质量问题
VARIANT_STOCK = [
    r"\d+\s*(สี|ขนาด|แบบ)\b", r"(มี|มีทั้งหมด)\s*\d+\s*(สี|ขนาด)",
    r"available\s+in", r"\d+\s*sizes?\s+available", r"in\s+stock",
    r"พร้อมส่ง", r"สินค้าพร้อมส่ง", r"เหลือ\s*\d+",
]

EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
SECOND_HAND_RE = re.compile(r"มือสอง|มือ\s*2|second[- ]?hand", re.I)


def _repeat_hits(text, max_rep=3):
    """泰语无空格，先按空格切词统计；没空格时用 6 字滑窗兜底，再按位置合并重叠片段。"""
    # ① 按空格分词（泰国卖家普遍用空格分隔短语）
    toks = [w for w in re.split(r"\s+", text) if len(w) >= 4 and THAI_RE.search(w)]
    hit_toks = [w for w in dict.fromkeys(toks) if toks.count(w) > max_rep]
    if hit_toks:
        return hit_toks[:3]

    # ② 兜底：长片段滑窗（由长到短，命中即停）+ 位置合并
    for L in (12, 10, 8, 6):
        cands = {}
        for run in re.findall(r"[\u0E00-\u0E7F]{%d,}" % L, text):
            for i in range(len(run) - L + 1):
                cands.setdefault(run[i:i + L], []).append(i)
        reps = {k: v for k, v in cands.items() if len(v) > max_rep}
        if not reps:
            continue
        accepted, spans = [], []
        for frag in sorted(reps, key=lambda k: -len(reps[k])):
            s = text.find(frag)
            e = s + len(frag)
            if any(not (e <= a or s >= b) for a, b in spans):
                continue
            accepted.append(frag)
            spans.append((s, e))
            if len(accepted) >= 3:
                break
        if accepted:
            return accepted
    return []


def analyse(title, platform, args):
    p = PLATFORMS[platform]
    res = []   # (级别, 检查项, 说明)
    t = title.strip()
    n = len(t)   # Python 字符串长度 = 字符数（非字节）

    # 1) 长度：25–255 双向
    if n > p["limit"]:
        res.append(("FAIL", "length", f"{n} 字符 > 平台上限 {p['limit']} —— 超出部分会被截断"))
    elif n < p["min_len"]:
        res.append(("FAIL", "length", f"{n} 字符 < 平台下限 {p['min_len']} —— 信息量不足，官方判不合格"))
    else:
        res.append(("PASS", "length", f"{n}/{p['limit']} 字符（下限 {p['min_len']}）"))

    # 2) 移动端首屏可见段
    if p["visible_n"]:
        res.append(("INFO", "visible40", f"「{t[:p['visible_n']]}」← 前 {p['visible_n']} 字符，主关键词放这里"))

    # 3) 禁用词
    forbidden = args.forbidden or []
    if isinstance(forbidden, str):
        forbidden = [w.strip() for w in forbidden.split(",") if w.strip()]
    if args.forbidden_file:
        try:
            with open(args.forbidden_file, encoding="utf-8") as f:
                forbidden += [ln.strip() for ln in f if ln.strip()]
        except OSError as e:
            res.append(("WARN", "forbidden", f"禁用词文件读不了：{e}"))
    hits = [w for w in forbidden if w and w.lower() in t.lower()]
    if hits:
        res.append(("FAIL", "forbidden", f"命中禁用词：{'、'.join(hits)}（未授权品牌词/绝对化用语会有下架风险）"))
    elif forbidden:
        res.append(("PASS", "forbidden", f"0 命中（查了 {len(forbidden)} 个词）"))

    # 4) 关键词覆盖
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        missing = [k for k in kws if k.lower() not in t.lower()]
        if missing:
            res.append(("WARN", "keywords", f"核心词未覆盖：{'、'.join(missing)}"))
        else:
            res.append(("PASS", "keywords", f"{len(kws)} 个核心词全覆盖"))

    # 5) 表情 / 特殊符号
    if EMOJI_RE.search(t):
        res.append(("FAIL", "emoji", f"发现表情/符号：{EMOJI_RE.findall(t)[:5]}（TikTok 禁特殊字符）"))

    # 6) 全大写单词
    caps = [w for w in re.findall(r"[A-Za-z]{4,}", t) if w.isupper()]
    if caps:
        res.append(("WARN", "all_caps", f"全大写词：{'、'.join(caps[:6])}（仅品牌缩写可接受）"))

    # 7) 促销词（硬禁）/ 绝对化宣称（警告）
    hard = [w for w in PROMO_HARD if w.lower() in t.lower()]
    if hard:
        res.append(("FAIL", "promo_words", f"促销/免运词：{'、'.join(hard)}（TikTok 标题禁促销信息，挪到主图角标或描述）"))
    soft = [w for w in PROMO_SOFT if w.lower() in t.lower()]
    if soft:
        res.append(("WARN", "promo_words", f"绝对化/畅销宣称：{'、'.join(soft)}（官方列为标题党式表达，降权风险）"))

    # 8) 变体数量 / 库存状态
    vs = [pat for pat in VARIANT_STOCK if re.search(pat, t, re.I)]
    if vs:
        res.append(("WARN", "variant_stock",
                    f"含变体/库存表述（命中 {len(vs)} 条规则）—— 官方列为标题质量问题，"
                    f"规格差异应放变体（SKU）而不是标题"))

    # 9) 重复词堆砌（TikTok 口径：同一词语 ≥4 次）
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", t.lower())
    dup = [w for w in set(words) if words.count(w) > 3 and len(w) > 2]
    dup += _repeat_hits(t)
    if dup:
        res.append(("FAIL", "duplicates", f"重复 ≥4 次：{'、'.join(dup[:6])}（关键词堆砌降权）"))

    # 10) 泰国站二手商品前缀
    if SECOND_HAND_RE.search(t) and not t.lower().startswith("[second-hand]"):
        res.append(("FAIL", "second_hand",
                    "泰国站二手商品标题必须以 [Second-hand] 开头（官方强制）"))

    # 11) 语言
    if CJK_RE.search(t):
        res.append(("FAIL", "locale", "标题含中文字符 —— 泰国站买家可见文本必须是泰语"))
    elif not THAI_RE.search(t):
        res.append(("WARN", "locale", "整条标题没有泰文字符 —— 泰国站建议泰语为主，英文/品牌词为辅"))

    ok = not any(lv == "FAIL" for lv, _, _ in res)
    return dict(platform=platform, chars=n, limit=p["limit"], ok=ok, checks=res,
                first_40=t[:40])


def main():
    ap = argparse.ArgumentParser(description="标题合规校验（TikTok Shop 泰国站，字符数实测）")
    ap.add_argument("title", nargs="?", help="标题文本；或用 --file 传入")
    ap.add_argument("--file", help="从文件读标题（一行一个，逐条校验）")
    ap.add_argument("--platform", required=True, choices=list(PLATFORMS))
    ap.add_argument("--forbidden", help="禁用词，逗号分隔（品牌词/绝对化用语）")
    ap.add_argument("--forbidden-file", help="禁用词文件（每行一个）")
    ap.add_argument("--keywords", help="核心关键词，逗号分隔（查覆盖）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    titles = []
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                titles = [ln.strip() for ln in f if ln.strip()]
        except OSError as e:
            sys.exit(f"[ERROR] 读不了文件：{e}")
    elif args.title:
        titles = [args.title]
    else:
        sys.exit("[ERROR] 给标题文本或 --file")

    reports = [analyse(t, args.platform, args) for t in titles]
    all_ok = all(r["ok"] for r in reports)

    if args.json:
        print(json.dumps(reports if len(reports) > 1 else reports[0],
                         ensure_ascii=False, indent=2))
    else:
        for r in reports:
            icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ "}
            print(f"\n「{r['first_40']}{'…' if r['chars'] > 40 else ''}」"
                  f"  [{r['platform']}  {r['chars']}/{r['limit']} 字符]"
                  f"  总判定: {'✅ 通过' if r['ok'] else '❌ 未通过'}")
            for lv, name, detail in r["checks"]:
                print(f"  {icon[lv]} {name:<12} {detail}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
