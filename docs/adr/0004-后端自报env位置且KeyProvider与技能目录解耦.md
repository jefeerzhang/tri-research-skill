# 后端自报 .env 位置，KeyProvider 与技能目录布局解耦

`KeyProvider.resolve` 内部写死两个候选路径（tri-research 的 `.env` 与兄弟 skill serpapi 的 `.env`，后者曾因多算一层 parent 指向不存在的 `<root>/serpapi/.env`，见 ADR-0003 期间的修复）；`serpapi_cli` 也反向写死 tri-research scripts 目录以 import 共享骨架。两个 skill 互相背得出对方的安装布局，新增后端必须修改公共 Key seam。

决定：`Backend` 新增 `env_file` 声明（与 `env_key` 并排），三个后端各自指向自家 `.env`；`KeyProvider.resolve` 删除全部硬编码候选，只读调用方递入的路径；`_search_cli._backend_api_key` 与 Registry 的 `_resolve_backend` / `check` 透传 `spec.backend.env_file`。

## Considered Options

- **连 import 耦合一起根治（打包重构）**：serpapi 反向 import `_search_cli` 依赖 `parents[2] / "tri-research" / "scripts"`；根治需把共享骨架做成可安装包并兼容 `~/.claude/skills/...` 等安装布局——伤筋动骨且当前可用，超出本轮最小爆炸半径（用户决策 A）。
- **保留硬编码候选作为兜底**：等于保留「后端忘申报就静默失去 `.env` 支持」的隐患来源，且布局知识仍泄漏在公共模块。
- **（采用）Backend 自报 `env_file`，KeyProvider 归零布局知识**：声明放在 `Backend`（与 `env_key` 并排）而非 `BackendSpec`，避免同一信息两处维护；`test_key_provider_resolve_knows_no_layout` 源码闸门防止技能名回流。

## Consequences

- 新增后端只需在自己的 `Backend` 上声明 `env_file`，不改公共代码。
- **行为收窄**：`SERPAPI_KEY` 碰巧写在 `skills/tri-research/.env` 不再被 serpapi 捞到（旧实现意外捎带）；各后端只认自家 `.env`。
- ADR-0003 的「sibling 候选路径」机制被本方案整体取代（含其修复）；`test_backend_key_resolution` 的兄弟路径钉子同步替换为「env_file 申报与生效」钉子。
- 剩余耦合（本次有意不动）：serpapi → tri-research scripts 的 import 路径；待打包重构时处理。
- 测试：`tests/test_backend_key_resolution.py`（env_file 端到端生效、三后端均已申报、resolve 源码无布局知识）。
