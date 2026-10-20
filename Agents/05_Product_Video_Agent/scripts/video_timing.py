#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_timing.py — 05 Product Video Agent 的确定性算术层（TikTok Shop 泰国站）。

只算，不判断"写得好不好"：
  1. 逐句泰文字符数 → 预估时长（默认 12 字符/秒，可用 --cps 调；英文型号按词另算）
  2. 时间轴（每句起止 + 累计）
  3. 字幕行长（泰语不分词，默认 > 30 字符/行告警）
  4. 钩子检查（第一句 ≤ 3 秒，保证黄金开场窗口内说完）
  5. 总时长 vs 目标（15s / 30s / 60s，容差 ±15%）
  6. 无泰文字符的句子告警（泰国站字幕必须泰语为主）

输入：配音稿纯文本，一行 = 一句台词（一个分镜）。空行与 # 开头的注释行忽略。
零第三方依赖，Python 3.9+。

用法：
  python video_timing.py --script 配音稿.txt --target tiktok15
  python video_timing.py --script 配音稿.txt --target 30 --cps 12 --subtitle-max 30 --format json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- 常量

DEFAULT_CPS = 12.0           # 泰语口播语速：约 12 字符/秒（泰国市场经验值）
DEFAULT_WPS = 2.5            # 英文单词语速兜底（型号、品牌名串在泰语里时用）
DEFAULT_SUBTITLE_MAX = 30    # 单行字幕字符上限（泰语字号大、字符宽）
HOOK_MAX_SECONDS = 3.0       # 第一句钩子必须 3 秒内说完
TOLERANCE = 0.15             # 总时长相对目标的允许偏差 ±15%

THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
LATIN_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'._%-]*")

PLATFORM_TARGETS = {
    "tiktok15": 15, "tiktok30": 30, "tiktok60": 60,
    "15": 15, "30": 30, "60": 60,
}


# ---------------------------------------------------------------- 工具

def _out(msg: str) -> None:
    print(msg, flush=True)


def _fmt_sec(t: float) -> str:
    return f"{t:.1f}s"


def _load_lines(path: str) -> list[tuple[int, str]]:
    p = Path(path)
    if not p.exists():
        sys.exit(f"[INPUT_MISSING] 找不到配音稿文件：{path}")
    lines: list[tuple[int, str]] = []
    for i, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append((i, line))  # 保留源行号便于定位
    if not lines:
        sys.exit(f"[INPUT_MISSING] {path} 里没有有效台词（空行/注释行不计）。")
    return lines


def _emoji_hit(text: str) -> bool:
    """粗判：字符串里是否含 emoji / 符号码位字符（字幕里不该有）。"""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk") or ord(ch) >= 0x1F000:
            return True
    return False


def _count(text: str) -> tuple[int, int]:
    """泰语不分词 → 数字符；英文型号/品牌名 → 数单词。两段分别计时后相加。"""
    thai_chars = len(THAI_RE.findall(text))
    latin_words = len(LATIN_WORD_RE.findall(THAI_RE.sub(" ", text)))
    return thai_chars, latin_words


# ---------------------------------------------------------------- 核心计算

def analyze(lines: list[tuple[int, str]], cps: float, wps: float,
            subtitle_max: int) -> dict:
    rows, t = [], 0.0
    issues: list[str] = []
    for idx, (src_no, text) in enumerate(lines, 1):
        thai_chars, latin_words = _count(text)
        dur = ((thai_chars / cps if cps > 0 else 0.0)
               + (latin_words / wps if wps > 0 else 0.0))
        start, end = t, t + dur
        t = end
        row = {
            "index": idx,
            "source_line": src_no,
            "text": text,
            "thai_chars": thai_chars,
            "latin_words": latin_words,
            "est_seconds": round(dur, 2),
            "timeline": f"{_fmt_sec(start)} → {_fmt_sec(end)}",
            "subtitle_chars": len(text),
        }
        # 字幕行长
        if len(text) > subtitle_max:
            row["flag"] = f"字幕 {len(text)} 字符 > 上限 {subtitle_max}（建议拆两行或精简）"
            issues.append(f"第 {idx} 句：{row['flag']}")
        if _emoji_hit(text):
            row["flag"] = "疑似含 emoji/特殊符号，导出字幕时可能乱码"
            issues.append(f"第 {idx} 句：{row['flag']}")
        if thai_chars == 0:
            row["flag"] = "整句没有泰文字符（泰国站字幕应以泰语为主）"
            issues.append(f"第 {idx} 句：{row['flag']}")
        rows.append(row)

    # 钩子检查（第一句必须 3 秒内）
    hook_note = None
    if rows and rows[0]["est_seconds"] > HOOK_MAX_SECONDS:
        hook_note = (
            f"第一句 {rows[0]['thai_chars']} 个泰文字符，按 {cps} 字符/秒需 "
            f"{_fmt_sec(rows[0]['est_seconds'])}，超过 3 秒黄金开场窗口，建议精简钩子"
        )
        issues.append(hook_note)

    return {"rows": rows, "total_seconds": round(t, 2), "issues": issues,
            "hook_note": hook_note}


