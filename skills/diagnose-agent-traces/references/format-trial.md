# Trial of annotation format v1.2 (2026-10-09)

Question: does a summary-first format (v1.2) keep the agreement between two passes at the level of the v1.1 format?

Setup:
- 10 units of the DUCK run (8 games, at most 2 per game, includes ft09 level 6; seed 41). 53 turns per pass.
- Format A = v1.1, the passes G1 and G2 of 2026-10-08.
- Format B = v1.2, two new independent passes (T_A and T_B), same model (gpt-5.6-luna-high), same packets, same other inputs.
- The prompt text of v1.2 in this trial has the hash `850d3f9626de`. It did not ask for a language.
- Rule fixed before the run: keep B if its top-category kappa and its failure-mode macro kappa are each at least those of A minus 0.05, and at least 90% of its turns have a summary and a reason.

| Measure | A (v1.1) | B (v1.2) |
|---|---|---|
| Top-category kappa between the two passes | 0.46 | 0.52 |
| Top-category agreement | 0.75 | 0.81 |
| Not-productive share, correlation between passes | 0.83 | 0.85 |
| Failure-mode macro kappa | 0.60 | 0.55 |
| Failure-mode pooled kappa | 0.74 | 0.79 |
| Mean output tokens per unit (pass 1) | 4,113 | 5,799 |
| Cost of the two passes on these 10 units | $0.327 | $0.328 |

Turns of B with a summary and a reason: 100%. Mean change of the not-productive share per turn, B minus A: -0.016 over 106 turns.
Runner fixes: 0 in both B passes. Failure-mode quotes verbatim: 18 of 21 (T_A), 15 of 17 (T_B).

Result by the rule: keep B (first trial; see the second trial below, which reverses this). Both measures are inside the tolerance, and the top-category kappa is a little higher.

What the first trial does not show:
- The sample is small (10 units, 53 turns). The differences of 0.05 are inside the noise of this size.
- The summaries of pass T_A are in Chinese, and those of pass T_B are in English. The prompt did not ask for a language, and the codebook file is in Chinese.
  The prompt now says: "Write `summary` and `reason` in English". This text has a new hash (`3cc0d67a825e`). The second trial uses it.
- B costs 41% more output tokens per unit. The cost of the two passes is the same on these units.

## Second trial: the prompt asks for English (hash 3cc0d67a825e)

Same 10 units, same model, same A passes. Two new passes of B (T_C and T_D).

| Measure | A (v1.1) | B (v1.2, English) |
|---|---|---|
| Top-category kappa between the two passes | 0.46 | 0.33 |
| Top-category agreement | 0.75 | 0.74 |
| Not-productive share, correlation between passes | 0.83 | 0.78 |
| Failure-mode macro kappa | 0.60 | 0.26 |
| Failure-mode pooled kappa | 0.74 | 0.51 |
| Mean output tokens per unit (pass 1) | 4,113 | 4,801 |
| Cost of the two passes on these 10 units | $0.327 | $0.313 |

Turns with a summary and a reason: 100%. None of the summaries or reasons has Chinese text. Runner fixes: 0. Failure-mode quotes verbatim: 14 of 17 (T_C), 13 of 14 (T_D).

Result by the rule: **do not switch to format B**. Top-category kappa is 0.13 lower, and failure-mode macro kappa is 0.34 lower.

## What we conclude

- The two trials of the same format gave different answers: top-category kappa 0.52 and then 0.33, failure-mode macro kappa 0.55 and then 0.26.
  The change between the trials is larger than the tolerance of 0.05. **At 10 units, this measure cannot decide a difference of 0.05.**
  Failure-mode kappa is the least stable: most codes have only a few positive cases in 10 units.
- We have **no evidence that v1.2 agrees as well as v1.1**. We also have no evidence that it agrees worse. The test is too small.
- The summaries are useful to read. They say what the turn is about and the reasons point at the text. The test did not measure if they make a label easier to check.
- Cost of the two trials: $0.33 and $0.31. Total for the format work: $0.64.

## Status and options

- The default stays **v1.1**. v1.2 stays optional (`--format v1.2`).
- Do not mix v1.1 and v1.2 labels in one comparison.
- Option 1 (cheap): use v1.1 for all numbers. Use v1.2 only for the few levels that you show as examples, to get readable summaries. Say in the report that the summaries come from a second format.
- Option 2: a larger trial. About 30 units, two passes, would cost about $2. It could decide a difference of 0.1. It cannot decide 0.05.

## Trial of format v1.3 (2026-10-09)

Format v1.3 keeps the output of v1.1 and adds a longer guide to the prompt: a decision order, "counts / does not count" rules, and real examples.
Same 10 units, same model, same A passes (v1.1). Two new passes of v1.3 (V13A, V13B). Cost of the two passes: $0.32.

| Measure | A (v1.1) | B (v1.3) |
|---|---|---|
| Top-category kappa between the two passes | 0.46 | 0.35 |
| Top-category agreement | 0.75 | 0.91 |
| Not-productive share, correlation between passes | 0.83 | 0.82 |
| Failure-mode macro kappa | 0.60 | 0.61 |
| Mean not-productive share of a turn (pass 1) | **43.8%** | **22.8%** |
| Mean output tokens per unit (pass 1) | 4,113 | 4,954 |

What the numbers say:
- **The guide moved the line between productive and not productive.** The not-productive share of a turn fell by 21 points on these units
  (productive 56% to 77%, over-deliberation 17% to 2%). The noise between two passes of one prompt is about 3 points. So the prompt is a much larger
  source of change than the annotator noise.
- Agreement did not improve in a clear way. The raw agreement on the top category rose (0.75 to 0.91) only because most turns are now "productive".
  The chance-corrected kappa fell (0.46 to 0.35), and the kappa of most not-productive categories fell to 0 or is undefined (they are almost never the top category).
  The failure-mode kappa did not change (0.60 and 0.61).
- We cannot say which format is right. Only a human gold set can say which line is closer to a person.
- Why it moved is not tested. One guess: the sentences "a test that gives new information is not waste" and step 1 of the decision order
  (hypothesis or plan -> productive) make the annotator more generous. Test this by removing them and running again.

Status: v1.3 stays a draft. The default stays v1.1. `compare_formats.py` now says "the rule does not decide" when the mean not-productive share
differs by more than 10 points between two formats.

Consequence for the headline number: the share of not-productive reasoning in a report depends on the prompt wording. Compare runs only inside one prompt
version, and choose the version with the human gold set.
