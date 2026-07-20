# Tri Research Skill

> 多元搜索并行、中英双补，一篇报告搞定。AnySearch通用 + Tavily深度 + SciVerse学术 + SerpApi中文Google/Scholar，可继续扩展。

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-tri--research-blueviolet)](SKILL.md)
[![Framework-agnostic](https://img.shields.io/badge/Framework-agnostic-green)](SKILL.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 你什么时候需要它？

- 要做一个需要 **10+来源** 的深度研究报告
- 要同时覆盖 **网页、学术论文、政策文件**
- 要在不同Agent框架间复用同一套研究逻辑

## 它会交付什么？

- 一份带引用的 Markdown 研究报告（`DEEP_RESEARCH_[TOPIC].md`）
- 15-40 个去重后的来源，按可信度分级（Tier 1/2/3）
- 来源溯源：每个来源标注由哪个搜索工具发现

## 快速开始

### 方式一：一条命令安装（推荐）

```bash
npx skills add <owner>/tri-research-skill
```

> 将 `<owner>` 替换为 GitHub 仓库所有者。安装后自动配置到支持的 Agent 框架。

### 方式二：手动安装

```bash
# 克隆仓库
git clone https://github.com/<owner>/tri-research-skill.git /tmp/tri-research

# 复制到技能目录
cp -r /tmp/tri-research/skills/* ~/.claude/skills/
```

### 搜索工具依赖（可选，有降级策略）

| 工具 | 类型 | 安装方式 |
|------|------|---------|
| [AnySearch](https://github.com/LearnPrompt/anysearch) | CLI Skill | `npx skills add LearnPrompt/anysearch` 或手动安装 |
| [Tavily](https://tavily.com) | MCP Server | 添加到 `~/.claude/mcp.json`，需要 API Key |
| SciVerse | MCP Server | OpenSpace MCP 或独立安装 |
| SerpApi | CLI Skill | 内置 `serpapi` skill（`scripts/serpapi_cli.py`）+ `SERPAPI_KEY` 环境变量；仅由主导代理集中调用，中英文 Google/Scholar 补强 |

### 降级原则

**装了技能就能跑，不需要先配工具。** 四个搜索工具是增强项，不是前置条件。技能会自动检测可用性并降级：

| 可用工具数 | 行为 | 用户体验 |
|-----------|------|---------|
| 4个 | 多元并行全速运行（SerpApi 由主导代理集中补强） | 最佳：最多来源，中英文/学术全覆盖 |
| 3个 | 静默跳过缺失工具 | 良好：约25-30来源 |
| 2个 | 静默跳过缺失工具 | 可用：约15-20来源 |
| 1个 | 单源搜索 | 可用：约10-15来源 |
| 0个 | 回退到内置WebSearch，仅提醒一次 | 基础：约5-10来源 |

> **SerpApi 特别说明**：免费档仅 250 次/月。它默认参与多元搜索，但配额耗尽或密钥缺失时**静默降级**到其余源，研究报告照常生成，不受影响。

**四个关键原则**：

1. **不打扰**：检测过程对用户透明，不需要用户参与任何配置检查
2. **不阻断**：缺工具不报错、不中断，降级后继续正常生成报告
3. **不唠叨**：全部不可用时只给一次轻量提醒（附 README 链接），不反复弹窗
4. **开箱即用**：装完技能直接 `tri-research <问题>` 就能跑，效果随配置提升

```
用户: tri-research <问题>
  ↓
主导代理自动检测（对用户透明）
  ├─ 4个可用 → 多元全速（最佳效果）
  ├─ 3个可用 → 其余源运行（静默跳过缺失）
  ├─ 2个可用 → 双源运行（静默跳过缺失）
  ├─ 1个可用 → 单源运行
  └─ 0个可用 → 提醒一次 + 内置WebSearch（不阻断）
  ↓
正常生成报告（来源数随可用工具递减，但流程始终完整）
```

### 触发研究

```
tri-research 比较 AWS、Azure 和 Google Cloud 的计算实例定价
```

## 触发方式

- `tri-research <研究问题>`
- `@tri-research <研究问题>`
- "帮我做一个深度研究：..."
- "用多元搜索研究一下..."

## 示例

**输入**：
```
tri-research 重污染行业上市公司资产搁搁浅风险
```

**输出**（约5000字报告）：
```markdown
# 深度研究：重污染行业上市公司资产搁浅风险

> 生成日期 2026-07-20 | 来源数: 39 | 搜索工具: AnySearch+Tavily+SciVerse

## TL;DR
资产搁浅风险是指因气候政策、技术变革导致资产提前减记的风险...

## Executive Summary
...（200-400字摘要）

## 1. 理论框架 [置信度: 高]
...（带引用 [1][2] 的正文）

## 参考文献
[1] Author — Title — URL — Tier: 1 — Found by: AnySearch
[2] ...
```

## 它和同类有什么不同？

| 特性 | 本Skill | GPT Researcher | Perplexity |
|------|---------|---------------|------------|
| 搜索源数 | **3（并行）** | 1 | 1 |
| 框架无关 | ✅ | ❌ | N/A |
| 学术论文覆盖 | ✅ SciVerse | 部分 | 部分 |
| 可定制子代理 | ✅ | ❌ | ❌ |
| 来源可信度分级 | ✅ Tier 1/2/3 | ❌ | ❌ |
| 降级策略 | ✅ 自动降级 | ❌ | N/A |

## 实测验证：五轮迭代对比

同一个研究主题（"重污染行业上市公司资产搁浅风险"）跑了5个版本，验证三源并行搜索的效果：

### 搜索工具演进

| 版本 | 搜索工具 | 改动说明 |
|------|---------|---------|
| v1 | `web_search` + `web_fetch` | 原始GitHub克隆，工具名写死 |
| v2 | 同v1（抽象接口映射） | 框架无关化重构，功能不变 |
| v3 | Tavily + SciVerse | 替换为深度搜索+学术搜索 |
| v4 | AnySearch + Tavily + SciVerse | 三源并行（无时间约束） |
| v5 | AnySearch + Tavily + SciVerse + 8min约束 | 三源并行 + 超时保护 |

### 核心指标对比

| 指标 | v1 | v2 | v3 | v4 | v5 |
|------|-----|-----|-----|-----|-----|
| 来源总数 | 24 | 27 | 34 | 23* | **39** |
| Tier 1 来源 | 16 | 18 | 22 | 17 | **25** |
| 2024-2025文献 | 3 | 5 | 12 | 8 | **15** |
| 顶刊文献 | 0 | 0 | 5 | 4 | **6** |
| 引用>100的文献 | 0 | 1 | 2 | 3 | **4** |
| 央行/监管文件 | 3 | 3 | 6 | 7 | **8** |
| 超时子代理 | 0 | 0 | 0 | 1 | **0** |

*v4的1个子代理因无时间约束被手动中止

### 三源互补性（v5数据）

v5的39个来源中，**67%来自单一工具独占**——说明三个搜索源互补性极强：

| 工具 | 独占来源 | 占比 | 代表来源 |
|------|---------|------|---------|
| AnySearch独占 | 12 | 31% | IEEE 2024, RMI中国, EY中国案例 |
| Tavily独占 | 6 | 15% | I4CE 2024, BPI 2025, Carbon Tracker |
| SciVerse独占 | 8 | 21% | Dietz 2016 NCC(638引), NBER, AI/ML 2025 |
| 多工具共同 | 13 | 33% | 交叉验证 |

### 关键发现

- **SciVerse独占的顶刊**：Dietz et al. (2016) *Nature Climate Change*（638次引用）、PNAS社会临界点研究（906次引用）——这些是Tavily和AnySearch搜不到的
- **AnySearch独占的监管文件**：BCBS巴塞尔委员会标准、ISSB工作人员文件、FSB路线图——这些是SciVerse搜不到的
- **Tavily独占的智库报告**：I4CE框架扩展研究、BPI的NGFS损害函数3倍膨胀分析——这些是其他工具搜不到的
- **8分钟约束有效**：v5的3个子代理全部在1.4-2.4分钟内完成，无超时

> 详细对比报告见 `COMPARISON_v1_v2_v3_v4_v5.md`

## 架构

```
用户: tri-research <问题>
  ↓
Lead Agent（主导代理）
  ├─ 分析查询 → 确定类型 → 制定计划
  ├─ 并行派发 2-6 个子代理
  │   ├─ Subagent 1 → AnySearch + Tavily + SciVerse → 报告
  │   ├─ Subagent 2 → AnySearch + Tavily + SciVerse → 报告
  │   └─ Subagent 3 → AnySearch + Tavily + SciVerse → 报告
  └─ 综合所有发现 → 最终报告
  ↓
Citations Agent（可选，添加引用）
```

## 安全边界

- 不会自动发布报告到外部服务
- 不会存储用户查询历史
- 搜索内容会发送到 AnySearch/Tavily/SciVerse API
- 子代理有8分钟超时限制，防止卡死

## 文件结构

```
tri-research/
├── SKILL.md              # 主导代理（研究协调）
├── README.md             # 本文件
├── test-prompts.json     # 测试用例
├── CHANGELOG.md          # 版本记录
├── LICENSE               # MIT License
research-subagent/
├── SKILL.md              # 子代理（搜索执行）
citations/
├── SKILL.md              # 引用代理（添加引用）
```

## License

MIT
