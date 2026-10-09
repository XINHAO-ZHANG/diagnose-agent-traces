<!-- Example report from the first analysis. The run, the numbers and the annotator names are from that analysis. -->
# Failure tracing pilot: where DUCK loses time

Status: draft, 2026-10-08. Not posted.

DUCK is the example run in this document.

## Summary

- Almost half of the wall-clock time goes to turns that end with no game action.
- About two thirds of the labeled reasoning time is not productive.
- Over-deliberation is the largest waste category.
- The reference runs use a larger share of their reasoning on productive work.
  This is true on the games where the reference reasoning text is visible.
  The gap is smaller than we first calculated.

## Why we did this

The time limit is the main constraint. Each game has about 7,920 s.
23 of the 25 games used all of this time before they were finished. The other two games were won.

We want to find where the agent loses time, so that it can act sooner.
We want to choose changes from what we observe in the traces.
We do not use the old arm experiments as evidence.

## What we did

### Data

- **DUCK**: the example run, 25 public games, 91 level segments.
- **REF**: 6 reference runs (ar25, ft09, lp85, sb26, su15, tu93).
  All six runs win. 51 attempts. The model and the harness are unknown.
- **Paired levels**: 34 levels that both DUCK and REF cleared.

### Reference reasoning is not always visible

| Game | Steps | Steps with reasoning text |
|---|---|---|
| lp85 | 108 | 108 |
| sb26 | 126 | 123 |
| su15 | 114 | 21 |
| ar25 | 256 | 12 |
| tu93 | 215 | 11 |
| ft09 | 77 | 0 |

Only lp85 and sb26 have full reasoning text.
For the other four games, we see one short sentence per step.
Because of this, we also report results for lp85 and sb26 alone.

### Annotation

- One unit is one DUCK level segment or one REF attempt. There are 142 units.
- The annotator reads the full trace of the unit. We did not cut the text.
- Annotator G1 and annotator G2: the same GPT model (gpt-5.6-luna-high),
  two independent runs, no tools, no prior labels.
- Annotator N1: a Gemini model (gemini-3.8-flash-high), same prompt.
  N1 finished 66 of the 142 units. The run stopped at a usage limit.

We also counted without any model: no-action turns, yields, read timeouts, and action counts.

### One earlier round is void

The first annotation round cut 79.6% of the DUCK reasoning text.
The REF text was almost complete.
The comparison was not fair, so we discarded the round.
We repeated it with full traces.

## How we label the reasoning

### Where the categories come from

We did not invent the categories in advance.

1. Codex first read traces of DUCK and REF as a trial (2026-10-08, morning comparison of paired levels).
2. Codex wrote down the patterns that repeat in the traces.
3. We turned these patterns into a closed list of categories (the table below).
4. We fixed the list before we ran the full annotation. We did not change it after we saw the results.

The failure-mode codes FM1 to FM6 are a separate list. We wrote them on 2026-10-04.

Because the list comes from a trial reading of a few levels, it can miss patterns.
It also reflects what Codex noticed first.

### What the annotator does

1. A turn is one model call. It has reasoning text, and it can have a tool call.
2. The annotator reads the whole turn.
3. The annotator gives one set of shares for the turn. The shares add up to 1.0.
   The annotator also gives one short quote for the largest "not productive" category.
4. We multiply each share by the wall-clock time of the turn.
   This gives seconds per category.
5. **Not productive** means every category except productive and unclear.

The annotator does **not** label single sentences.
One turn gets one set of shares.

This is the real output for one turn (ft09 L6, turn 26, annotator G1):

```
 productive          0.15
 over-deliberation   0.65
 discarded plan      0.20
 quote               "Decision: test A"
```

**Next time we should annotate in two steps.**
First, the annotator writes one sentence: "In this turn, the agent thinks about ...".
Second, the annotator gives the shares and says why.
The first sentence makes each label easy to check.
The present data has no such sentence.

