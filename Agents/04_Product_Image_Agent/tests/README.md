# 04 · check_main_image.py 测试夹具（TikTok Shop 泰国站）

5 张合成图，**每张都埋了已知的合规项与违规项**。
clone 下来跑一遍，输出与下表一致 = 校验脚本工作正常。

夹具由 [`make_fixtures.py`](./make_fixtures.py) 生成（纯 Pillow，可重跑复现）：

```bash
python make_fixtures.py
```

---

## 怎么跑

```bash
cd Agents/04_Product_Image_Agent/scripts

python check_main_image.py ../tests/th_pass.png           --platform tiktok_th   # 预期 ✅
python check_main_image.py ../tests/th_coverage_fail.png --platform tiktok_th   # 预期 ❌ coverage
python check_main_image.py ../tests/th_square_fail.png   --platform tiktok_th   # 预期 ❌ square
python check_main_image.py ../tests/th_chaotic.png       --platform tiktok_th   # 预期 ⚠️ 三项
python check_main_image.py ../tests/th_fix.png           --platform tiktok_th --fix ../tests/th_fixed.png
```

---

## 夹具清单与实测结果（2026-10-20）

| 夹具 | 构造 | 预期 | 实测 |
|---|---|---|---|
| `th_pass.png` | 1200×1200 纯白底，主体 85% | ✅ 通过 | ✅ size 1200 · square 1:1 · coverage 85% · white_bg 100% · bg_uniformity 100% · 0.01MB |
| `th_coverage_fail.png` | 1200×1200 纯白底，主体 **45%** | ❌ coverage | ❌ coverage 45% < 60%（其余全过） |
| `th_square_fail.png` | **1100×1000** 非正方形，主体 85% | ❌ square | ❌ square 1100×1000 非正方形（其余全过） |
| `th_chaotic.png` | 1000×1000，边缘散布噪声块，主体 80% | ⚠️ 背景项告警 | ⚠️ white_bg 46% · ⚠️ bg_uniformity 52% · ⚠️ coverage 100%\* |
| `th_fix.png` | 900×900 米白底 `#FAF8F0`，主体 **55%** | ❌ coverage + ⚠️ 尺寸/背景 | ❌ coverage 55% < 60% · ⚠️ size 900 < 1000 · ⚠️ white_bg 0% |
| `th_fixed.png` | 上者经 `--fix` 输出 | ✅ 通过 | ✅ coverage 85% · 白底 · 1000px（尺寸/背景/占比三项一次修好） |

> **\* 关于 `th_chaotic` 的 coverage=100%**：占比用「与边缘基准色差异明显」的像素包围盒测量，
> 噪声本身就贴着边缘 → 包围盒被撑满全图。**杂乱背景下包围盒占比法必然失效** —— 这不是 bug，
> 恰恰是脚本同时输出 `bg_uniformity` 告警的原因：背景花掉的图，占比数字不可信，先清背景再谈占比。

---

## 这组夹具覆盖了什么

| 能力 | 被哪张验证 |
|---|---|
| 纯白底 + 合规占比的正常通过路径 | `th_pass` |
| 主体占比跌破官方 60% 下限 | `th_coverage_fail` |
| 非正方形检测（会被平台自动裁切） | `th_square_fail` |
| 背景杂乱的双重告警（近白率 + 主色占比） | `th_chaotic` |
| **非白纯色底**（米白/浅灰）不被误判成主体 | `th_fix`（改前用近白判定时占比会误报 100%） |
| `--fix` 同时修尺寸、背景、占比 | `th_fix` → `th_fixed` |
| 首图文字/水印/SKU 一致性 | **不测**（需 OCR 与实物比对，列为人工确认项） |

**不覆盖**：图内文字占比（需 OCR）、真实产品照片（夹具为合成图，只测几何与颜色）。

---

**脚本**：[`scripts/check_main_image.py`](../scripts/check_main_image.py) · **规则卡**：[TikTok Shop 泰国站](../references/platform-tiktok-th.md) · **夹具生成**：[`make_fixtures.py`](./make_fixtures.py)
