---
name: sop-ecom-listing-lint
description: >-
  Listing 合规校验 Skill：标题字符数实测（字符非字节）、禁用词命中、核心词覆盖、
  促销词/表情/堆砌检测、参数一致性溯源（文案里每个数字必须能对上 spec_table）。
  当用户要检查标题、查超限、查禁用词、查参数漂移、上架前自检时使用。
  中文「标题查一下 / 合规检查 / 参数对不对」同样触发。
  NOT for 写标题写详情页（那是 03 主流程的活）、生图（04）。
allowed-tools:
  - Bash(python *)
  - Read
metadata:
  version: 0.4.0
  category: e-commerce/listing-compliance
  license: MIT
---

# 03 · Listing Compliance Skill（下限守卫）

> **定位**：守住 Listing 的**下限** —— 不超字、不被截断、不踩禁用词、参数不漂移。
> **上限**（点不点得动）不归它管，那要上架看真实 CTR。

---

## 快速开始

```bash
# 标题校验（字符数是实测值）
python scripts/title_lint.py "标题文本" --platform tiktok_th \
    --forbidden "iPhone,Samsung" --keywords "กระเป๋าเป้,กันน้ำ,20นิ้ว"

# 参数一致性：文案里每个数字必须溯源到 spec_table
python scripts/spec_consistency.py --spec examples/spec_table.csv --text 详情页文案.md

# 标题 + 详情一起校验
python scripts/spec_consistency.py --spec examples/spec_table.csv \
    --title "标题" --text 详情页文案.md
```

---

## 检查项

### title_lint.py（按平台规则卡）

| 检查 | 阈值 / 行为 | 级别 |
|---|---|---|
| 字符长度 | **25–255**（低于 25 也算不达标） | ❌ FAIL |
| 前 40 字符 | 单独输出（移动端首屏可见段，主关键词必须在这） | ℹ️ INFO |
| 促销词 | `ส่งฟรี` / `ลดราคา` / `โปรโมชั่น` / sale … | ❌ FAIL |
| 绝对化宣称 | `ถูกที่สุด` / `ขายดีที่สุด` / best seller … | ⚠️ WARN |
| 表情符号 | emoji 与装饰性特殊字符 | ❌ FAIL |
| 全大写堆砌 | 品牌缩写以外的全大写词 | ⚠️ WARN |
| 重复词 **≥4 次** | 有空格按分词统计，无空格用 12/10/8/6 字滑窗兜底 | ❌ FAIL |
| 变体 / 库存表述 | `มี 5 สี` / `in stock` / `พร้อมส่ง` | ⚠️ WARN |
| 二手商品前缀 | 泰国站强制 `[Second-hand]` 开头 | ❌ FAIL |
| 中文字符混入 | 买家可见文本必须是泰语 | ❌ FAIL |
| 无泰文字符 | 纯英文标题拿不到自然流量 | ⚠️ WARN |
| 禁用词 | 自备清单（未授权品牌词 / 类目敏感词） | ❌ FAIL |
| 核心词覆盖 | 缺词提醒 | ⚠️ WARN |

### spec_consistency.py

| 检查 | 说明 |
|---|---|
| **参数漂移** | 文案里每个数字溯源到 spec_table；溯不到 = 笔误/编造/口径不一致 |
| **参数漏讲** | spec_table 里有数字的参数在文案中从未出现 → 提醒补内容 |

支持泰国数字格式（`20.000` = 20000）与 `--allow` 豁免（年份等无关常量）。

---

## 规则卡

- [references/platform-title-rules.md](references/platform-title-rules.md) —— 字数/禁项/堆砌规则的出处与阈值
- 案例数据：[examples/spec_table.csv](examples/spec_table.csv)（充电宝参数表）

## 已知限制

| 限制 | 说明 |
|---|---|
| 图内文字不检测 | 主图/详情图的叠字合规归 04 的 `check_main_image.py`（像素级） |
| 禁用词清单要自备 | 平台不公开完整违禁词表；用 03 合规扫描 Prompt 的输出喂给 `--forbidden` |
| 只校验不生成 | 写标题请回 03 主流程 Prompt；本 Skill 是发布前最后一道闸 |
