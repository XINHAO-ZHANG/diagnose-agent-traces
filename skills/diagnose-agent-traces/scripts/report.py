"""Stage 4: write the issue-ready report from the outputs of stages 0 to 3. No model call.
Usage: python3 report.py --stage1 DIR --analysis DIR --run-packets PK --pass G1 --out REPORT.md
           --run-name NAME [--preflight DIR] [--base-name NAME] [--level GAME:LEVEL] [--min-share-for-action 0.2]
Every number in the report is read from the earlier outputs. The sentences that explain the numbers are fixed
rules. The section 'What this means' lists only rows whose condition holds. A human must read and edit the result."""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CATS = ['RW_PRODUCTIVE', 'RW_OVERDELIBERATION', 'RW_REDERIVE', 'RW_BOARD_REDESCRIBE', 'RW_DISCARDED', 'RW_TOOL_DEBUG', 'RW_LOCKIN_BATCH', 'RW_UNCLEAR']
NP = [c for c in CATS if c not in ('RW_PRODUCTIVE', 'RW_UNCLEAR')]
LETTER = {'RW_PRODUCTIVE': 'P', 'RW_OVERDELIBERATION': 'O', 'RW_REDERIVE': 'R', 'RW_BOARD_REDESCRIBE': 'B', 'RW_DISCARDED': 'D',
          'RW_TOOL_DEBUG': 'T', 'RW_LOCKIN_BATCH': 'L', 'RW_UNCLEAR': 'U'}
NAME = {'RW_PRODUCTIVE': 'productive', 'RW_OVERDELIBERATION': 'over-deliberation', 'RW_REDERIVE': 're-derive',
        'RW_BOARD_REDESCRIBE': 'board re-describe', 'RW_DISCARDED': 'discarded plan', 'RW_TOOL_DEBUG': 'tool debug',
        'RW_LOCKIN_BATCH': 'lock-in batch', 'RW_UNCLEAR': 'unclear'}


def pct(x, nd=1):
    return 'n/a' if x is None else f'{x * 100:.{nd}f}%'


def load(p):
    return json.loads(Path(p).read_text())


def load_turns(pk, uid):
    plan = next(p for p in load(Path(pk) / 'chunk_plan.json')['units'] if p['uid'] == uid)
    out = []
    for fn in plan['chunk_files']:
        for r in load(Path(pk) / 'packets' / fn)['raw_excerpt'].get('records', []):
            t = r['turn_stats']
            out.append({'id': r['record_id'], 'wall': t['wall_seconds_to_next_record'], 'actions': t['actions_in_turn'],
                        'yield': 'turn_time_budget' in (t['turn_end_status'] or '')})
    return out


def stretch(turns, max_actions=1, min_len=3):
    """The run of consecutive turns (with wall time) that has at most `max_actions` actions and the most seconds."""
    best = None
    for i in range(len(turns)):
        w = a = 0
        for j in range(i, len(turns)):
            t = turns[j]
            if t['wall'] is None or t['actions'] is None:
                break
            w += t['wall']; a += t['actions']
            if a > max_actions:
                break
            if j - i + 1 >= min_len and (best is None or w > best[2]):
                best = (i, j, w, a)
    return best


def pick_example(run_packets, level=None, ann_dir=None):
    """The unit for the example: the one with the longest stretch of at most 1 action (or the level given as GAME:LEVEL).
    Returns (uid, unit, turns, stretch) or None."""
    units = {u['uid']: u for u in load(Path(run_packets) / 'units.json')['units']}
    cand = []
    for uid, u in units.items():
        if level and f'{u["game_id"]}:{u["level"]}' != level:
            continue
        if ann_dir is not None and not (Path(ann_dir) / 'units' / f'{uid}.rw.json').exists():
            continue       # a unit without an annotation cannot be the example
        try:
            turns = load_turns(run_packets, uid)
        except StopIteration:
            continue
        st = stretch(turns)
        if st:
            cand.append((st[2], uid, turns, st))
    if not cand:
        return None
    _, uid, turns, st = max(cand, key=lambda c: c[0])
    return uid, units[uid], turns, st