The label describes what the text does.
It does not say if the reasoning was easy to avoid.
Any agent without prior knowledge must explore and make some mistakes.
For this reason, we compare DUCK with REF.

A wrong hypothesis is still productive when the agent tests it with a clear experiment.

### The categories, with one real example each

| Category | Meaning | Example from a DUCK trace |
|---|---|---|
| Productive | Reads new feedback. Forms or tests a hypothesis that can be true or false. Makes a plan that the agent executes. | ft09 L6, turn 21: "Let me do them one at a time" (single-click tests). |
| Over-deliberation | The action is trivial or already decided. The agent keeps weighing it. | ls20 L2, turn 27 (825 s): the agent checks the bar cap, the drain rate and the death condition again. It already observed all three. |
| Re-derive | The agent derives again a fact that is already in the trace. | r11l L2, turn 15 (884 s): "Let me re-track positions". |
| Board re-describe | The agent lists objects, colors or positions again. It adds no new conclusion. | r11l L2, turn 9: "Let me list all w pixels." |
| Discarded plan | The agent builds a plan or a hypothesis and drops it. No test and no action follow. A turn that ends with no action also counts. | cn04 L1, turn 18: "Let me step back and think about the game from a fresh perspective…". New goal ideas follow. The agent drops all of them without a test. |
| Lock-in batch | The agent trusts a rule that it has not tested. It plans many actions on that rule. The batch later fails. | g50t L3, turn 36: "let me do attempt 1 + SPACE in one call". |
| Tool debug | The agent reasons about a code error, an API call, or a repair of the state. | ls20 L2, turn 15: `AttributeError: 'HistoryEntryView' object has no attribute 'step'`. |

### A full example: ft09 level 6 in DUCK

**What to see in this example:**
The agent knew the true rule in turn 18.
The level ended in turn 28.
The cause of the delay was one hint that the agent read wrongly.
**Turns 24 to 27 took 1,239 s (52% of the level) and had 1 action.**

The level has 12 turns with a measured wall-clock time. They total 2,399 s.
Turn 28 has no wall-clock time in our data, so it is not in the totals.
"Yield" means the turn budget ended before an action ran.

The level has four phases:

| Phase | Turns | Time | Actions | What happens |
|---|---|---|---|---|
| 1. Wrong rule | r16 to r18 | 606 s | 14 | The agent clicks 14 tiles. It assumes that a click flips only that tile. The board is wrong. In r18 it finds the true rule: a click flips the tile and the tile above it. |
| 2. Right rule, wrong result | r19 to r23 | 554 s | 28 | The agent clicks in three batches (12, 6 and 9 clicks, plus 1 probe). None of them wins. |
| **3. Search for another cause** | **r24 to r27** | **1,239 s** | **1** | **The board matches the agent's hint map. The level does not end. The agent guesses other goals. It does not check its reading of each hint cell (g or W).** |
| 4. Fix | r28 | not measured | 5 | The agent finds that it read one hint wrongly (`gWW`, true value `gWg`). It clicks 5 tiles. WIN. |

```
 time bar: 1 character = 30 s.   █ = turn with action(s)   · = turn with no action
  r16     r17      r18         r21  r22          r24  r25    r26              r27             
 |███████|········|······|█|██|████|··········|█|····|██████|················|···············|
  11111111111111111111111 2222222222222222222222 33333333333333333333333333333333333333333333 
 1 = wrong rule (r16-r18)   2 = right rule, each batch still fails (r19-r23)
 3 = search for another cause (r24-r27)   [r28 = fix, not in the bar]
```

Each turn, with the G1 shares (P = productive, O = over-deliberation, D = discarded plan,
L = lock-in batch, T = tool debug, R = re-derive, B = board re-describe).
The shares are in percent:

