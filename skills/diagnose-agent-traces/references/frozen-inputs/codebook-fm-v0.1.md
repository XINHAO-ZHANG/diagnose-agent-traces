# Annotation output schema — `trajectory-v1 + fm-v0.1`（标注员必须输出的格式）

> 状态：**已冻结**（改任何一个字都要升版本号，比如 fm-v0.2，并重新跑受影响的 batch）。
> 依据：`skills/annotate-agent-trajectories/references/schema.md`（trajectory-v1）和 `protocol.md`。
> fm-v0.1 只在 trajectory-v1 上**加一层封闭的 failure-mode codebook**，原有字段一个都不改。
> 为什么要加这一层：现有 protocol 的 episode label 和 `inefficiency_candidate.label` 都是**自由文本**（protocol 写的是 "Do not force a vocabulary"），这种标签没法直接算 Cohen's kappa。fm-v0.1 是一个固定代码集，两个 annotator 都按它判断；自由标签照样保留在 `other_labels` 里，后面要做 `label_clusters.json` 时还能用。

## 1. 每个 level-attempt 必须产出的文件

沿用 skill 现有的目录结构（`runs/<run_id>/<game_id>/level_<n>/attempt_<n>/`）：

| 文件 | 状态 | 说明 |
|---|---|---|
| `records.json`, `actions.json` | 现有 | 照 trajectory-v1 不变 |
| `annotations.json` | 现有 + 新增 1 个顶层字段 | 新增 `failure_modes_unit`（对象，结构见 §3） |
| `review.html` | 现有，**本周可选** | 为了省 Codex 额度，A2 可以不生成 HTML |
| **`<out>/failure_modes.jsonl`** | **新增，必需** | 每个 level-attempt 一行，内容和 `failure_modes_unit` 一样，另外带上身份字段。`failure_mode_stats.py` 读的就是这个文件 |

**统计单位 = 一个 game-level attempt**（同一个 `run_id` + `game_id` + `level` + `attempt`）。没过关、被截断的 attempt 也必须写一行（schema.md 原话："Include failed/truncated attempts"）。

## 2. failure-mode codebook fm-v0.1（封闭集，6 个代码）

每个代码**都要显式给出** `present: true | false | null`。`null` 表示证据不足、判断不了，**不等于** false。

| Code | 定义（满足才标 true） | 不算的情况 | 来源 |
|---|---|---|---|
| `FM1_REPEATED_EXPLORATION` | 一个 probe 或假设已经被当时可见的证据解决了，agent 还是重复同样的尝试，而且没有提出新的假设或区分性目的 | 有明确理由的验证；换了条件的再测试；K 之前的正常探索 | BEHAVIOR_ANALYSIS_PLAN Q1；protocol "repeating a resolved probe" |
| `FM2_FEEDBACK_NOT_USED` | 环境已经返回了**能区分假设**的反馈（帧、状态、工具输出），但后续判断或行动没有采用，或者把它**读错了**（比如没变化读成有变化、坐标或颜色读错） | 反馈本身有歧义；模型根本看不到的信息（比如缺图）| Plan Q2；protocol "failing to use discriminating feedback"；unk_harness "feedback misinterpretation" |
| `FM3_NO_REVISION_AFTER_CONTRADICTION` | 存在某个 C（commitment）之后，出现了**明确反证**（失败或矛盾反馈），agent 却继续沿用原来的 model/plan，没有发生 R | 一次失败后合理的重试；还没有 C 的阶段（这种情况看 FM2）| Plan Q3；protocol R 的定义 |
| `FM4_POST_K_DELAY` | K（知识已经够用）之后，有证据表明 agent 没有利用这些知识：继续探索、反复确认、迟迟不执行（通常 D_K>0，或者 K 后又退回探索）| 必要的验证；D_K=0 的连续正确执行；K 只是低置信候选、而且有别的解释时 → 标 null | Plan Q4；protocol "continued exploration after K" |
| `FM5_EXECUTION_DEVIATION` | 计划已经确定，但落实到动作或代码时出错（plan-to-action conversion error），比如 unk_harness ar25 L7 坐标单位换算错了 | 计划本身就是错的（那是 knowledge 问题）；工具崩溃（那是 FM6）| Plan Q5；protocol "plan-to-action conversion error" |
| `FM6_TOOL_OR_STATE_ERROR` | 工具或代码报错（SyntaxError、IndexError 等）、超时续跑、状态需要修复，并且**占用了**可观察的动作或分析回合 | 报错但对过程没有影响（比如已经过关之后的报错，见 unk_harness B38）| protocol "tool-state repair"；unk_harness B11/B38 |

