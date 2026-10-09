
## G1/G2 RUN ADDENDUM (full traces; appended after the v1.1-cursor prompt, which is otherwise unchanged)
- In this run `raw_excerpt` is the FULL, untruncated trajectory: every section text is complete and there are no
  `…[truncated N chars]…` markers. Statements above about truncation do not apply; judge from the full text.
- If `chunk` is present in the UNIT PACKET, the unit was split on turn/step boundaries because it exceeds the context
  window. You see only chunk `chunk.index` of `chunk.total` (records/steps listed). `prior_chunks_summary` (if present)
  holds facts carried over from the earlier chunks, written by an earlier call of this same annotation; treat it as
  context, not as evidence (quotes must come from this chunk's `raw_excerpt`).
  For a chunk: allocate `reasoning_waste` only for the records/steps in this chunk; judge each FM code ONLY on the
  evidence in this chunk plus the summary (present=true needs a quote or observation from this chunk; use null if this
  chunk alone cannot decide); give milestones only if they occur in this chunk (else status "unknown" with null actions).
  Add one extra top-level field `carry_over_summary`: at most 350 words listing the established facts, mechanics,
  coordinates, hypotheses (tested / untested), plans in progress and FM-relevant events (with record ids / steps) that
  a reader of the NEXT chunk needs.