| Turn | Time | Actions | What the agent does | G1 shares |
|---|---|---|---|---|
| r16 | 211 s | 14 | Reads the hints. Clicks 14 tiles. | P 75, B 25 |
| r17 | 229 s | 0 (yield) | Doubts its reading of the board: "maybe the magenta dots matter". | R 45, O 55 |
| r18 | 166 s | 0 (yield) | Tests shapes for the click effect. Finds "this tile AND the tile above". | P 15, O 55, D 30 |
| r19 | 38 s | 12 | Clicks 12 tiles with the new rule. Still wrong. | P 50, L 50 |
| r20 | 45 s | 1 | One probe click. | P 35, T 35, O 30 |
| r21 | 134 s | 6 | Single-click tests. | P 75, B 25 |
| r22 | 295 s | 0 (yield) | Checks the flip model again. | P 20, T 40, O 40 |
| r23 | 42 s | 9 | Clicks 9 tiles. Board matches its target map. Level not done. | P 35, L 65 |
| **r24** | **122 s** | **0 (yield)** | **"ALL plain tiles now match the target T! But the level didn't complete." Then: "I'm stuck on theory."** | **P 15, O 45, D 40** |
| **r25** | **184 s** | **1** | **Test click on a hint tile. Nothing changes.** | **P 20, O 70, B 10** |
| **r26** | **472 s** | **0 (yield)** | **New goal ideas. No test. (See the zoom below.)** | **P 15, O 65, D 20** |
| **r27** | **461 s** | **0 (yield)** | **Picks a test plan.** | **P 45, O 35, R 20** |
| r28 | not measured | 5 | Finds the misread hint. WIN. | P 100 |

Totals for the level, weighted by wall-clock time:

| Category | G1 | G2 |
|---|---|---|
| Productive | 30.2% | 18.2% |
| Over-deliberation | 41.7% | 36.6% |
| Re-derive | 8.1% | 20.4% |
| Discarded plan | 8.0% | 8.8% |
| Tool debug | 5.6% | 11.8% |
| Board re-describe | 4.4% | 1.3% |
| Lock-in batch | 1.9% | 2.9% |

1,745 s of the 2,399 s (73%) are in turns with no action.

### Zoom on turn 26 (472 s, no action)

The agent has 14 tiles that match its hint map. The level does not end.
The agent then reasons about why. The text has about 20,700 characters.
The lines in brackets are short summaries of the text, not exact quotes.
G1 gives this turn one set of shares: productive 15%, over-deliberation 65%, discarded plan 20%.

```
 CHECKS (productive)
   [check]      "Clicking a special does nothing ✓"
   [check]      "The legend shows Y and N ✓"

 NEW GOAL IDEAS (the annotator sees these as over-deliberation and discarded plans)
   [idea 1]     "Maybe the goal is different ... the number of tiles of each color?"
   [idea 2]     "Maybe the magenta dot marks a tile as 'unset'?"
   [idea 3]     "Maybe the goal is a Lights-Out pattern: all dots off?"    <- the dots never change
   [idea 4]     "Maybe W means the OTHER color?"
   [idea 5]     "Maybe the goal is 'all tiles the same color'?"           <- level 5 shows this is false
   (no test for any idea)

 CODE (productive)
   [code]       one script: it finds a 7-click and a 12-click solution

 END
   the turn ends in a yield. No action runs.

 NOT IN THIS TURN: a check of its reading of each hint cell (g or W).
 The error was there. The agent found it in turn 28.
```

This label is a judgment. Another reader can call part of these ideas productive search.
The next section shows how often two runs of the same model disagree.

### How stable the labels are

G1 and G2 are two independent runs of the same model.
They disagree on single turns:

| Turn | G1 | G2 |
|---|---|---|
| ft09 L6, turn 17 | over-deliberation 55%, re-derive 45% | tool debug 45%, discarded 30%, re-derive 25% |
| ft09 L6, turn 18 | productive 15%, over-deliberation 55%, discarded 30% | tool debug 45%, over-deliberation 35%, discarded 20% |
| ft09 L6, turn 21 | productive 75%, board re-describe 25% | productive 60%, re-derive 25%, tool debug 15% |