派生字段（统计脚本自动算，**不需要标注**）：`outcome_class` = `solved` / `unsolved_K_reached`（信息够了但没转化）/ `unsolved_no_K`（信息没拿全）/ `unsolved_K_unknown` / `unknown`。

判定规则：
1. 一个 unit 可以同时有多个代码（co-occurrence 本来就是要统计的东西）。
2. 每个 `present: true` 都要附上 ≥1 条 evidence（字段沿用 schema.md 的 Evidence object：精确 quote 或 observation），还要写 `episode_ids` 或 `steps`。
3. `cost_actions` 填这个模式占用的已执行动作数，**只在有依据时填**，否则填 null。它不代表"可避免的成本"。
4. 没把握标 true 时，宁可标 `null` 并写明理由，不要猜。
5. 自由标签（Probe、Control discovery 等）照旧写在 episodes 里，并在 `other_labels` 里列一份。

## 3. `failure_modes.jsonl` 行格式（字段表）

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `record_type` | `"failure_mode_unit"` | ✓ | |
| `schema_version` | `"trajectory-v1+fm-v0.1"` | ✓ | |
| `codebook_version` | `"fm-v0.1"` | ✓ | 统计脚本只接受和 `--codebook` 一致的行 |
| `prompt_version`, `prompt_sha256` | str | ✓ | 填 `annotator-prompt-v1.md` 文件的 sha256。**A1 和 A2 必须一致**，不一致时脚本会报警 |
| `annotator_id` | `"A1"` / `"A2"` / … | ✓ | |
| `annotator_model` | str 或 null | ✓ | 实际的模型 ID；拿不到就写 `"Unknown"` |
| `batch` | str | ✓ | 比如 `B1` |
| `blind` | bool | ✓ | 只有确实没看到其他 annotator 的输出时才写 true |
| `retrospective_exposure` | bool | ✓ | 标注时是否已经看过结局（读完整个 trace 就算看过；protocol 要求声明）|
| `run_id`, `harness`, `model`, `game_id`, `level`, `attempt` | | ✓（harness/model 可以填 `"Unknown"`）| 和 annotations.json 一致 |
| `source_ids` | [sha256] | ✓ | |
| `annotation_path` | str | 建议 | 对应 annotations.json 的相对路径 |
| `outcome` | `{cleared: bool/null, terminal_status: str, actions: int/null}` | ✓ | terminal_status 的取值：`cleared`、`stopped`、`timeout`、`gave_up`、`truncated`、`unknown` |
| `milestones` | `{K_status, K_completed_actions, K_confidence, S_status, S_completed_actions, n_C, n_R}` | ✓ | 状态取值沿用 observed/candidate/unknown/not_reached；位置不确定时填 null |
| `metrics` | `{A_K, P_C, D_K, A_KS, status}` | ✓ | 和 annotations.json 里的 `metrics.knowledge_utilization` 一致；null 必须有理由（理由写在 annotations.json 里）|
| `failure_modes` | object：6 个 code → `{present, confidence, episode_ids, steps, cost_actions, evidence, rationale}` | ✓ | present=false 时其余字段可以省略 |
| `other_labels` | [{label, episode_ids}] | 建议 | 自由标签 |
| `notes` | str | 可选 | |

JSON Schema：`failure_modes.schema.json`。模板：`failure_modes.template.jsonl`（只是模板，**不是数据**）。

## 4. 校验（统计脚本会自动做的部分）
- 缺必需字段的行、codebook 版本不匹配的行 → 丢弃，并写进 `validation.json`
- 缺 code → 当 null 处理并报警；`present: true` 但没有 evidence → 报警
- 同一个 annotator 对同一个 unit 有重复行 → 保留后一条并报警
- 同一个 annotator 用了多个 prompt 版本，或者 A1 和 A2 的 prompt hash 不一致 → 报警（agreement 就不能解释为"同一协议下的一致性"）
- `actions` 两边对不上 → 在 `milestone_agreement.csv` 里标出来（说明 unit 切分有分歧，要先解决这个再看 kappa）
