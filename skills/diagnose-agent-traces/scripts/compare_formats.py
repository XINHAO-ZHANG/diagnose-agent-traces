"""Compare two annotation formats on the same units. No model call.
Usage: python3 compare_formats.py --a-dirs ANN_G1,ANN_G2 --b-dirs ANN_G1,ANN_G2 [--uids-file F] [--tolerance 0.05] --out FILE
Each --*-dirs is two annotation directories (with units/) of the same format: two independent passes.
It measures the agreement between the two passes inside each format, on the units that all four directories have.
Rule, fixed before the test: keep format B if its top-category kappa and its failure-mode macro kappa are
each at least (those of A minus the tolerance), and at least 90% of its turns have a summary and a reason."""
import argparse
import json
import sys
from pathlib import Path

from analyze import RunData, agreement


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--a-dirs', required=True); ap.add_argument('--b-dirs', required=True)
    ap.add_argument('--uids-file'); ap.add_argument('--tolerance', type=float, default=0.05); ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    A = [RunData.load_ann(Path(d)) for d in a.a_dirs.split(',')]
    B = [RunData.load_ann(Path(d)) for d in a.b_dirs.split(',')]
    common = set(A[0]['rows']) & set(A[1]['rows']) & set(B[0]['rows']) & set(B[1]['rows'])
    if a.uids_file:
        common &= {l.strip() for l in Path(a.uids_file).read_text().splitlines() if l.strip()}
    keep = lambda u: u in common
    ga, gb = agreement(A[0], A[1], keep), agreement(B[0], B[1], keep)

    def cover(ann):
        items = [x for u in common for x in ann['rw'][u]['reasoning_waste']]
        ok = [x for x in items if x.get('summary') and x.get('reason')]
        return len(ok), len(items)
    def out_tokens(ann):
        v = [ann['rw'][u].get('usage', {}).get('outputTokens', 0) for u in common]
        return sum(v) / len(v) if v else None
    def cost(ann):
        return sum(ann['rw'][u].get('cost_usd') or 0 for u in common)
    ca = [cover(x) for x in B]
    cov = sum(c[0] for c in ca) / max(1, sum(c[1] for c in ca))
    # per-turn difference of the not-productive share between the two formats (same pass index)
    diffs = []
    for i in (0, 1):
        for u in common:
            da = {x['record_id']: 1 - x['allocation'].get('RW_PRODUCTIVE', 0) for x in A[i]['rw'][u]['reasoning_waste']}
            db = {x['record_id']: 1 - x['allocation'].get('RW_PRODUCTIVE', 0) for x in B[i]['rw'][u]['reasoning_waste']}
            diffs += [db[r] - da[r] for r in set(da) & set(db)]
    f = lambda x: 'n/a' if x is None else f'{x:.2f}'
    keep_b = (gb['dominant_kappa'] is not None and ga['dominant_kappa'] is not None and gb['dominant_kappa'] >= ga['dominant_kappa'] - a.tolerance
              and gb['fm_macro_kappa'] >= ga['fm_macro_kappa'] - a.tolerance and cov >= 0.9)
    L = ['# Format comparison', '', f'Units that all four passes have: {len(common)}. Turns: A {ga["turns"]}, B {gb["turns"]}.',
         'This is a small test. Read the numbers as a check, not as a proof.', '',
         '| Measure | Format A | Format B |', '|---|---|---|',
         f'| Top-category kappa between the two passes | {f(ga["dominant_kappa"])} | {f(gb["dominant_kappa"])} |',
         f'| Top-category agreement | {f(ga["dominant_agreement"])} | {f(gb["dominant_agreement"])} |',
         f'| Not-productive share, correlation between passes | {f(ga["nonprod_r"])} | {f(gb["nonprod_r"])} |',
         f'| Failure-mode macro kappa | {f(ga["fm_macro_kappa"])} | {f(gb["fm_macro_kappa"])} |',
         f'| Failure-mode pooled kappa | {f(ga["fm_pooled_kappa"])} | {f(gb["fm_pooled_kappa"])} |',
         f'| Mean output tokens per unit (pass 1) | {out_tokens(A[0]):.0f} | {out_tokens(B[0]):.0f} |',
         f'| Cost of the two passes on these units | ${cost(A[0]) + cost(A[1]):.3f} | ${cost(B[0]) + cost(B[1]):.3f} |', '',
         f'Turns of format B with a summary and a reason: {cov:.0%}.',
         f'Mean change of the not-productive share per turn, B minus A (same pass index): {sum(diffs) / len(diffs):+.3f} over {len(diffs)} turns.' if diffs else '',
         '', f'Rule (tolerance {a.tolerance}): **{"keep format B" if keep_b else "do not switch to format B"}**.']
    Path(a.out).write_text('\n'.join(L) + '\n'); print('\n'.join(L))
    return 0 if keep_b else 1


if __name__ == '__main__':
    sys.exit(main())
