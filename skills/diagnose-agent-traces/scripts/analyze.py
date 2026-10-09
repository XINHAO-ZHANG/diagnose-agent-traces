"""Stage 3: statistics and comparison of annotation results. No model call.
Usage:
  python3 analyze.py --run RUN_DIR --run-packets PK --pass G1 --out OUT \\
      [--pass2 G2] [--base BASE_DIR --base-packets PK2 --base-pass G1 [--base-pass2 G2]] \\
      [--min-kappa 0.5] [--bootstrap 2000] [--seed 41] [--allow-mixed-pass]
Annotations are read from PK/annotations/<pass>/units/ (or from --ann-dir / --base-ann-dir / --ann2-dir / --base-ann2-dir).
Writes OUT/ANALYSIS.md, OUT/analysis.json, OUT/cells.csv. Exit 1 if a guard fails."""
import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from lib import load_benchmark

RWC = ["RW_PRODUCTIVE", "RW_OVERDELIBERATION", "RW_REDERIVE", "RW_BOARD_REDESCRIBE", "RW_DISCARDED", "RW_TOOL_DEBUG", "RW_LOCKIN_BATCH", "RW_UNCLEAR"]
NP = [c for c in RWC if c not in ('RW_PRODUCTIVE', 'RW_UNCLEAR')]
CODES = ["FM1_REPEATED_EXPLORATION", "FM2_FEEDBACK_NOT_USED", "FM3_NO_REVISION_AFTER_CONTRADICTION",
         "FM4_POST_K_DELAY", "FM5_EXECUTION_DEVIATION", "FM6_TOOL_OR_STATE_ERROR"]


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] / n * cb[k] / n for k in set(ca) | set(cb))
    return None if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


def pabak(pairs):
    return 2 * sum(a == b for a, b in pairs) / len(pairs) - 1 if pairs else None


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx, vy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy) if vx and vy else None


class RunData:
    """One run: packets (turn stats, outcomes), benchmark (tokens), and the annotation passes."""

    def __init__(self, run_dir, pk, pass_name, ann_dir, pass2, ann2_dir):
        self.run_dir, self.pk = Path(run_dir), Path(pk)
        meta = json.loads((self.pk / 'units.json').read_text())
        self.units = {u['uid']: u for u in meta['units']}
        plan = json.loads((self.pk / 'chunk_plan.json').read_text())['units']
        self.turns = {}      # (uid, record_id) -> stats
        for p in plan:
            for fn in p['chunk_files']:
                pkt = json.loads((self.pk / 'packets' / fn).read_text())
                for r in pkt['raw_excerpt'].get('records', []):
                    t = r['turn_stats']
                    self.turns[(p['uid'], r['record_id'])] = {'chars': t['reasoning_chars_full'],
                                                              'wall': t['wall_seconds_to_next_record'],
                                                              'actions': t['actions_in_turn']}
        bench = load_benchmark(self.run_dir)
        self.level_tokens = {}
        for g, B in bench.items():
            c = 0
            for i, a in enumerate(B['actions_per_level']):
                if a:
                    self.level_tokens[(g, i + 1)] = sum(x.get('generated_tokens') or 0 for x in B['history'][c:c + a]); c += a
        # keep only the units that have turn data (a packet with 'records'); other formats are not supported here
        with_turns = {uid for uid, _ in self.turns}
        self.units = {u: v for u, v in self.units.items() if u in with_turns}
        self.level_chars = defaultdict(int)
        for (uid, _), t in self.turns.items():
            u = self.units[uid]; self.level_chars[(u['game_id'], u['level'])] += t['chars']
        self.ann = {}
        for name, d in ((pass_name, ann_dir), (pass2, ann2_dir)):
            if name:
                self.ann[name] = self.load_ann(Path(d) if d else self.pk / 'annotations' / name)
        for ann in self.ann.values():
            ann['rows'] = {u: r for u, r in ann['rows'].items() if u in self.units}
            ann['rw'] = {u: r for u, r in ann['rw'].items() if u in self.units}
        self.main = pass_name
        self.second = pass2

    @staticmethod
    def load_ann(d):
        rows, rws = {}, {}
        for p in sorted((d / 'units').glob('*.row.json')):
            uid = p.name[:-len('.row.json')]
            rows[uid] = json.loads(p.read_text())
            rw = p.with_name(uid + '.rw.json')
            rws[uid] = json.loads(rw.read_text()) if rw.exists() else {'reasoning_waste': []}
        status = d / 'status.json'
        return {'rows': rows, 'rw': rws, 'status': json.loads(status.read_text()) if status.exists() else {}}

    def cells(self, name):
        out = []
        for uid, w in self.ann[name]['rw'].items():
            u = self.units.get(uid)
            if not u:
                continue
            seen = set()
            for x in w['reasoning_waste']:
                rid = x.get('record_id')
                t = self.turns.get((uid, rid))
                if not t or rid in seen:
                    continue
                seen.add(rid)
                lv = (u['game_id'], u['level'])
                tok = self.level_tokens.get(lv, 0) * t['chars'] / self.level_chars[lv] if self.level_chars[lv] else 0.0
                for cat, f in x['allocation'].items():
                    out.append({'uid': uid, 'game': u['game_id'], 'level': u['level'], 'record': rid, 'category': cat, 'frac': f,
                                'chars': f * t['chars'], 'wall_s': f * (t['wall'] or 0), 'tokens_est': f * tok,
                                'no_action_turn': t['actions'] == 0, 'has_wall': t['wall'] is not None})
        return out

    def cleared(self):
        return {(u['game_id'], u['level']): u['outcome']['actions'] for u in self.units.values()
                if u['outcome'].get('cleared') and u['outcome'].get('actions')}


