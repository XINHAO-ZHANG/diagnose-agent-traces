# Codebooks (frozen: rw-v0.1 and fm-v0.1)

## Reasoning-waste categories (rw-v0.1), one set of shares per turn

The shares of a turn add up to 1.0. The annotator does not label single sentences.

| Category | Meaning | Example |
|---|---|---|
| Productive | Reads new feedback. Forms or tests a hypothesis that can be true or false. Makes a plan that the agent executes. | "Let me do them one at a time" (single-click tests). |
| Over-deliberation | The action is trivial or already decided. The agent keeps weighing it. | The agent checks the bar cap, the drain rate and the death condition again. It already observed all three. |
| Re-derive | The agent derives again a fact that is already in the trace. | "Let me re-track positions". |
| Board re-describe | The agent lists objects, colors or positions again. It adds no new conclusion. | "Let me list all w pixels." |
| Discarded plan | The agent builds a plan or hypothesis and drops it. No test and no action follow. A turn that ends with no action also counts. | "Let me step back and think about the game from a fresh perspective…", then ideas with no test. |
| Lock-in batch | The agent trusts a rule that it did not test. It plans many actions on it. The batch later fails. | "let me do attempt 1 + SPACE in one call". |
| Tool debug | The agent reasons about a code error, an API call or a repair of the state. | `AttributeError: 'HistoryEntryView' object has no attribute 'step'`. |
| Unclear | The annotator cannot judge. | |

A wrong hypothesis is productive when the agent tests it with a clear experiment.

## Failure modes (fm-v0.1), one value per level

Each code is true, false or null. Null means "the trace is not enough". It does not mean false.
"True" needs one exact quote or one clear observation, a step range and a short reason.
One level can have several codes.

| Code | True when | Not this |
|---|---|---|
| FM1 Repeated exploration | A probe or hypothesis is already answered by evidence in the trace. The agent repeats it with no new idea. | A check with a reason. A test under changed conditions. Normal exploration before the key knowledge. |
| FM2 Feedback not used | The environment gave a result that separates the hypotheses. The later reasoning or action ignores it or reads it wrongly. | Ambiguous feedback. Information the model cannot see. |
| FM3 No revision after contradiction | The agent committed to a plan. A result clearly contradicts it. The agent keeps the plan. | One reasonable retry after one failure. Phases with no commitment yet (that is FM2). |
| FM4 Delay after key insight | The agent has the knowledge to solve the level. It keeps exploring, re-checking or waiting. | A needed check. Continuous correct execution. |
| FM5 Execution differs from plan | The plan is settled. The conversion to actions or code is wrong (for example a wrong unit). | A wrong plan (a knowledge problem). A tool crash (FM6). |
| FM6 Tool or state error | A code error, a timeout or a state repair uses up turns or actions. | An error with no effect on the process. |

`cost_actions` is the number of actions that the pattern used.
Fill it only when the trace shows the number.
It does not mean "actions we could have saved".

FM6 is mostly the turn-budget yield. This is a harness event. It is not a reasoning failure.

## Trust in the 2026-10-08 data

| Item | Trust |
|---|---|
| Not-productive total | Yes. Two model families agree within about 7 points. |
| Over-deliberation as the largest category | Yes. Two families agree. |
| Order of the other categories | No. Kappa near 0 between families. |
| FM2, FM6 | Yes. Kappa 0.69 and 0.96. |
| FM3, FM4, FM5 | No. Kappa 0.38, 0.37, 0.47, and few cases. |