Agreement on the top category of a turn is 69% (kappa 0.46).
The share that is not productive agrees better (correlation 0.76).

For this reason:

- We trust the total "not productive" share.
- We trust over-deliberation as the largest category.
  A Gemini annotator agrees with this.
- We do **not** trust the order of the other categories.
  Their kappa is near 0 between the model families.

## How we label failure modes

Reasoning waste is a label for each turn. A failure mode is a label for the whole level.
The question is: where did the process break?

### The pipeline and the six codes

```
 explore --> read feedback --> know the rule --> make a plan --> act --> compare result --> fix the plan
    |             |                 |                |           |            |                 |
   FM1           FM2               FM4               -          FM5          FM3               -
 repeats a    ignores or        knows the rule,     (a wrong    does not     sees a            (the fix
 test that    misreads the      but waits           plan is     do what      contradiction,    is the
 is already   result            before it acts      a knowledge the plan     keeps the         good case)
 answered                                           problem)    says         old plan

 FM6: a tool, code or harness error uses up turns or actions. It can happen at any step.
```

| Code | Plain meaning | Example from a DUCK trace |
|---|---|---|
| FM1 Repeated exploration | The agent repeats a test that the trace already answered. It has no new idea. | ar25 L5: the agent finishes the horizontal move. It then runs the same LEFT/RIGHT selection probe again. The selection did not change. |
| FM2 Feedback not used | The environment gave a clear result. The agent ignores it or reads it wrongly. | ft09 L6, turn 18: a batch of 14 clicks gives a clear result. The agent reads it as "my clicks were shifted by one grid position!". It then runs a wrong batch of 12 clicks. |
| FM3 No revision after contradiction | The agent has a plan. A result clearly contradicts the plan. The agent keeps the plan. | lp85 L5: the first action already breaks the prediction (the tool prints `mism 2`). The agent still runs the same six-action plan to the end. |
| FM4 Delay after key insight | The agent has the knowledge to solve the level. It still explores or checks again before it acts. | ar25 L1: after step 2 the agent has the right goal and an exact move plan. It first asks "check SPACE and ACTION7 quickly?" and tests SPACE. |
| FM5 Execution differs from plan | The plan is right. The agent converts it to actions or code in the wrong way. | ar25 L7: the plan is fixed. The agent passes a block coordinate where the solver needs a cell coordinate (`av=12`). The bar moves to the wrong place. 40 actions. |
| FM6 Tool or state error | A code error, a timeout or a state repair uses up turns or actions. | ft09 L6: `NameError: name 'open' is not defined`. Also: "the turn time budget expired while your code was still inspecting". |

In this data, FM6 is mostly a turn-budget yield. This is a harness event.
It is not a reasoning failure.

### How the annotator uses the codes

- The annotator reads the whole level and gives a value to **every** code: present, absent, or unknown.
  Unknown means "the trace is not enough to decide". It does not mean absent.
- "Present" needs one exact quote or one clear observation from the trace, a step range, and a short reason.
- The annotator can mark several codes for one level.
- `cost_actions` is the number of actions that the pattern used.
  The annotator fills it only when the trace shows the number.
  It does **not** mean "actions we could have saved".
- A count such as "27 of 85" means: 27 levels have the code, and the annotator could decide on 85 levels.

## Findings

### 1. Time without action (counted, no annotator)

| Item | Value |
|---|---|
| Wall-clock, 91 DUCK levels | 182,876 s |
| Turns with no game action | 86,971 s (47.6%) |
| Turn-budget yields | 292 turns, in 66 of 91 levels |
| Read timeouts (900 s), all 25 games | 16,317 s (8.7% of wall-clock) |

In ar25, 66% of the time went to turn-budget yields.

A yield is not fully lost time.
The thinking and the tool results stay in the trace.
But no action runs, and the board does not change.

### 2. Reasoning waste inside DUCK

