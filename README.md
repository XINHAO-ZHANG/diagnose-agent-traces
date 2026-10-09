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
