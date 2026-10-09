---
name: diagnose-agent-traces
description: Diagnose where an ARC-AGI-3 agent run loses time, from its transcripts folder. Counts the time (turns with no action, turn-budget yields, read timeouts), labels each turn with a reasoning-waste breakdown and each level with failure-mode codes, compares the run with a baseline run, and writes an English report. Use when the user gives a transcripts folder of a run and asks to diagnose, analyse or compare the trajectories of that run.
---

# Diagnose agent traces

This skill is a diagnostic. It shows where the time goes and whether a targeted behavior changed.
It does **not** decide if a run is better. Use the project's own gate (levels, paired, replicated) for that.

Talk with the user in the user's language. Write the final report in plain, short English
(ASD-STE100 style: short sentences, one meaning per word, active voice).

All scripts are in `scripts/` (Python 3.8 or newer, standard library only). Paths below are relative to this folder.

## What the user gives you

- `RUN`: the folder of the run to diagnose. It has `benchmark.json` and `transcripts/<game>-*_p0.txt` (DUCK tool-agent format).
- `BASE` (optional but better): the folder of a baseline run in the same format, for the same games.
- A work folder for the results. If the user gives none, make a new folder next to `RUN`. Never write into `RUN`.

If the user gives only a transcripts folder, ask where `benchmark.json` is. If there is no baseline, the report has no comparison.

## What you do

1. **Free check. This spends nothing.**
   ```sh
   python3 scripts/pipeline.py --run RUN --base BASE --work WORK --name RUN_NAME --base-name BASE_NAME
   ```
   - It checks the data (stage 0), counts the time (stage 1), builds the annotation packets, and prints a cost estimate.
   - Stage 0 must say `0 with FAIL`. If a game fails, tell the user why. Do not skip the game.
   - Open `WORK/stage1/run/STAGE1.md`. Tell the user the counted results first: the share of wall-clock in turns with no action,
     the yields, the read timeouts, the games that used the time limit. These numbers are already usable.
2. **Ask the user who annotates.** Do not choose for the user. Show the estimate. Give these options:
   - **A. You (the current agent) annotate**, with sub-agents. No extra account. It uses the user's own quota and takes time.
     Go to "Annotate with the current agent".
   - **B. Another agent program annotates.** `cursor-agent` is tested and has a cost cap. `claude -p` and `codex exec` work as
     a command, but their flags are examples that you must test on one unit first. Go to "Annotate with another agent".
   - **C. No annotation.** The user keeps only the counted results (step 1). Stop here.
   Say which option you recommend: B with `cursor-agent` if the user has it (tested), else A.
3. **Run the annotation** with the option the user chose. Ask for a budget (option B) or for the scope (option A:
   `--games a,b` for a few games, or `--passes G1` for one pass instead of two; one pass gives no noise estimate).
4. **Give the user `WORK/REPORT.md`.** Then follow "Read the report".
5. **Do not commit, push or post anything** unless the user asks.

## Annotate with the current agent

Use `--backend manual`. The label after `--model` is your own model name (for example `claude-opus-5-5`).
Use the same label for the base and the run. The script stores it and checks it.

```sh
python3 scripts/pipeline.py --run RUN --base BASE --work WORK --name RUN_NAME --base-name BASE_NAME \
    --annotate --backend manual --model YOUR_MODEL_NAME
```

The command writes one prompt file for each unit and stops. It prints the folders. In each folder `requests/<uid>.txt` is a full prompt.

For each request file:

1. Act as the annotator. Read the file. It has the instructions and the full trace of one unit.
2. Answer with the JSON object only (no text around it, no markdown fence). Save it as `answers/<same name>.json` in the same folder.
3. Do not read any other file: no other answers, no other pass, no earlier labels, no source code of this skill.
   Do not run code. The annotator must be blind and independent.

How to do this well:

- Use one **fresh sub-agent for each request**, with no other context. Give it two paths only: the request file and the answer file.
  Run them in batches (for example 5 at a time). A sub-agent with a clean context is the closest to the tested setup.
  You, in the main conversation, know the context of the user's question. You are not blind.
- The passes G1 and G2 must be independent. A sub-agent for G2 must not see the answers of G1.
  If you cannot start sub-agents, use `--passes G1` and tell the user that the labels have no noise estimate.
- A unit can have up to about 190,000 tokens. With 91 units, two passes and two runs, there are about 364 requests.
  Tell the user this number before you start.
- Check that each answer is valid JSON. If it is not, delete the file and ask again.

Then run the **same command again**. It reads the answers, runs stages 3 and 4, and writes `WORK/REPORT.md`.
If some answers are still missing, it lists them again.

## Annotate with another agent

Cursor (tested). The cost cap is for the whole command. If the command stops (cap or usage limit), run it again: it resumes.
```sh
python3 scripts/pipeline.py --run RUN --base BASE --work WORK --name RUN_NAME --base-name BASE_NAME \
    --annotate --backend cursor --model gpt-5.6-luna-high --budget-usd 8
```
Any other program, with `--backend command`. The program reads the prompt on stdin and prints the answer (the JSON) on stdout.
The cost is not tracked. `--model` is only a label that is stored in the result. Test on one unit first
(`python3 scripts/annotate.py --packets WORK/packets/run --pass-name T --backend command --command "..." --model LABEL --uids UID`).
Examples, not tested here:
```sh
--backend command --model claude-sonnet --command 'claude -p --model sonnet --tools ""'
--backend command --model codex          --command 'codex exec --sandbox read-only --skip-git-repo-check'
```

