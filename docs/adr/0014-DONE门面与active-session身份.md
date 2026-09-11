# DONE 单一门面、证明/证据异常分类与 active-session 身份

W0–W4 收口了源名单、台账输入、档位、交付单元与检索拓扑。控制面仍有三处会漂：`Ledger*Error` 挂在 `ReportValidationError` 下（审计 P1-6），`state_machine.complete` 在 `proof.build_proof` 之外再跑一次 `audit_report`——编排层第二次解析报告（审计 P1-7），`citations` 另维护一份可与 `validate_report` 漂移的规则清单。并行会话还可能省略 `--session`、误打到被覆盖的 `active-session` 指针。决定：收口异常分类与 DONE 门面，citations 降为软层，并行会话强制显式身份。

- **`Ledger*Error` 不得继承 `ReportValidationError`**：台账指纹失败挂在专用 `EvidenceError` 下。报告格式失败走 Report Validation；台账 MISSING/MISMATCH 走 Evidence Error；`done` 溯源失败仍是 `EvidenceAuditFailed`（`StateError`，半句仍由 `audit` / `done` 各自追加）。
- **`complete()` 只调一个门面**：`proof.build_proof(..., audit=True)` 在同一调用里做结构验收、台账指纹、Evidence Audit。编排不再散落第二次 `parse_report`。DONE 语义不变（三者仍全要过）。
- **`citations` 是 `validate_report` 输出的薄解释层**：指向并运行验收器；**不**维护第二份章节/来源/URL 清单。
- **并行会话必须显式 `--session`**：`active-session` 指针只服务单会话回退。本波 **不加** 指针锁——`start` 已在 per-session `write_lock` 内写指针，`resolve_session` 读指针尚无 session id；指针锁与会话锁嵌套会形成锁序反转。身份问题要靠 SKILL + 合约测试，不是第二把锁。

## Considered Options

- **维持 `Ledger*Error(ReportValidationError)`**：被拒——台账字节对不上不是报告格式问题；捕获 `ReportValidationError` 的调用方会把两种修复路径（改报告 vs 查台账）揉成一类。
- **把 `Ledger*Error` 挂到 `ProofError` 下**：被拒——`proof.py` 已 import `evidence.py`，反向再挂基类会成环；`ProofError` 仍是证明生命周期的捕获面（`require_complete` / `verify_integrity`），台账半区由门面译成 `ProofMissingError` / `ProofTamperedError`。独立 `EvidenceError` 切断与 Report Validation 的继承。
- **`complete()` 继续先 `build_proof` 再手调 `audit_report`**：被拒——两处各 parse 一次报告，门禁顺序靠编排纪律而不是门面契约。
- **把报告验收与溯源合并成单一 `completion_gate`**：被拒——与 ADR-0005 相同理由：失败语义与修复路径不同（改报告 vs 补台账）。门面只编排，不发明宽接口。
- **citations 继续内嵌八条规则、冲突时「以 validate_report 为准」**：被拒——第二份清单仍能与代码漂移；Agent 可能按 SKILL 的过时条款改报告。
- **废弃 citations skill**：不选——软层对人话解释仍有用；收口成「去跑验收器」即可。
- **给 `active-session` 加专用锁**：被拒——锁序反转风险（读指针时尚无 `session_id`）；并发写指针已由 PID 临时名 + `os.replace` 重试覆盖（见既有并发测试）。并行会话的故障是**打错身份**，锁防不了省略 `--session`。
- **（采用）`EvidenceError` + `build_proof(audit=True)` + citations 薄解释层 + SKILL 强制显式 `--session`**：结构收紧，DONE / INTEGRITY / 单会话回退行为不变。

## Consequences

- `evidence.LedgerIntegrityError` 改挂 `EvidenceError`；不再是 `ReportValidationError` 子类。`proof.verify_integrity` 仍把台账半区译成 `ProofMissingError` / `ProofTamperedError`（`marker` 不变）。
- `proof.build_proof(..., audit=True)` 在指纹之后跑 `audit_report`；默认 `audit=False` 保留库调用方（测试 / 只建据）。`complete()` 传 `audit=True`，本身不再 import `audit_report`。
- `citations/SKILL.md` 只解释如何跑 `validate_report.py` 以及如何读它的失败行；合约测试禁止它独立枚举七章或六源名单。
- SKILL / CONTEXT：并行 Research Session 的每条 `state_machine` / `evidence` / Machine 检索命令必须带 `--session`；省略只合法于单会话。
- 不在本 ADR 落地：打包（ADR-0015）、改 usage roster / required backends、重绘 `architecture.json`、给指针加锁、改 `EvidenceAuditFailed` 的 `StateError` 身份。
- 测试：异常继承闸门、`build_proof(audit=True)` 行为、`complete()` 源码只调门面、citations / 并行 `--session` 合约钉子。