def target_check(total: float, target: float | None, cps: float) -> dict | None:
    if not target:
        return None
    lo, hi = target * (1 - TOLERANCE), target * (1 + TOLERANCE)
    ok = lo <= total <= hi
    return {
        "target": target,
        "window": f"{_fmt_sec(lo)} – {_fmt_sec(hi)}",
        "delta": round(total - target, 2),
        "pass": ok,
        "verdict": ("✅ 时长达标" if ok else
                    (f"❌ 偏短 {abs(total - target):.1f}s（内容不够，需加卖点句或放慢节奏）"
                     if total < lo else
                     f"❌ 超时 {total - target:.1f}s（需删句或提速，台词量按 {target}s×{cps} 字符/秒 ≈ {int(target * cps)} 个泰文字符上限裁）")),
    }


# ---------------------------------------------------------------- 输出

def to_markdown(res: dict, chk: dict | None, cps: float, wps: float,
                subtitle_max: int) -> str:
    L = ["# 配音时长与字幕校验报告（TikTok Shop 泰国站）\n"]
    L.append(f"- 语速假设：**{cps} 泰文字符/秒**（英文词按 {wps} 词/秒另计，可 --cps 调整）")
    L.append(f"- 字幕单行上限：**{subtitle_max} 字符**")
    L.append(f"- 总句数：**{len(res['rows'])}**")
    L.append(f"- 预估总时长：**{_fmt_sec(res['total_seconds'])}**")
    if chk:
        L.append(f"- 目标时长：{chk['target']}s（允许 {chk['window']}）→ **{chk['verdict']}**")
    L.append("")
    L.append("| # | 时间轴 | 泰文字符 | 英文词 | 预估时长 | 字幕字符 | 台词 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in res["rows"]:
        flag = f" ⚠️{r['flag']}" if "flag" in r else ""
        L.append(f"| {r['index']} | {r['timeline']} | {r['thai_chars']} | "
                 f"{r['latin_words']} | {_fmt_sec(r['est_seconds'])} | "
                 f"{r['subtitle_chars']} | "
                 f"{r['text'][:40]}{'…' if len(r['text']) > 40 else ''}{flag} |")
    L.append("")
    if res["hook_note"]:
        L.append(f"> 🪝 {res['hook_note']}\n")
    if res["issues"]:
        L.append(f"## 需要处理（{len(res['issues'])} 项）\n")
        for x in res["issues"]:
            L.append(f"- {x}")
    else:
        L.append("## 需要处理\n\n- 无 ✅（时长与字幕全部达标）")
    L.append("")
    L.append("> ⚠️ 预估时长基于均匀语速模型，**不能替代真人/配音工具的实际试听**。"
             "交付前按实际配音回听微调；泰语语速个体差异大，方言口播要单独试听一次。")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="配音时长与字幕校验（TikTok Shop 泰国站，确定性算术）")
    ap.add_argument("--script", required=True, help="配音稿文本：一行 = 一句台词")
    ap.add_argument("--target", help="目标秒数（15 / 30 / 60）或平台键 tiktok15/tiktok30")
    ap.add_argument("--cps", type=float, default=DEFAULT_CPS,
                    help=f"泰语语速，字符/秒（默认 {DEFAULT_CPS}）")
    ap.add_argument("--wps", type=float, default=DEFAULT_WPS,
                    help=f"英文词速，词/秒（默认 {DEFAULT_WPS}，仅用于混排的型号/品牌名）")
    ap.add_argument("--subtitle-max", type=int, default=DEFAULT_SUBTITLE_MAX,
                    help=f"单行字幕字符上限（默认 {DEFAULT_SUBTITLE_MAX}）")
    ap.add_argument("--format", choices=["md", "json", "both"], default="md")
    ap.add_argument("-o", "--output", help="输出文件前缀（默认仅打印）")
    args = ap.parse_args()

    lines = _load_lines(args.script)
    target = None
    if args.target:
        key = str(args.target).strip().lower()
        target = PLATFORM_TARGETS.get(key)
        if target is None:
            try:
                target = float(key)
            except ValueError:
                sys.exit(f"[INPUT_MISSING] 无法识别的目标时长：{args.target}"
                         f"（可用：{', '.join(sorted(PLATFORM_TARGETS))} 或任意秒数）")

    res = analyze(lines, args.cps, args.wps, args.subtitle_max)
    chk = target_check(res["total_seconds"], target, args.cps)

    md = to_markdown(res, chk, args.cps, args.wps, args.subtitle_max)
    payload = {
        "meta": {"platform": "tiktok_th", "cps": args.cps, "wps": args.wps,
                 "subtitle_max": args.subtitle_max, "target": target,
                 "total_seconds": res["total_seconds"], "lines": len(res["rows"])},
        "timeline": res["rows"],
        "target_check": chk,
        "issues": res["issues"],
    }

    if args.format in ("md", "both"):
        _out(md)
    if args.format in ("json", "both"):
        js = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.format == "json":
            _out(js)
    if args.output:
        pref = Path(args.output)
        if args.format in ("md", "both"):
            pref.with_suffix(".md").write_text(md, encoding="utf-8")
        if args.format in ("json", "both"):
            pref.with_suffix(".json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _out(f"\n已写出：{pref.with_suffix('.md')}" +
             (f" / {pref.with_suffix('.json')}" if args.format in ("json", "both") else ""))


if __name__ == "__main__":
    main()
