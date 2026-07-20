# Tri Research Skill

> 三源并行搜索，一篇报告搞定。AnySearch通用 + Tavily深度 + SciVerse学术。

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-tri--research-blueviolet)](skills/tri-research/SKILL.md)
[![Framework-agnostic](https://img.shields.io/badge/Framework-agnostic-green)](skills/tri-research/SKILL.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](skills/tri-research/LICENSE)

## 一条命令安装

```bash
npx skills add jefeerzhang/tri-research-skill
```

## 它做什么？

为 Agent 提供深度研究能力：自动将研究问题拆分为多个子任务，并行派发子代理通过三个搜索后端（AnySearch + Tavily + SciVerse）检索信息，最终综合为一份带引用的 Markdown 报告。

**核心特性**：
- 🔍 **三源并行搜索**：AnySearch（通用+23垂直领域）+ Tavily（深度网页）+ SciVerse（学术论文）
- 🧩 **框架无关**：同一份技能适配 Claude Code、Codex、OpenCode 等任意支持子代理的框架
- 📊 **来源可信度分级**：Tier 1（权威）/ Tier 2（可信）/ Tier 3（补充）
- 🔄 **自动降级**：缺工具不报错，静默降级继续运行
- ⏱️ **8分钟超时**：子代理不会卡死

## 降级策略

装了就能跑，不需要先配工具：

| 可用工具数 | 行为 | 预期来源数 |
|-----------|------|-----------|
| 3个 | 三源全速 | ~39 |
| 2个 | 双源运行 | ~25-30 |
| 1个 | 单源运行 | ~10-15 |
| 0个 | 内置WebSearch | ~5-10 |

## 触发方式

```
tri-research 比较 AWS、Azure 和 Google Cloud 的计算实例定价
```

## 文件结构

```
skills/
├── tri-research/           # 主导代理（研究协调）
│   ├── SKILL.md
│   ├── README.md
│   ├── test-prompts.json
│   ├── CHANGELOG.md
│   └── LICENSE
├── research-subagent/      # 子代理（搜索执行）
│   └── SKILL.md
└── citations/              # 引用代理（添加引用）
    └── SKILL.md
```

## 实测数据

同一研究主题五轮迭代对比（来源数）：

| v1 (web_search) | v2 (抽象接口) | v3 (Tavily) | v4 (三源) | v5 (三源+约束) |
|:-:|:-:|:-:|:-:|:-:|
| 24 | 27 | 34 | 23 | **39** |

三源互补率：**67%**（26/39来源来自单一工具独占）

## License

MIT