| Annotator | Not productive | Over-deliberation |
|---|---|---|
| G1 (91 levels) | 65.4% | 28.4% |
| G2 (91 levels) | 65.8% | 31.8% |
| G1 (66 units) | 65.5% | 30.4% |
| N1 (same 66 units) | 58.3% | 28.2% |

- Over-deliberation is the largest category for G1 in 21 of 25 games.
- Both model families agree on this.

### 3. DUCK compared with REF

Share of reasoning tokens that is productive, paired levels only:

| Annotator | Games | DUCK | REF |
|---|---|---|---|
| G1 | all 6 games | 42.7% | 61.4% |
| G1 | lp85 and sb26 | 47.4% | 61.4% |
| G2 | lp85 and sb26 | 49.9% | 64.7% |
| N1 | lp85 and sb26 | 52.5% | 71.5% |

- The total token count is almost equal (578k for DUCK, 536k for REF).
  The difference is in how the tokens are used.
- On lp85 and sb26, REF is 14 to 19 points higher. All three annotators agree.
- Over-deliberation on lp85 and sb26 is almost equal
  (G1: 14.9% for DUCK, 13.1% for REF).
  The large gap in the all-games table comes from the four games with short summaries.
  A short summary has little room for over-deliberation.
- By wall-clock time, the gap is not stable on lp85 and sb26.
  G1 and G2 show no gap or a small reverse gap.

### 4. Failure modes

The codes are explained in "How we label failure modes".

Annotator G1. "27 of 85" means: 27 levels have the code, out of 85 levels that the annotator could judge.

| Code | DUCK | REF | Do the two model families agree? |
|---|---|---|---|
| FM1 Repeated exploration | 21 of 90 levels | 0 of 31 | The direction agrees. Gemini finds about half as many. |
| FM2 Feedback not used | 27 of 85 | 1 of 28 | Yes (kappa 0.69). |
| FM3 No revision after contradiction | 3 of 91 | 0 of 31 | No (kappa 0.38). Too few cases. |
| FM4 Delay after key insight | 5 of 69 | 0 of 27 | No (kappa 0.37). Too few cases. |
| FM5 Execution differs from plan | 14 of 84 | 1 of 30 | No (kappa 0.47). |
| FM6 Tool or state error | 78 of 91 | 0 of 51 | Yes (kappa 0.96). Mostly turn-budget yields. |

- FM2 is the most frequent failure that is not a harness event.
- Use FM2 and FM6. Do not use the FM3, FM4 and FM5 rates.
- FM1, FM2 and FM5 occur mostly in the levels that DUCK did not clear.

### 5. The ft09 level 6 comparison

The level needs 15 actions in REF and 48 actions in DUCK.
Both agents first assume that one click changes one tile.
The true rule: one click changes the tile and the tile above it.

```
 REF   15 actions, WIN
       [test][undo][1 planned click] -> result differs -> new rule -> [12 clicks]
                                        ^ the agent changes the rule after 1 click

 DUCK  48 actions, WIN, 2,399 s
       [14 clicks, wrong rule] -> [12 clicks, solver error] -> [9 clicks, hint copied wrongly] -> [5 clicks]
                              ^ the agent finds the rule only after the whole batch
```

- REF clicked once, saw a different result, and corrected the rule at once.
- DUCK sent a batch of 14 clicks with the wrong rule.
  Two more failed batches followed.
- For this example, we see only a one-sentence summary on the REF side.

## What this means

| Finding | Evidence | Action |
|---|---|---|
| Many turns end without an action | Counted. Strong. | Limit the reasoning per turn. When the budget is almost used, send an action. |
| Read timeouts use 8.7% of time | Counted. Strong. | Make the 900 s read timeout shorter. Retry sooner. |
| Batches run under an untested rule | One clear example. FM2 is stable. | Compare prediction and result after each step. Stop at the first mismatch. |
| Discarded plans and tool debug are above REF | Two model families agree. | Ask for the smallest next step first. Give short, structured tool errors. |
| Fact ledger or board-diff injection | Rankings are not stable. REF re-describes the board more. | Do not do this first. |
