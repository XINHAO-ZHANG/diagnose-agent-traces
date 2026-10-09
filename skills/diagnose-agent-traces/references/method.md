# Method and stop rules

## Units

- A **unit** is one level segment of a run (or one attempt, for a reference run).
- A **turn** is one model call. It has reasoning text and can have a tool call.
- A **yield** is a turn that the harness ended because the turn budget ran out. No action runs and the board does not change.
- **Paired levels** are the levels that both runs cleared with a known action count. Compare only these.

## Stage 0: preflight

Stop if one of these fails. Tell the user why.

| Check | Pass condition |
|---|---|
| Full text | No section in any packet is cut. The share of cut characters is 0. |
| Packet size | The largest packet fits in the context window of the annotator. If not, split on turn boundaries (see the addendum). |
| Text visibility | For each game of each run: steps with reasoning text, visible characters, hidden reasoning tokens. |
| Pairing | The paired levels are listed with both action counts. |

A game with little or no reasoning text is "summary only". Report it, but do not put it in the same table as full-text games.

## Stage 1: counted metrics

No model call. Compute and report first:

- Wall-clock, total and per game.
- Turns with no action: count, seconds, share of wall-clock.
- Yields: count, and the number of levels that have one.
- Read timeouts: count and seconds.
- Actions per level, and the gap on paired levels.
- For games that hit the time limit: the split of time into action turns, yields, timeouts and the tail.

These numbers do not depend on a language model. They are the strongest result.

## Stage 2: annotation

- Annotator: one model, no tools, blind (no prior labels, no milestone labels).
- Input: the full trace of one unit, in one prompt, sent through stdin. The fixed harness system prompt is not repeated in the packet.
- Output: one JSON object per unit (see the output contract).
  - Per turn: shares over the reasoning-waste categories. The shares add up to 1.0. One short quote for the largest not-productive category.
  - Per level: present, absent or unknown for each failure-mode code, with a quote or an observation, a step range and a reason.
- Run each unit twice, in two independent calls (G1 and G2). This gives the noise of the labels.
- Run `RUN` and `BASE` in the same pass.
- Record the model name, the prompt hash and the codebook version in every row.
- Check each quote against the text. Keep the share that matches.
- Keep a cost estimate and a cost cap. Write each unit to disk when it finishes, so that a stop can resume.

### Format v1.2: summary first, then shares

Format v1.1 gives shares and one quote per turn. It has no summary.
Format v1.2 asks for three fields in this order: `summary` (one sentence on what the agent thinks about, with no category names),
`allocation` (the shares), and `reason` (one sentence on why the largest shares are large). The quote stays.
Use `--format v1.2` in `build_packets.py` or in `pipeline.py`.

Two rules:
- Do not mix v1.1 and v1.2 labels in one comparison. They are different prompts (different hashes).
- Switch the default only after `compare_formats.py` says to keep v1.2 on the same units. See [format-trial.md](format-trial.md): two trials on 10 units gave different answers, and the second one failed the rule. The default stays v1.1.
Use in the pipeline: the numbers come from v1.1. One extra v1.2 pass, on the unit of the example level only, gives the turn summaries for the report table.

## Stage 3: statistics

- Seconds per category = share x wall-clock time of the turn.
- Tokens per category = share x tokens of the turn. When the harness gives no tokens per turn, split the tokens of the level by the share of characters.
- **Not productive** = every category except productive and unclear.
- Turns with no wall-clock time (for example the last turn of a level) are not in the totals.
- Agreement: Cohen's kappa on the top category of a turn, correlation of the not-productive share, and kappa per failure-mode code.
- Use paired levels for any comparison between two runs. Give an interval, not only a point value.

## What each kind of result can support

| Kind | Example | Can support |
|---|---|---|
| Counted | 47.6% of wall-clock is in turns with no action | A decision. |
| Within one run, labeled | Over-deliberation is the largest category | A decision, if two annotator families agree. |
| Between two runs, labeled | Productive share is higher in run B | A hint. Check the text visibility and the annotation pass first. |
| One example level | ft09 level 6 | An illustration. It proves nothing alone. |

## Where the categories come from

Codex first read traces of both runs as a trial. It wrote down the patterns that repeat.
We turned these patterns into the closed lists in [codebooks.md](codebooks.md) and fixed them before the full annotation.
The failure-mode list was written earlier, on 2026-10-04.
The lists come from a few levels. If a new run shows a behavior that no category fits, add it as free text and review the lists later.
Change the version number when you change a list, and annotate again.