def shares(cells, key):
    d = defaultdict(float)
    for c in cells:
        d[c['category']] += c[key]
    s = sum(d.values())
    return {k: (d[k] / s if s else None) for k in RWC}, s


def level_sums(cells, key):
    d = defaultdict(lambda: defaultdict(float))
    for c in cells:
        d[(c['game'], c['level'])][c['category']] += c[key]
    return d


def bootstrap_diff(run_l, base_l, levels, cats, B, seed):
    """Paired bootstrap over levels: share(cats) in run minus share(cats) in base."""
    rng = random.Random(seed)
    levels = [lv for lv in levels if lv in run_l and lv in base_l]
    if not levels:
        return None

    def share(src, sample):
        num = sum(sum(src[lv][c] for c in cats) for lv in sample)
        den = sum(sum(src[lv].values()) for lv in sample)
        return num / den if den else None
    point = share(run_l, levels) - share(base_l, levels)
    ds = []
    for _ in range(B):
        s = [rng.choice(levels) for _ in levels]
        a, b = share(run_l, s), share(base_l, s)
        if a is not None and b is not None:
            ds.append(a - b)
    ds.sort()
    return {'levels': len(levels), 'diff': point, 'lo': ds[int(0.025 * len(ds))], 'hi': ds[int(0.975 * len(ds)) - 1],
            'p_gt_0': sum(d > 0 for d in ds) / len(ds)}


def fm_table(rows, pairs=None):
    out = {}
    for c in CODES:
        v = [(uid, r['failure_modes'].get(c, {})) for uid, r in rows.items()]
        v = [(uid, f) for uid, f in v if pairs is None or pairs(uid)]
        k = sum(f.get('present') is True for _, f in v); n = sum(f.get('present') in (True, False) for _, f in v)
        cost = [f.get('cost_actions') for _, f in v if f.get('present') is True and isinstance(f.get('cost_actions'), int)]
        out[c] = {'present': k, 'assessed': n, 'units': len(v), 'cost_known_actions': sum(cost), 'cost_known_n': len(cost)}
    return out


def agreement(a, b, units_filter=None):
    shared = sorted(set(a['rows']) & set(b['rows']))
    shared = [u for u in shared if units_filter is None or units_filter(u)]
    res = {'shared_units': len(shared), 'fm': {}}
    pooled, kaps = [], []
    for c in CODES:
        pr = [(a['rows'][u]['failure_modes'][c].get('present'), b['rows'][u]['failure_modes'][c].get('present')) for u in shared]
        pr = [(x, y) for x, y in pr if x is not None and y is not None]
        pooled += pr
        k = kappa(pr)
        if k is not None:
            kaps.append(k)
        res['fm'][c] = {'n': len(pr), 'kappa': k, 'pabak': pabak(pr), 'positives_a': sum(x for x, _ in pr), 'positives_b': sum(y for _, y in pr)}
    res['fm_macro_kappa'] = sum(kaps) / len(kaps) if kaps else None
    res['fm_pooled_kappa'] = kappa(pooled)
    dom, npr = {}, {}
    for u in shared:
        da = {x['record_id']: x['allocation'] for x in a['rw'][u]['reasoning_waste']}
        db = {x['record_id']: x['allocation'] for x in b['rw'][u]['reasoning_waste']}
        for rid in set(da) & set(db):
            dom[(u, rid)] = (max(da[rid].items(), key=lambda kv: kv[1])[0], max(db[rid].items(), key=lambda kv: kv[1])[0])
            npr[(u, rid)] = (1 - da[rid].get('RW_PRODUCTIVE', 0), 1 - db[rid].get('RW_PRODUCTIVE', 0))
    res['turns'] = len(dom)
    res['dominant_agreement'] = sum(x == y for x, y in dom.values()) / len(dom) if dom else None
    res['dominant_kappa'] = kappa(list(dom.values()))
    res['nonprod_r'] = pearson([x for x, _ in npr.values()], [y for _, y in npr.values()])
    res['rw_category_kappa'] = {cat: kappa([(x == cat, y == cat) for x, y in dom.values()]) for cat in RWC if cat != 'RW_UNCLEAR'}
    return res