def time_bar(turns, hi):
    tot = sum(t['wall'] or 0 for t in turns)
    scale = next((s for s in (10, 30, 60, 120, 300) if tot / s <= 80), 600)
    bar, labels, marks, pos = '|', ' ', ' ', {}
    for k, t in enumerate(turns):
        if t['wall'] is None:
            continue
        w = max(1, round(t['wall'] / scale))
        pos[k] = (len(bar), len(bar) + w)
        bar += ('█' if t['actions'] else '·') * w + '|'
    labels = [' '] * len(bar); marks = [' '] * len(bar)
    for k, (s, e) in pos.items():
        name = turns[k]['id'].replace('record-', 'r')
        if e - s >= len(name):
            for i, ch in enumerate(name):
                labels[s + i] = ch
    if hi and hi[0] in pos and hi[1] in pos:
        for i in range(pos[hi[0]][0], pos[hi[1]][1]):
            marks[i] = '^'
    return scale, ''.join(labels), bar, ''.join(marks)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--stage1', required=True); ap.add_argument('--analysis', required=True)
    ap.add_argument('--run-packets', required=True); ap.add_argument('--pass', dest='pass_name', required=True)
    ap.add_argument('--ann-dir'); ap.add_argument('--preflight')
    ap.add_argument('--summary-ann-dir', help='annotation dir (format v1.2) with the turn summaries of the example level. The shares still come from the main pass')
    ap.add_argument('--run-name', required=True); ap.add_argument('--base-name', default='the baseline')
    ap.add_argument('--level', help='GAME:LEVEL for the example. Default: the unit with the longest stretch of turns with at most 1 action')
    ap.add_argument('--out', required=True)
    ap.add_argument('--no-action-row-share', type=float, default=0.2,
                    help='add the row about turns with no action when they use at least this share of wall-clock (default 0.2)')
    a = ap.parse_args(argv)
    m = load(Path(a.stage1) / 'metrics.json'); an = load(Path(a.analysis) / 'analysis.json')
    run, base = m['run'], m.get('base')
    cats = run['categories']; total = run['total_wall_s']
    sec = lambda k: cats.get(k, {'seconds': 0})['seconds']
    na = sum(sec(k) for k in cats if k != 'action_turn')
    yields = cats.get('no_action_turn_budget_yield', {'turns': 0, 'seconds': 0}); rto = cats.get('request_timeout', {'turns': 0, 'seconds': 0})
    hit = [g for g, s in run['games'].items() if s['hit_time_limit']]
    sh = an['shares_all']['wall']; nps = sum(sh[c] or 0 for c in NP)
    top = max(NP, key=lambda c: sh[c] or 0)
    ag = an.get('agreement_run'); mk = an['min_kappa']
    trusted_cat = lambda c: bool(ag) and (ag['rw_category_kappa'].get(c) or -1) >= mk
    trusted_fm = lambda c: bool(ag) and (ag['fm'][c]['kappa'] or -1) >= mk
    bs = an.get('bootstrap') or {}
    L = [f'# Failure tracing: where {a.run_name} loses time', '', 'Status: generated draft. A human must read it and edit it. Not posted.', '',
         '## Summary', '',
         f'- {pct(na / total)} of the wall-clock ({na:,} of {total:,} s, all games) goes to turns with no game action '
         f'(turn-budget yields, read timeouts and the final stop). {yields["turns"]} turns end in a turn-budget yield and {rto["turns"]} in a read timeout.',
         f'- {len(hit)} of {len(run["games"])} games used the whole time limit.',
         f'- {pct(nps)} of the labeled reasoning time is not productive. The largest category is {NAME[top]} ({pct(sh[top])}).'
         + ('' if trusted_cat(top) else ' The agreement for this category is below the trust threshold.' if ag else ' There is no second pass, so the labels have no noise estimate.')]
    pm = bs.get('productive share of tokens')
    if pm:
        cont = pm['lo'] <= 0 <= pm['hi']
        L.append(f'- Against {a.base_name}, on {pm["levels"]} paired levels: ' + (
            f'the data do not show a difference in the productive share of tokens ({pm["diff"] * 100:+.1f} points, interval {pm["lo"] * 100:+.1f} to {pm["hi"] * 100:+.1f}).' if cont else
            f'the productive share of tokens is {abs(pm["diff"]) * 100:.1f} points {"higher" if pm["diff"] > 0 else "lower"} (interval {pm["lo"] * 100:+.1f} to {pm["hi"] * 100:+.1f}).'))
    # ---- data and guards
    L += ['', '## Data and annotation', '']
    if a.preflight:
        pf = load(Path(a.preflight) / 'preflight.json')
        low = [g['game'] for g in pf['games'] if (g.get('text_share') or 0) < 0.9]
        L.append(f'- Reasoning text: {len(pf["games"]) - len(low)} of {len(pf["games"])} games have the full reasoning text.' + (f' Games with little text: {low}.' if low else ''))
    for g in an['guards']:
        L.append(f'- {g["name"]}: {g["units_annotated"]} of {g["units_total"]} units annotated by {g["models"][0]}; '
                 f'{g["quotes_verified"]} of {g["quotes"]} quotes are verbatim; the annotator used tools on {len(g["units_with_tool_use"])} units.')
    L += [f'- WARNING: {w}' for w in an.get('warn', [])] + [f'- FAIL: {w}' for w in an.get('fail', [])]
    # ---- counted results
    L += ['', '## Result 1: time without action (counted, no annotator)', '', '| Category | Turns | Seconds | Share of wall-clock |', '|---|---|---|---|']
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1]['seconds']):
        L.append(f'| {k} | {v["turns"]} | {v["seconds"]:,} | {pct(v["share"])} |')
    if hit:
        L += ['', 'Games that used the time limit and had the most time in turn-budget yields:', '', '| Game | Levels | Wall s | Yield s | Share |', '|---|---|---|---|---|']
        for g in sorted(hit, key=lambda g: -run['games'][g]['categories'].get('no_action_turn_budget_yield', {'seconds': 0})['seconds'])[:5]:
            s = run['games'][g]; y = s['categories'].get('no_action_turn_budget_yield', {'seconds': 0})['seconds']
            L.append(f'| {g} | {s["levels_completed"]}/{s["n_levels"]} | {s["final_wallclock_s"]:,} | {y:,} | {pct(y / s["final_wallclock_s"])} |')
    # ---- waste
    L += ['', '## Result 2: reasoning waste', '', f'Share of the labeled wall-clock time (annotator pass {a.pass_name}).']
    if ag:
        L += ['Kappa is the agreement between two independent passes on the top category of each turn (' + f'{ag["turns"]} turns). "Use" is yes when kappa reaches {mk}.', '',
              '| Category | Share | Kappa | Use |', '|---|---|---|---|']
        for c in CATS:
            k = ag['rw_category_kappa'].get(c)
            k_txt = 'n/a' if k is None else '%.2f' % k
            use = 'yes' if trusted_cat(c) else ('no' if k is not None else 'n/a')
            L.append(f'| {NAME[c]} | {pct(sh[c])} | {k_txt} | {use} |')
        r_txt = 'n/a' if ag['nonprod_r'] is None else '%.2f' % ag['nonprod_r']
        L.append(f'| **not productive** | {pct(nps)} | r = {r_txt} | see note |')
        L += ['', 'For the total "not productive", r is the correlation of the not-productive share of a turn between the two passes. '
              'The total is steadier than the single categories: a turn can move between two not-productive categories and still count as not productive.']
    else:
        L += ['There is no second pass, so there is no agreement number.', '', '| Category | Share |', '|---|---|']
        for c in CATS:
            L.append(f'| {NAME[c]} | {pct(sh[c])} |')
        L.append(f'| **not productive** | {pct(nps)} |')
    if pm:
        L += ['', f'## Result 3: comparison with {a.base_name}', '', f'Paired levels: {an["paired_levels"]}. Difference = run minus base, paired bootstrap over levels.', '',
              '| Measure | Difference | 95% interval | Levels |', '|---|---|---|---|']
        for k, v in bs.items():
            if v:
                L.append(f'| {k} | {v["diff"] * 100:+.1f} pt | {v["lo"] * 100:+.1f} to {v["hi"] * 100:+.1f} | {v["levels"]} |')
        pa = an.get('paired_actions')
        if pa:
            L.append(f'\nActions on paired levels: run {pa["run"]}, base {pa["base"]}, net {pa["run"] - pa["base"]:+d}.')
    # ---- failure modes
    L += ['', f'## Result {4 if pm else 3}: failure modes', '', 'present / assessed. Kappa is the agreement between two independent passes (1 is full agreement, 0 is the same as chance). "Use" is yes when kappa reaches ' + f'{mk}.', '', '| Code | Run | Kappa | Use |', '|---|---|---|---|']
    for c, v in an['fm_run'].items():
        k = ag['fm'][c]['kappa'] if ag else None
        L.append(f'| {c} | {v["present"]}/{v["assessed"]} | {"n/a" if k is None else f"{k:.2f}"} | {"yes" if trusted_fm(c) else "no"} |')
    # ---- example level
    cells = defaultdict(lambda: defaultdict(float))
    with open(Path(a.analysis) / 'cells.csv') as fh:
        for r in csv.DictReader(fh):
            if r['run'] == 'run':
                cells[(r['uid'], r['record'])][r['category']] = float(r['frac'])
    ann_dir = Path(a.ann_dir) if a.ann_dir else Path(a.run_packets) / 'annotations' / a.pass_name
    ex = pick_example(a.run_packets, a.level, ann_dir)
    L += ['', '## Example level']
    if not ex:
        L += ['', 'No level has a stretch of 3 or more turns with at most 1 action.']
    else:
        uid, u, turns, st = ex
        lvl_total = sum(t['wall'] or 0 for t in turns)
        rw = {x['record_id']: x for x in load(ann_dir / 'units' / f'{uid}.rw.json')['reasoning_waste']}
        i, j, w, acts = st
        known = sum(t['actions'] or 0 for t in turns)
        total_acts = u['outcome'].get('actions')
        last_fill = (total_acts - known) if (turns[-1]['actions'] is None and total_acts is not None and total_acts >= known) else None
        L += ['', f'**{u["game_id"]} level {u["level"]}.** Turns {turns[i]["id"].replace("record-", "r")} to {turns[j]["id"].replace("record-", "r")} '
              f'took {w:,.0f} s ({pct(w / lvl_total, 0)} of the level) and had {acts} action{"s" if acts != 1 else ""}.',
              '', f'The level has {len(turns)} turns and {lvl_total:,.0f} s of measured wall-clock time. '
              '"yield" means the turn budget ended before an action ran. Turns without a wall-clock time are not in the totals.', '']
        scale, lab, bar, mark = time_bar(turns, (i, j))
        sum_rw = rw
        sfile = Path(a.summary_ann_dir) / 'units' / f'{uid}.rw.json' if a.summary_ann_dir else None
        if sfile and sfile.exists():
            sum_rw = {x['record_id']: x for x in load(sfile)['reasoning_waste']}
        has_sum = any(x.get('summary') for x in sum_rw.values())
        L += ['```', f' time bar: 1 character = {scale} s.   █ = turn with action(s)   · = turn with no action', ' ' + lab, ' ' + bar, ' ' + mark, '```', '',
              'Shares are in percent (P productive, O over-deliberation, R re-derive, B board re-describe, D discarded plan, T tool debug, L lock-in batch).', '',
              ('| Turn | Time | Actions | What the turn is about (annotator summary) | Annotator shares | Quote from the annotator |' if has_sum else
               '| Turn | Time | Actions | Annotator shares | Quote from the annotator |'), '|---|---|---|---|---|' + ('---|' if has_sum else '')]
        for k, t in enumerate(turns):
            al = cells.get((uid, t['id']), {})
            shs = ', '.join(f'{LETTER[c]} {v * 100:.0f}' for c, v in sorted(al.items(), key=lambda kv: -kv[1]) if v >= 0.05)
            q = rw.get(t['id'], {}).get('quote')
            qv = rw.get(t['id'], {}).get('quote_verified')
            qs = f'"{q}"' if q and qv else ('(quote is not verbatim)' if q else '')
            tm = f'{t["wall"]:,.0f} s' if t['wall'] is not None else 'not measured'
            if t['actions'] is not None:
                ac = f'{t["actions"]}' + (' (yield)' if t['yield'] else '')
            else:
                ac = f'{last_fill} (level total minus the other turns)' if (last_fill is not None and k == len(turns) - 1) else '?'
            sm = (sum_rw.get(t['id'], {}).get('summary') or '').replace('|', '/')
            row = f'| {t["id"].replace("record-", "r")} | {tm} | {ac} | ' + (f'{sm} | ' if has_sum else '') + f'{shs} | {qs} |'
            L.append(row.replace('| ', '| **', 1).replace(' |', '** |') if i <= k <= j and False else row)
        if has_sum and sum_rw is not rw:
            L += ['', 'The summaries come from a separate annotation pass in format v1.2 (summary first, then shares). The shares and the quotes come from the main pass. The two passes can differ.']
        L += ['', f'Rows from {turns[i]["id"].replace("record-", "r")} to {turns[j]["id"].replace("record-", "r")} are the stretch that the marks `^` show in the time bar.']
    # ---- what this means (rules)
    L += ['', '## What this means (suggested rows; a human must check them)', '', '| Finding | Evidence | Action |', '|---|---|---|']
    if na / total >= a.no_action_row_share:
        L.append(f'| {pct(na / total)} of wall-clock is in turns with no action | Counted. Strong. | Limit the reasoning per turn. When the budget is almost used, send an action. |')
    if rto['seconds'] / total >= 0.02:
        L.append(f'| Read timeouts use {pct(rto["seconds"] / total)} of wall-clock | Counted. Strong. | Make the read timeout shorter. Retry sooner. |')
    fm2 = an['fm_run'].get('FM2_FEEDBACK_NOT_USED')
    if fm2 and fm2['assessed'] and fm2['present'] / fm2['assessed'] >= 0.1 and trusted_fm('FM2_FEEDBACK_NOT_USED'):
        L.append(f'| FM2 (feedback not used) in {fm2["present"]} of {fm2["assessed"]} levels | Labeled. Two passes agree. | Compare prediction and result after each step. Stop at the first mismatch. |')
    if trusted_cat(top) and (sh[top] or 0) >= 0.15:
        L.append(f'| {NAME[top].capitalize()} is the largest waste category ({pct(sh[top])}) | Labeled. Two passes agree. | Choose a change that targets it. |')
    L += ['', '## Limits (generated from the checks)', '']
    lim = [w for w in an.get('warn', [])]
    if not ag:
        lim.append('There is only one annotation pass. The labels have no noise estimate.')
    if ag:
        bad = [c for c in an['fm_run'] if not trusted_fm(c)]
        if bad:
            lim.append(f'Failure-mode codes below the trust threshold: {bad}.')
        badc = [NAME[c] for c in CATS if c in ag['rw_category_kappa'] and not trusted_cat(c)]
        if badc:
            lim.append(f'Waste categories below the trust threshold (do not rank them): {badc}.')
    lim.append('The labels come from a language model. Use the counted results for decisions.')
    L += [f'- {x}' for x in lim]
    Path(a.out).write_text('\n'.join(L) + '\n')
    print(f'wrote {a.out} ({len(L)} lines)')
    # the final report is in English: stop if any line has Chinese, Japanese or Korean text
    cjk = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]')
    bad = [i + 1 for i, line in enumerate(L) if cjk.search(line)]
    if bad:
        print(f'FAIL: the report has non-English text on lines {bad[:10]}. The final report must be in English. '
              'Translate those lines or run the summary pass again with format v1.2 (it asks for English).')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
