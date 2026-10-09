# Shared annotation protocol — trajectory-v1

This consolidates the pilot v0.5 semantics across source formats. Format adaptation changes provenance, not the meaning of the annotations.

## Milestones

| Type | Evidence standard |
|---|---|
| PK | Important correct knowledge is available, but level-specific information is still missing. Identify both. An unsupported hypothesis is not PK. |
| K | Earliest defensible prefix containing sufficient observations/history/context/reasoning to construct a correct solution. Agent self-confidence or saying “I understand” is insufficient. A complete explicit plan or globally complete world model is unnecessary. |
| C | Distinct commitment enacted in behavior: stopping current exploration and acting on a particular model/plan. Intent alone is insufficient. The plan may be incomplete or wrong. |
| R | After a C, contradiction/failure leads to modifying or abandoning that model/plan. Identify the revised C, contradiction and changed plan. Failure or routine progress updates alone are not R. |
| S | Environment-confirmed level completion; a prediction of success is not S. |

C and R may recur. Test and execution can overlap. K may precede or follow a C. Ongoing correct execution after K does not require inventing another C. A single episode need not pass through a fixed sequence.

For K, explicitly list required information and its prefix evidence, distinguish newly acquired information from inherited knowledge, and identify unresolved requirements. Later success must not fill an earlier gap. Later failure does not by itself invalidate previously available sufficient information: the agent may have failed to utilize it. Missing visual/context data limits earliest-boundary claims, but lack of later execution alone does not disprove K. Preserve candidate boundaries, alternatives and confidence. Do not demand a later successful test as a universal K prerequisite.

Annotate chronologically. If the annotator has already seen later outcomes, declare retrospective exposure; do not claim a blinded prefix evaluation. Confidence is high/medium/low with a reason, not a calibrated probability. Unknown and not-reached differ. Absence of evidence is not proof that an event did not happen.

## Position and accounting

Step 1 is the first counted environment action of this level attempt. Initial state is Step 0 for indexing only, displayed as Initial state. Commands such as ACTION1 are distinct from chronological Step numbers.

Store milestone position as before_action, action_execution, after_feedback, or analysis_only. Store source record/section order separately: several reasoning or revision events may occur between the same two Steps. A C in a batch is assigned a specific Step only when source order supports that boundary; otherwise retain a range or unknown.

| Metric | Definition |
|---|---|
| A_K | Number of completed actions from initial state through K. Before Step n means n−1; after Step n means n. |
| P_C | Selected C events strictly before K, respecting source order even at identical action counts. Not a count of proven mistakes. |
| D_K | Actions after K and before first appropriate utilization, excluding the first utilizing action. Zero for immediate/ongoing appropriate use. An inappropriate C does not end this interval. Null if the utilization boundary is unknown/unreached. |
| A_KS | Actions after K through the clearing action. Null without observed K and S boundaries. |

For a K after completed action k and appropriate use at Step u, D_K=max(0,u−k−1); only compute if ordering is established. If K is inside an action/batch with unresolved ordering, dependent metrics are null or explicitly bounded, not silently rounded. For a solved run with an exact between-action K, A_K+A_KS equals its total actions. D_K overlaps A_KS, and P_C counts events; never sum the four metrics.

Record conditional statistics for candidate K, with K confidence and alternatives. Include runs that stop before K or S. Zero action expenditure may involve substantial analysis time. Keep measured elapsed time, header-window proxies, recorded token sums, verified unique-request usage and unknown costs distinct; do not distribute a batch's time/tokens among unobserved substeps.

## Episodes and inefficiency

Summarize what happened, then propose free English labels: Probe, Hypothesis test, Revision, Selection discovery, Execution, etc. Multiple labels may apply. Do not force a vocabulary or sequence. Each label has exact supporting quotes/observations and an explanation; for a revision provide the contradictory feedback and the change. Preserve original labels when later clustering.

Episodes are contiguous, non-overlapping accounting units covering the observed record sequence; labels may overlap. Preserve no-action episodes. If a desired boundary falls inside an indivisible cost record, keep its cost unallocated/shared explicitly, never charge it twice.

For suspected inefficiency, store a candidate label, evidence, rationale, alternative explanation, confidence and scope. Examples include repeating a resolved probe, failing to use discriminating feedback, plan-to-action conversion error, tool-state repair, or continued exploration after K. Justified exploration, verification, necessary selection and optimal execution are not automatically waste. Avoidable actions/time require a supported counterfactual or matched baseline; otherwise null. Timeout windows do not prove reasoning itself was slow.
