# diagnose-agent-traces

An agent skill that finds **where an ARC-AGI-3 agent run loses time**, from the transcripts folder of the run.

You give your agent (Claude Code, Codex, Cursor) the folder of a run. The agent counts the time, labels the reasoning,
compares the run with a baseline, and gives you an English report.

## What you get

`REPORT.md` with:
- **Counted results (no model):** the share of wall-clock in turns with no action, turn-budget yields, read timeouts, actions on the levels that both runs cleared.
- **Reasoning waste:** for each turn, how much of the reasoning is productive, over-deliberation, re-derive, board re-describe, discarded plan, lock-in batch or tool debug.
- **Failure modes:** six codes for each level (repeated exploration, feedback not used, no revision after contradiction, delay after key insight, execution differs from plan, tool or state error).
- **A comparison** with a baseline run on the paired levels, with 95% intervals.
- **How far to trust each number:** agreement between two independent annotation passes.
- **One example level:** a time bar, and a table of each turn with its summary, shares and quote.

It is a **diagnostic**. It shows where the time goes. It does not say if a run is better: use your own gate for that.

## Install

One command, from the folder of your project (it installs the skill for this project only):

```sh
npx skills add XINHAO-ZHANG/diagnose-agent-traces
```

- Add `-g` to install it for all your projects (in your home folder).
- Add `--agent claude-code --agent cursor --agent codex` to choose the agents. Without it, the tool uses the agents that it finds.
- It needs Node.js 18 or newer. The `skills` tool is described [here](https://docs.keeper.io/en/keeperpam/secrets-manager/integrations/ai-agents/skills-cli).

No Node.js? Copy the folder `skills/diagnose-agent-traces/` into `.claude/skills/` (Claude Code), `.cursor/skills/` (Cursor) or
`.agents/skills/` (Cursor, and newer Codex) in your project. Use `~/.claude/skills/` and so on to install it for all projects.
Where each tool reads skills: [Cursor](https://cursor.com/docs/skills), [Codex](https://developers.openai.com/codex/skills)
(run `/skills` in the CLI to see what it loads).

Requirements for the skill itself: Python 3.8 or newer. No packages.

## How it works

```
 INPUT                        STAGES                                              OUTPUT

 run folder ─┐              ┌──────────────────────────────────────┐
 benchmark.json             │ 0  Check the data              free  │  stops here if a game fails
 transcripts/  ├───────────►│    transcripts parse, no cut text,   │
 baseline ───┘  (optional)  │    reasoning text is there           │
                            └───────────────────┬──────────────────┘
                                                ▼
                            ┌──────────────────────────────────────┐
                            │ 1  Count the time              free  │──►  STAGE1.md
                            │    turns with no action, yields,     │     (counted results,
                            │    read timeouts, actions per level  │      no model)
                            └───────────────────┬──────────────────┘
                                                ▼
                            ┌──────────────────────────────────────┐
                            │ 2a Cut each level into a packet free │  full text, nothing cut
                            └───────────────────┬──────────────────┘
                                                ▼
                            ┌──────────────────────────────────────┐   the agent asks you who annotates:
                            │ 2b Annotate (a language model)  paid │    A  the agent itself (sub-agents)
                            │    per turn: shares of waste types   │    B  another agent program
                            │    per level: 6 failure-mode codes   │       (cursor-agent, claude -p, codex exec)
                            │    base first, then the run;         │    C  nobody: stop after stage 1
                            │    two independent passes            │
                            └───────────────────┬──────────────────┘
                                                ▼
                            ┌──────────────────────────────────────┐
                            │ 3  Statistics                  free  │──►  ANALYSIS.md, analysis.json
                            │    shares, run vs baseline with      │
                            │    95% intervals, agreement between  │
                            │    the two passes (what to trust)    │
                            └───────────────────┬──────────────────┘
                                                ▼
                            ┌──────────────────────────────────────┐
                            │ 4  Report                      free  │──►  REPORT.md  (English)
                            └──────────────────────────────────────┘
```

Stages 0, 1, 3 and 4 use no model. Only stage 2b uses a language model. You can stop after stage 1 and keep the counted results.
The command `python3 scripts/pipeline.py` runs all stages. It spends nothing until you add `--annotate`.

## What the report looks like

An excerpt, shortened, from a real run (25 games, annotated with a language model; the numbers are from that run):

````markdown
# Failure tracing: where the example run loses time

## Summary

- 49.1% of the wall-clock (92,434 of 188,427 s, all games) goes to turns with no game action
  (turn-budget yields, read timeouts and the final stop). 292 turns end in a turn-budget yield and 30 in a read timeout.
- 23 of 25 games used the whole time limit.
- 65.3% of the labeled reasoning time is not productive. The largest category is over-deliberation (28.4%).

## Data and annotation

- Reasoning text: 25 of 25 games have the full reasoning text.
- run: 91 of 91 units annotated; 168 of 207 quotes are verbatim; the annotator used tools on 0 units.

## Result 1: time without action (counted, no annotator)

| Category | Turns | Seconds | Share of wall-clock |
|---|---|---|---|
| action_turn | 717 | 96,003 | 50.9% |
| no_action_turn_budget_yield | 292 | 75,103 | 39.9% |
| request_timeout | 30 | 16,317 | 8.7% |

## Result 2: reasoning waste

| Category | Share |
|---|---|
| productive | 34.6% |
| over-deliberation | 28.4% |
| re-derive | 10.6% |
| ... | ... |
| **not productive** | 65.3% |

## Result 3: failure modes

| Code | Run | Kappa | Use |
|---|---|---|---|
| FM2_FEEDBACK_NOT_USED | 27/85 | 0.65 | yes |
| FM3_NO_REVISION_AFTER_CONTRADICTION | 3/91 | 0.22 | no |
| FM6_TOOL_OR_STATE_ERROR | 78/91 | 1.00 | yes |

## Example level

**ft09 level 6.** Turns r24 to r27 took 1,239 s (52% of the level) and had 1 action.

```
 time bar: 1 character = 30 s.   █ = turn with action(s)   · = turn with no action
  r16     r17      r18         r21  r22          r24  r25    r26              r27
 |███████|········|······|█|██|████|··········|█|····|██████|················|···············|
                                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

| Turn | Time | Actions | What the turn is about | Shares | Quote |
|---|---|---|---|---|---|
| r24 | 122 s | 0 (yield) | The agent sees an apparent target match without completion and explores many alternative win conditions. | O 45, D 40, P 15 | "I'm stuck on theory." |
| r26 | 472 s | 0 (yield) | The agent rejects several hypotheses and plans tests of alternate target interpretations. | O 65, D 20, P 15 | |
| r27 | 461 s | 0 (yield) | The agent revisits the hint mapping, finds transcription mistakes in two cells, and computes the correction. | P 45, O 35, R 20 | |

## What this means (suggested rows; a human must check them)

| Finding | Evidence | Action |
|---|---|---|
| 49.1% of wall-clock is in turns with no action | Counted. Strong. | Limit the reasoning per turn. |
| FM2 (feedback not used) in 27 of 85 levels | Labeled. Two passes agree. | Compare prediction and result after each step. |

## Limits (generated from the checks)

- Failure-mode codes below the trust threshold: ['FM3_NO_REVISION_AFTER_CONTRADICTION'].
- The labels come from a language model. Use the counted results for decisions.
````

The report is a draft. The script writes the numbers and the facts. You edit "What this means" and add what the agent does in each phase of the example level.

## Use

In the agent, say for example:

> Use the diagnose-agent-traces skill. The new run is in `~/runs/new-harness`. The baseline is `~/runs/duck`. Diagnose the trajectories of the new run.

(In Codex you can write `$diagnose-agent-traces`.) The agent will:

1. Check the data and give you the counted results at once. This is free.
2. **Ask you who should annotate**, and show the cost:
   - **the agent itself** (with sub-agents, no extra account, uses your quota),
   - **another agent program** (`cursor-agent` is tested and has a cost cap; `claude -p` and `codex exec` can be used as a command),
   - **nobody** (you keep only the counted results).
3. Run the annotation, compute the statistics, and give you `REPORT.md` to read and edit.

Input format: a run folder with `benchmark.json` and `transcripts/<game>-*_p0.txt` (DUCK tool-agent transcripts).
You can also run the scripts yourself: see `skills/diagnose-agent-traces/SKILL.md`.

## Test it with no data and no account

```sh
sh skills/diagnose-agent-traces/tests/smoke_test.sh
```

It makes a small invented run and runs every stage with a test double instead of a model.

## What is tested, and what is not

- Tested on one real run of 25 games (91 level segments): the counted results, the packets, the statistics and the report reproduce a hand analysis.
  Details: `skills/diagnose-agent-traces/references/validation.md`.
- The `cursor-agent` backend worked on a real model call (one unit). A full pass with a real model was done once, with this method, before the code was packaged.
- The `manual` backend (the current agent annotates) and the `command` backend are tested with a test double only. The `claude` and `codex` commands in the skill file are examples.
- Only the DUCK transcript format is supported.
- The annotators are language models. Two passes of the same model agree well on the totals and on two failure-mode codes (FM2, FM6),
  and badly on the order of the smaller waste categories. The report says which numbers to trust.

## Files

```
skills/diagnose-agent-traces/
  SKILL.md        what the agent reads
  scripts/        the pipeline (stages 0 to 4)
  references/     method, codebooks, frozen prompt inputs, report template, validation
  tests/          smoke test and test doubles
LICENSE
```

## License

MIT. See `LICENSE`.
