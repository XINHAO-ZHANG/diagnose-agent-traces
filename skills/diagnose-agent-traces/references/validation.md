# What was checked

These checks used the DUCK run (25 games, 91 level segments) and the annotations of 2026-10-08.

Stage 0 and 1: the totals equal the 2026-10-08 results
(188,427 s; action turns 50.9%; yields 39.9%, 292 turns; read timeouts 8.7%, 30 turns).
A copy of the run with an annotation-cut marker made stage 0 fail and stage 1 not run.

Checked for stage 2 on the DUCK run, with the packet label `TXT`:
- 91 of 91 packets built from the raw transcripts are identical to the packets that the 2026-10-08 annotators read.
- The prompt message for ft09 level 6 was byte-equal to the 2026-10-08 message. Afterwards one status line in the codebook file was edited (the text about who confirms the freeze), so a new message differs from the old one in that line only. New rows also store `inputs_sha256`, a hash of all the input files; the guard in `analyze.py` stops when two sets of rows have different input hashes.
- The dry-run estimate for the 91 units is $1.90. The 2026-10-08 run of the same units cost about the same ($3.02 for 142 units).
- With the test double: resume, retry of failed units, cost cap, usage-limit stop, unknown-model check and chunk merge all work.
- Stage 3 on the 2026-10-08 annotations (91 DUCK units, passes G1 and G2) reproduces the earlier numbers: category seconds (over-deliberation 47,489 s), failure-mode counts (for example FM2 27/85, FM6 78/91), kappa per code, 987 turns, top-category kappa 0.46.
- Stage 3 guards: a run compared with itself gives a difference of 0. A base annotated with another model makes it exit 1.
- Size of the label noise: G1 against G2 on the same units, paired levels, gives a difference of -0.6 points in the productive share of tokens, with an interval of -2.9 to +1.9. A real difference must be larger than this.
- A real model call on one unit (`TXT__ft09__L3__a1`, gpt-5.6-luna-high) worked: cost $0.0091, 26 s, the answer parsed with no fix, the quote was verbatim, the failure-mode codes equal the 2026-10-08 labels.
- Stage 4 on the 2026-10-08 data, level ft09 6: the report finds the stretch r24 to r27 (1,239 s, 52% of the level, 1 action) by itself. The per-turn times, actions and shares equal the hand-made figure.
- `pipeline.py` end to end with the test double (2 games, run and base, 2 passes): the cost estimate, the stop at a cap, the resume, the guards, stages 3 and 4, and `REPORT.md` all work. A missing run directory stops at stage 0.
- Run a few units first (`--uids`) before a full pass.

The packets omit the SYSTEM PROMPT section. It is the fixed harness prompt and it repeats in every turn.
`build_packets.py` warns when a run has more than one system prompt.

Stage 0 does not yet check the pairing of levels. Stage 1 lists the paired levels.
A game is flagged "hit time limit" when its wall-clock is at least 95% of `--time-limit-s`.
In the DUCK run, 23 of 25 games hit the limit.

The harness also cuts long tool outputs (`... [truncated N chars]`). The model saw those cuts.
Stage 0 counts them in the column `tool-cut` and does not fail on them.