## Read the report

1. Read "Data and annotation" first: any `WARNING` or `FAIL`, the share of verbatim quotes, the tool-use count.
   If the guard says that the run and the base used a different model or prompt, stop. Annotate again in the same pass.
2. Compare each difference with the size of the label noise (see [validation.md](references/validation.md)). In the tested data, two passes of the
   same model differ by about -3 to +2 points in the productive share of tokens. A difference inside that range is not a difference.
3. Edit the report with the user:
   - Replace the suggested rows in "What this means" with rows that the numbers support.
   - Add the phase table for the example level (what the agent does in each phase). The script gives only facts.
   - Remove any sentence that the numbers do not support.
4. Decide with the counted results. Use the labeled shares only as a hint.
5. Check each number in the text against `WORK/analysis/analysis.json` and `WORK/stage1/run/STAGE1.md`.
6. The final report must be in English. `report.py` stops when it finds Chinese, Japanese or Korean text.

## Rules (each one cost us something)

1. **Never give the annotator cut text.** A first round cut 79.6% of the reasoning and gave a reverse answer. `build_packets.py` audits this.
2. **Check the reasoning text of every reference game.** In one reference set, one game had no reasoning text, and four of six had almost none.
3. **Compare only inside one annotation pass.** A different annotator model moved the not-productive share by about 7 points.
4. **Keep the annotator blind and tool-free.** No prior labels. Flag any unit where the annotator used tools.
5. **Check every quote** against the text. Keep the share of verbatim quotes in the report.
6. **Report agreement.** The totals and two failure-mode codes (FM2, FM6) agreed between model families. The order of the smaller categories did not.
   Set the trust threshold before you read the results.
7. **Do not use the shares as a pass or fail test.** They are labels from a language model.
8. **Send big prompts through stdin**, not as an argument. A 540 KB argument returned nothing, with no error.
9. **Set a cost cap and make the run resumable.** One run stopped at a usage limit with 66 of 142 units done.
10. **Do not commit, push or post an issue unless the user asks.**
11. **The final report is in English.** The failure-mode fields that the annotator writes (`rationale`, `observation`, `notes`) can be in Chinese
    because the codebook file is in Chinese. The report does not print them. Translate them before you quote them.

## Scripts

| Script | What it does |
|---|---|
| `scripts/pipeline.py` | **One command for stages 0 to 4.** Without `--annotate` it spends nothing. `--backend cursor\|command\|manual` chooses who annotates. Rerun the same command to resume. After the main annotation it adds one pass in format v1.2 for the single example level (about $0.03 with `cursor`), so that the per-turn table has a one-sentence summary. `--no-example-summaries` skips it. |
| `scripts/preflight.py` | Stage 0. Per game: transcript found, headers parse, action index fits the benchmark, no annotation-cut marker, reasoning text present. Exit 1 on any FAIL. |
| `scripts/metrics.py` | Stage 1. Wall-clock split into action turns, budget yields, read timeouts, stop. With `--base`: paired levels and action gaps. |
| `scripts/stage01.py` | Stage 0, then stage 1 only if stage 0 passes. |
| `scripts/build_packets.py` | Stage 2a. One packet per level segment with the full text. Plans chunks for packets above the context limit. `--format v1.1\|v1.2`. |
| `scripts/annotate.py` | Stage 2b. The three backends. Resumable per unit. `--dry-run` prints the estimate. |
| `scripts/analyze.py` | Stage 3. Shares by category, paired bootstrap, failure-mode table, agreement (kappa, PABAK) with a trust flag. Stops if run and base used a different model or prompt. |
| `scripts/report.py` | Stage 4. Writes the English report from the results of the earlier stages. |
| `scripts/compare_formats.py` | Compares two annotation formats by the agreement between two passes. |
| `tests/` | `smoke_test.sh` runs every stage on a made-up sample run, with a test double instead of a model. |

Format v1.1 (shares and one quote per turn) is the default and gives all the numbers.
Format v1.2 (summary, shares, reason) was not shown to agree as well ([format-trial.md](references/format-trial.md)).
Format v1.3 (the v1.1 output with a longer guide: a decision order, 'counts / does not count' rules, real examples) is a draft. In one trial it moved the not-productive share of a turn by -21 points, without a clear gain in agreement ([format-trial.md](references/format-trial.md)). Choose between v1.1 and v1.3 with a human gold set.

## References

- [method.md](references/method.md): stage rules and what each kind of result can support.
- [codebooks.md](references/codebooks.md): the waste categories and the failure-mode codes, with examples.
- [validation.md](references/validation.md): what was checked, and the size of the label noise.
- [report-template.md](references/report-template.md), [example-issue-2026-10-08.md](references/example-issue-2026-10-08.md): the report shape and a finished example.
- [format-trial.md](references/format-trial.md): the trial of format v1.2.
- `references/frozen-inputs/`: the prompt, addendum, protocol, codebook and output contract. Do not edit them: a change gives a new hash.
