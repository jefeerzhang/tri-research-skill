# 可选交付：机制图嵌入与 LaTeX/PDF 渲染

tri-research 主 SKILL.md 的可选交付分支（推荐、不阻塞 `DONE`）。机制图 / PDF 都是**派生展示物**：md 是唯一真源，验证器不要求、不审计它们，不渲染无损，随时可重新生成。

## 机制图 / 结构图嵌入（推荐）

机制、概念、架构类研究若关系结构用图表达更清楚，可在**撰写阶段**调用 `drawio-skill` 生成一张图并嵌进报告 md：

- **用**：驱动→机制→结果这类因果链、多要素关系、流程/架构结构。
- **不用**：纯文献观点对比、事实问答、结论清单——图没有信息增量，不要为了有图而画。

步骤：

1. 调 `drawio-skill` 生成 `.drawio`，用其 `scripts/validate.py` 校验、draw.io CLI 导出 PNG
2. PNG 转 base64 data-URI 内嵌，报告保持**单文件自包含**：

   ```bash
   python -c "import base64,pathlib;print('data:image/png;base64,'+base64.b64encode(pathlib.Path('<图名>.png').read_bytes()).decode())"
   ```

   把输出粘贴进 `![图题](<data-URI>)`

3. 图放 `## 概述` 顶部或机制描述处，正文配一句文字指回（如「机制见图」）
4. 定稿后删除中间产物 `.drawio` / `.png` / `*.drawio.png`——图已内嵌，删除无坏链、无外部依赖

**防编造软规则**：图只能表达正文已出现的结论与关系，不得新增节点、数字或正反证据之外的联想链接；正文结论与图不一致是缺陷。

**done 之后补图**：md 已变，须重跑 `validate_report.py` + `done` 恢复 `INTEGRITY: OK`。

## 渲染 LaTeX/PDF（推荐）

`done` 之后用 `scripts/render_tex.py` 把报告渲成书样单文件 PDF：

```bash
python scripts/render_tex.py <报告路径>                        # 生成同名 .tex 并自动编译 .pdf
python scripts/render_tex.py <报告路径> --fonts-dir <字体目录> # 指定思源字体目录（含 SourceHanSerifCN-Regular.otf 等）
python scripts/render_tex.py <报告路径> --no-compile          # 只生成 .tex，不编译
```

- 内置 XeLaTeX + xeCJK 书样模板（5×8 英寸，思源/系统 CJK 字体可配、回退 Noto CJK），自包含
- **drawio 框架图排除**：渲染自动跳过报告里的机制图（`![...]` 图片行及 `*图：…*` 说明），PDF 不含中间产物机制图
- 探测到 xelatex 自动编译（`TRI_RESEARCH_XELATEX` / `XELATEX` → TinyTeX 路径 → PATH）；找不到则只出 `.tex` 并提示
- `.tex` 属中间产物可删除；交付以 md + pdf 为准

## TinyTeX 安装引导（PDF 编译引擎）

自动编译需要 `xelatex`。**TinyTeX** 是 TeX Live 轻量发行版（约百 MB、无需管理员、装进用户目录）；未装也能用（只产 `.tex`），装了才直接出 PDF：

| 平台        | 安装                                                                                                                               | 默认安装位置                                                   | 验证                 |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | -------------------- |
| Windows     | 下载 [install-bin-windows.bat](https://tinytex.yihui.org/install-bin-windows.bat) 双击运行（需 PowerShell）；或 Chocolatey / Scoop | `%APPDATA%/TinyTeX`（`C:\Users\<你>\AppData\Roaming\TinyTeX`） | `xelatex --version`  |
| macOS       | `curl -sL "https://tinytex.yihui.org/install-bin-unix.sh" \| sh`                                                                   | `~/Library/TinyTeX`                                            | `xelatex --version`  |
| Linux       | `wget -qO- "https://tinytex.yihui.org/install-bin-unix.sh" \| sh`                                                                  | `$HOME/.TinyTeX`                                               | `xelatex --version`  |
| R（全平台） | `install.packages('tinytex'); tinytex::install_tinytex()`                                                                          | 同上                                                           | `tinytex::xelatex()` |

脚本自动探测路径：`TRI_RESEARCH_XELATEX` / `XELATEX` 环境变量 → Windows `%APPDATA%\TinyTeX\bin\windows\xelatex.exe` → PATH。Windows 默认安装即可被自动找到；xelatex 在别处就设 `TRI_RESEARCH_XELATEX` 指向其可执行文件。

**缺宏包**：模板用到 `fontspec` / `xeCJK` / `booktabs` / `longtable` / `array` / `enumitem` / `hyperref` / `geometry` / `setspace` / `fancyhdr` / `xcolor` / `graphicx`。精简版缺包时 `tlmgr install <包名>` 补装（`tlmgr search --global --file "/<文件名>"` 可查归属包）。