def pct(x, nd=1):
    return 'n/a' if x is None else f'{x * 100:.{nd}f}%'


def f3(x):
    return 'n/a' if x is None else f'{x:.2f}'


def guards(name, rd, pass_name):
    """Facts about one annotation pass: model, prompt hash, quote rate, tool use, coverage."""
    ann = rd.ann[pass_name]; rows = ann['rows']
    models = {r.get('annotator_model') for r in rows.values()}; shas = {r.get('prompt_sha256') for r in rows.values()}
    q = sum(w.get('quotes', 0) for w in ann['rw'].values()); qv = sum(w.get('quotes_verified', 0) for w in ann['rw'].values())
    tool = [u for u, w in ann['rw'].items() if w.get('tool_events')]
    cells = rd.cells(pass_name)
    lab = sum(c['wall_s'] for c in cells)
    tot = sum(t['wall'] or 0 for t in rd.turns.values())
    return {'name': name, 'pass': pass_name, 'units_annotated': len(rows), 'units_total': len(rd.units), 'models': sorted(m or '?' for m in models),
            'prompt_sha256': sorted(s or '?' for s in shas),
            'inputs_sha256': sorted({r.get('inputs_sha256') for r in rows.values() if r.get('inputs_sha256')}), 'quotes': q, 'quotes_verified': qv, 'units_with_tool_use': tool,
            'labeled_wall_share': lab / tot if tot else None, 'status_state': ann['status'].get('state')}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True); ap.add_argument('--run-packets', required=True)
    ap.add_argument('--pass', dest='pass_name', required=True); ap.add_argument('--ann-dir')
    ap.add_argument('--pass2'); ap.add_argument('--ann2-dir')
    ap.add_argument('--base'); ap.add_argument('--base-packets'); ap.add_argument('--base-pass'); ap.add_argument('--base-ann-dir')
    ap.add_argument('--base-pass2'); ap.add_argument('--base-ann2-dir')
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-kappa', type=float, default=0.5, help='trust threshold. Set it before you read the results (default 0.5)')
    ap.add_argument('--bootstrap', type=int, default=2000); ap.add_argument('--seed', type=int, default=41)
    ap.add_argument('--allow-mixed-pass', action='store_true', help='compare runs that were not annotated in the same pass (not for decisions)')
    a = ap.parse_args(argv)
    run = RunData(a.run, a.run_packets, a.pass_name, a.ann_dir, a.pass2, a.ann2_dir)
    base = RunData(a.base, a.base_packets, a.base_pass or a.pass_name, a.base_ann_dir, a.base_pass2, a.base_ann2_dir) if a.base else None
    bpass = (a.base_pass or a.pass_name) if base else None
    G = [guards('run', run, a.pass_name)] + ([guards('base', base, bpass)] if base else [])
    fails, warns = [], []
    for g in G:
        if g['units_annotated'] < g['units_total']:
            warns.append(f"{g['name']}: {g['units_annotated']} of {g['units_total']} units are annotated")
        if g['units_with_tool_use']:
            warns.append(f"{g['name']}: the annotator used tools on {len(g['units_with_tool_use'])} units (not blind): {g['units_with_tool_use'][:5]}")
        if g['quotes'] and g['quotes_verified'] / g['quotes'] < 0.7:
            warns.append(f"{g['name']}: only {g['quotes_verified']}/{g['quotes']} quotes are verbatim")
    if base:
        norm = lambda g: sorted({m.split(' (')[0] for m in g['models']})
        ins = [g['inputs_sha256'] for g in G]
        if norm(G[0]) != norm(G[1]) or G[0]['prompt_sha256'] != G[1]['prompt_sha256'] or (ins[0] and ins[1] and ins[0] != ins[1]):
            msg = f"run and base were not annotated with the same model and prompt: {norm(G[0])} {[x[:10] for x in G[0]['prompt_sha256']]} vs {norm(G[1])} {[x[:10] for x in G[1]['prompt_sha256']]}"
            (warns if a.allow_mixed_pass else fails).append(msg)
        elif G[0]['models'] != G[1]['models']:
            warns.append(f"the model name is the same, but the variant that the service reported differs: {G[0]['models']} vs {G[1]['models']}")
    out = {'guards': G, 'fail': fails, 'warn': warns, 'min_kappa': a.min_kappa}
    cells_run = run.cells(a.pass_name)
    cells_base = base.cells(bpass) if base else None
    L = ['# Stage 3: annotation statistics', '', '## Guards', '']
    for g in G:
        L.append(f"- {g['name']}: {g['units_annotated']}/{g['units_total']} units, model {g['models']}, prompt {[s[:10] for s in g['prompt_sha256']]}, "
                 f"quotes verbatim {g['quotes_verified']}/{g['quotes']}, labeled share of wall-clock {pct(g['labeled_wall_share'])}, "
                 f"annotator tool use on {len(g['units_with_tool_use'])} units.")
    L += [f'- FAIL: {m}' for m in fails] + [f'- WARN: {m}' for m in warns]
    if fails:
        L += ['', 'Stop. The comparison below is not valid.']
    # ---- table 1: shares per category
    def cat_table(title, cs_run, cs_base):
        L.extend(['', f'## {title}', '', '| Category | Run wall s | Run share of wall | Run share of tokens |' + (' Base share of wall | Base share of tokens |' if cs_base is not None else ''),
                  '|---|---|---|---|' + ('---|---|' if cs_base is not None else '')])
        rw_, tw = shares(cs_run, 'wall_s'); rt_, _ = shares(cs_run, 'tokens_est')
        bw = bt = None
        if cs_base is not None:
            bw, _ = shares(cs_base, 'wall_s'); bt, _ = shares(cs_base, 'tokens_est')
        for c in RWC:
            row = f"| {c[3:].lower()} | {sum(x['wall_s'] for x in cs_run if x['category'] == c):,.0f} | {pct(rw_[c])} | {pct(rt_[c])} |"
            if cs_base is not None:
                row += f' {pct(bw[c])} | {pct(bt[c])} |'
            L.append(row)
        npw = sum(rw_[c] or 0 for c in NP); npt = sum(rt_[c] or 0 for c in NP)
        row = f'| **not productive** | | {pct(npw)} | {pct(npt)} |'
        if cs_base is not None:
            row += f" {pct(sum(bw[c] or 0 for c in NP))} | {pct(sum(bt[c] or 0 for c in NP))} |"
        L.append(row)
        na = [c for c in cs_run if c['no_action_turn']]
        if na:
            nw, _ = shares(na, 'wall_s')
            L.append(f"\nIn turns with no action: {sum(c['wall_s'] for c in na):,.0f} s labeled, not productive {pct(sum(nw[c] or 0 for c in NP))}, over-deliberation {pct(nw['RW_OVERDELIBERATION'])}.")
        return rw_, rt_
    sh_w, sh_t = cat_table('Reasoning waste, all annotated units' + (' (run and base)' if base else ''), cells_run, cells_base)
    out['shares_all'] = {'wall': sh_w, 'tokens': sh_t}
    # ---- paired comparison
    if base:
        cr, cb = run.cleared(), base.cleared()
        pl = sorted(set(cr) & set(cb))
        out['paired_levels'] = len(pl)
        pr = [c for c in cells_run if (c['game'], c['level']) in pl]; pb = [c for c in cells_base if (c['game'], c['level']) in pl]
        if len(pl) < 10:
            warns.append(f'only {len(pl)} paired levels: treat the comparison as a hint')
        L += ['', f'## Paired levels ({len(pl)} levels that both runs cleared)']
        cat_table('Reasoning waste, paired levels', pr, pb)
        L += ['', '### Difference run minus base, paired bootstrap over levels (95% interval)', '',
              '| Measure | Difference | 95% interval | P(difference > 0) | Levels |', '|---|---|---|---|---|']
        out['bootstrap'] = {}
        for label, key, cats in (('productive share of tokens', 'tokens_est', ['RW_PRODUCTIVE']), ('productive share of wall-clock', 'wall_s', ['RW_PRODUCTIVE']),
                                 ('over-deliberation share of tokens', 'tokens_est', ['RW_OVERDELIBERATION']), ('not-productive share of tokens', 'tokens_est', NP)):
            bs = bootstrap_diff(level_sums(pr, key), level_sums(pb, key), pl, cats, a.bootstrap, a.seed)
            out['bootstrap'][label] = bs
            if bs:
                L.append(f"| {label} | {bs['diff'] * 100:+.1f} pt | {bs['lo'] * 100:+.1f} to {bs['hi'] * 100:+.1f} | {bs['p_gt_0']:.2f} | {bs['levels']} |")
        L += ['', 'An interval that contains 0 means: the data do not show a difference. Do not use the shares as a pass or fail test.']
        ra = sum(cr[lv] for lv in pl); rb = sum(cb[lv] for lv in pl)
        L += ['', f'Actions on paired levels: run {ra}, base {rb}, net {ra - rb:+d}.']
        out['paired_actions'] = {'run': ra, 'base': rb}
    # ---- failure modes
    L += ['', '## Failure modes (present / assessed)', '']
    fr = fm_table(run.ann[a.pass_name]['rows']); out['fm_run'] = fr
    fb = fm_table(base.ann[bpass]['rows']) if base else None
    out['fm_base'] = fb
    L += ['| Code | Run |' + (' Base |' if base else '') + ' Known action cost (run) |', '|---|---|' + ('---|' if base else '') + '---|']
    for c in CODES:
        x = fr[c]; row = f"| {c} | {x['present']}/{x['assessed']} |"
        if base:
            y = fb[c]; row += f" {y['present']}/{y['assessed']} |"
        L.append(row + f" {x['cost_known_actions']} actions in {x['cost_known_n']} levels |")
    L += ['', 'The action cost is the number of actions that the pattern used where the trace shows it. It is not the number of actions that we could save.']
    # ---- agreement and trust
    ag = None
    if a.pass2:
        ag = agreement(run.ann[a.pass_name], run.ann[a.pass2]); out['agreement_run'] = ag
        L += ['', f'## Agreement between two passes of the run ({a.pass_name} and {a.pass2}), {ag["shared_units"]} units, {ag["turns"]} turns', '',
              f"Failure modes: macro kappa {f3(ag['fm_macro_kappa'])}, pooled kappa {f3(ag['fm_pooled_kappa'])}. "
              f"Top category of a turn: agreement {pct(ag['dominant_agreement'])}, kappa {f3(ag['dominant_kappa'])}. "
              f"Not-productive share: correlation {f3(ag['nonprod_r'])}.", '',
              f'Trust threshold: kappa at least {a.min_kappa}.', '', '| Item | Kappa | PABAK | Cases | Use? |', '|---|---|---|---|---|']
        for c in CODES:
            x = ag['fm'][c]
            L.append(f"| {c} | {f3(x['kappa'])} | {f3(x['pabak'])} | {x['positives_a']}/{x['positives_b']} of {x['n']} | {'yes' if (x['kappa'] or -1) >= a.min_kappa else 'no'} |")
        for cat, k in ag['rw_category_kappa'].items():
            L.append(f"| {cat} (top of turn) | {f3(k)} | | | {'yes' if (k or -1) >= a.min_kappa else 'no'} |")
        L += ['', 'PABAK is more stable than kappa for rare codes. A code with few cases and low kappa is not usable.']
    else:
        L += ['', '## Agreement', '', 'No second pass was given (`--pass2`). The labels have no noise estimate.']
    if base and a.base_pass2:
        agb = agreement(base.ann[bpass], base.ann[a.base_pass2]); out['agreement_base'] = agb
    out['warn'] = warns
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    (outd / 'analysis.json').write_text(json.dumps(out, indent=1, default=str))
    cols = ['run', 'uid', 'game', 'level', 'record', 'category', 'frac', 'chars', 'wall_s', 'tokens_est', 'no_action_turn']
    with open(outd / 'cells.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore'); w.writeheader()
        for tag, cs in (('run', cells_run), ('base', cells_base or [])):
            for c in cs:
                w.writerow(dict(c, run=tag))
    # warnings can grow after the guard list is printed; list them again at the end
    (outd / 'ANALYSIS.md').write_text('\n'.join(L) + '\n')
    print('\n'.join(L))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
