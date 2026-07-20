# serpapi

> 搜完直接出可归档的 Markdown 研究报告，本机代理坑已填平——不用自己写爬虫，也不用和 CAPTCHA、反爬、SSL 握手较劲。

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-18C964)](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 你什么时候需要它？
- 想拿 **真实 Google / Bing / Baidu / YouTube / Amazon / Scholar** 搜索结果做研究、竞品监测、价格追踪，但不想写爬虫。
- 在本机跑 SerpApi 总报 `SSL UNEXPECTED_EOF` / 代理掐断——这个 skill 的 CLI 已自动清掉 `HTTP_PROXY`/`HTTPS_PROXY`。
- 想把搜索结果**落盘成报告**归档，而不是只看一眼终端输出。

## 它会交付什么？
- `search`：终端可读列表（序号 / 标题 / 链接 / 摘要），或 `--json` 出原始 JSON。
- `export`：一份 Markdown 研究报告，每条结果带标题、链接、摘要，自动存到 `data/output/<关键词>_检索结果.md`。

示例（中文，hl=zh-cn / gl=cn）：
```markdown
# 资产搁浅风险 - 检索结果
- 检索时间: 2026-07-20 02:37 UTC
- 引擎: google (hl=zh-cn, gl=cn)
- 结果数: 10

## 1. 搁浅资产与中国的燃煤发电——环境风险暴露分析
- 链接: https://www.nrdc.cn/information/informationinfo?id=179
- 摘要: 报告认为，中国煤电资产搁浅的成因（即风险指标）主要源于地方及国家层面的环境因素及气候政策……
```

## 快速开始
```bash
# 1. 装依赖（仅需 requests）
pip install requests

# 2. 配置 key（环境变量，避免明文落盘）
export SERPAPI_KEY="你的key"        # Linux/macOS
$env:SERPAPI_KEY="你的key"          # PowerShell

# 3. 跑一次
python <skill_dir>/scripts/serpapi_cli.py search --query "资产搁浅风险" --hl zh-cn --gl cn --num 10
```

获取免费 key：https://serpapi.com/dashboard （免费档 250 次/月，无需信用卡）。

## 触发方式（用户真实会说的话）
- "用 SerpApi 搜一下 XXX"
- "抓取谷歌结果 / 抓一下 Google Scholar"
- "把搜索结果存成文件 / 导出报告"
- "本机调 SerpApi 报 SSL 错，帮忙看看"

## 示例
```bash
# 基础搜索（打印）
python serpapi_cli.py search --query "OpenAI" --num 5

# 中文 + 地理定位
python serpapi_cli.py search --engine google --query "北京天气" --hl zh-cn --gl cn

# 学术搜索
python serpapi_cli.py search --engine google_scholar --query "transformer attention"

# 原始 JSON
python serpapi_cli.py search --query "python" --json > out.json

# 一键导出研究报告
python serpapi_cli.py export --query "资产搁浅风险" --hl zh-cn --gl cn --num 10
python serpapi_cli.py export --query "stranded assets" --out ./report.md

# 看支持的引擎
python serpapi_cli.py engines
```

## 它和同类有什么不同？
| 维度 | 官方 serpapi/skills (MCP) | 本 skill |
|---|---|---|
| 接入形态 | 托管 MCP server，一行接入 | 本地 Python CLI，零服务端 |
| 代理/SSL 坑 | 未特别处理 | 自动清除本机代理变量 |
| 结果落盘 | 需自己接 | 内置 `export` 出 Markdown 报告 |
| 中文场景 | 通用 | zh-cn / gl=cn 开箱即用 |

不重复造官方 MCP 的轮子——本 skill 主打**本机兼容 + 一键出报告**。

## 安全边界
- 只向 `https://serpapi.com/search` 发 GET 请求，不写、不改任何外部数据。
- 不删除、不覆盖用户文件；`export` 只新建/追加 `data/output/` 下的文件。
- 不收集密钥：key 仅从 `SERPAPI_KEY` 环境变量或 `--api_key` 读取，绝不写入日志或 stdout。
- 不是默认搜索源：SerpApi 不可用时停止并报错，不静默替代其他搜索方式。
- 查询内容会发送至 SerpApi 并触发计费（按次扣额度），避免用其查询含敏感信息的私密内容。

## 文件结构
- `SKILL.md` — 技能说明、触发条件、API key 指南、安全边界
- `scripts/serpapi_cli.py` — 跨平台 CLI（doc / search / export / engines）
- `.env.example` — key 模板（实际 key 请用环境变量，不要落盘）

## 验证与测试
```bash
# 应返回 HTTP 200 与 10 条结果
python serpapi_cli.py search --query "资产搁浅风险" --hl zh-cn --gl cn --num 10

# 应生成 data/output/资产搁浅风险_检索结果.md
python serpapi_cli.py export --query "资产搁浅风险" --hl zh-cn --gl cn --num 10
```
