"""One command for stages 0 to 4. It stops at the first failed check, and it does not spend money unless you ask.
Usage:
  python3 pipeline.py --run RUN_DIR --work WORK_DIR --name NAME [--base BASE_DIR --base-name NAME]
        [--label RUN] [--model gpt-5.6-luna-high] [--passes G1,G2] [--budget-usd 8] [--annotate]
        [--games a,b] [--agent PATH] [--level GAME:LEVEL]
Without --annotate: runs stages 0 and 1, builds the packets, prints the cost estimate, and stops.
With --annotate: annotates the base first and then the run (same model, same inputs, same passes), then runs stages 3 and 4.
--backend chooses who annotates (cursor, command, manual). --budget-usd is the cap for the whole command (cursor backend only). If a call stops (cap or usage limit), run the same command again: it resumes.
Layout of WORK_DIR: stage1/{run,base}, packets/{run,base}, analysis, REPORT.md"""
import argparse
import json
import sys
from pathlib import Path

import analyze
import annotate
import build_packets
import metrics
import preflight
import report
from report import pick_example


def step(title):
    print(f'\n===== {title}')


def spent(pk, pass_name):
    sp = Path(pk) / 'annotations' / pass_name / 'status.json'
    return json.loads(sp.read_text()).get('spent_usd', 0) if sp.exists() else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True); ap.add_argument('--work', required=True); ap.add_argument('--name', required=True)
    ap.add_argument('--base'); ap.add_argument('--base-name', default='the baseline')
    ap.add_argument('--label', default='RUN', help='prefix of the unit ids (use another prefix for the base automatically)')
    ap.add_argument('--model', default='gpt-5.6-luna-high', help='model name (cursor backend) or a label for the result (other backends)')
    ap.add_argument('--prices')
    ap.add_argument('--backend', choices=['cursor', 'command', 'manual'], default='cursor',
                    help='who annotates: cursor (the cursor-agent program), command (any program, see --command), manual (the agent that you talk to)')
    ap.add_argument('--command', help='for --backend command: a shell command that reads the prompt on stdin and prints the JSON answer')
    ap.add_argument('--passes', default='G1,G2', help='names of the annotation passes; the first is the main one')
    ap.add_argument('--budget-usd', type=float, default=8.0)
    ap.add_argument('--annotate', action='store_true', help='spend money: run the annotation')
    ap.add_argument('--format', default='v1.1', choices=['v1.1', 'v1.2', 'v1.3'], help='annotation format (v1.2 adds a summary and a reason per turn)')
    ap.add_argument('--no-example-summaries', action='store_true',
                    help='do not make the extra v1.2 pass that writes the turn summaries of the example level')
    ap.add_argument('--games'); ap.add_argument('--agent'); ap.add_argument('--level'); ap.add_argument('--time-limit-s', default='7920')
    ap.add_argument('--parallel', default='3'); ap.add_argument('--min-kappa', default='0.5')
    a = ap.parse_args(argv)
    work = Path(a.work); passes = [p for p in a.passes.split(',') if p]
    sets = [('run', a.run, a.label)] + ([('base', a.base, 'BASE' if a.label != 'BASE' else 'BASE2')] if a.base else [])

    for tag, d, _ in sets:
        step(f'stage 0 and 1: {tag}')
        if preflight.main(['--run', d, '--out', str(work / 'stage1' / tag)]) != 0:
            print(f'Stage 0 failed for the {tag}. Nothing else ran.'); return 1
    metrics.main(['--run', a.run, '--out', str(work / 'stage1' / 'run'), '--time-limit-s', a.time_limit_s] +
                 (['--base', a.base] if a.base else []))

    for tag, d, label in sets:
        step(f'stage 2a: packets for the {tag}')
        out = work / 'packets' / tag
        if (out / 'units.json').exists():
            print(f'{out} exists. Using it.')
        elif build_packets.main(['--run', d, '--out', str(out), '--label', label, '--format', a.format] + (['--games', a.games] if a.games else [])) != 0:
            print('Packet audit failed.'); return 1

    common = ['--model', a.model, '--parallel', a.parallel, '--backend', a.backend] + (['--command', a.command] if a.command else []) + (['--prices', a.prices] if a.prices else []) + (['--agent', a.agent] if a.agent else [])
    if not a.annotate:
        step('stage 2b: cost estimate (nothing is spent)')
        tot_est = tot_units = 0
        for tag, _, _ in sets:
            for p in passes:
                annotate.main(['--packets', str(work / 'packets' / tag), '--pass-name', p, '--budget-usd', str(a.budget_usd), '--dry-run'] + common)
                tot_est += annotate.LAST.get('est', 0); tot_units += annotate.LAST.get('units', 0)
        print(f'\nTotal estimate: ${tot_est:.2f} for {tot_units} calls (units already done are not counted). Cap: ${a.budget_usd}.')
        print('Stopped before the annotation. Add --annotate to spend money. The cap is --budget-usd, for the whole command.')
        return 0

    remaining = a.budget_usd
    pending = []
    step('stage 2b: annotation (the base first, then the run; same backend, model, inputs and passes)')
    for tag, _, _ in reversed(sets):
        pk = work / 'packets' / tag
        for p in passes:
            before = spent(pk, p)
            rc = annotate.main(['--packets', str(pk), '--pass-name', p, '--budget-usd', str(max(remaining, 0.0001))] + common)
            remaining -= max(spent(pk, p) - before, 0)
            if rc == 4:      # manual backend: the prompts are written, the answers are not there yet
                pending.append(f'{pk}/annotations/{p}'); continue
            if rc != 0:
                print(f'\nStopped in {tag} / {p}. Check {pk}/annotations/{p}/status.json. Run the same command again to resume.'); return 1
    sum_args = []
    if not a.no_example_summaries and a.format != 'v1.2':
        ex = pick_example(work / 'packets' / 'run', a.level)
        if ex:
            uid, u, _, _ = ex
            step(f'summaries for the example level {u["game_id"]}:{u["level"]} (format v1.2, one unit)')
            epk = work / 'packets' / 'example'
            if not (epk / 'units.json').exists():
                build_packets.main(['--run', a.run, '--out', str(epk), '--label', a.label, '--format', 'v1.2', '--games', u['game_id']])
            before = spent(epk, 'S1')
            rc = annotate.main(['--packets', str(epk), '--pass-name', 'S1', '--budget-usd', str(max(remaining, 0.0001)), '--uids', uid] + common)
            remaining -= max(spent(epk, 'S1') - before, 0)
            if rc == 4:
                pending.append(f'{epk}/annotations/S1')
            elif rc != 0:
                print('The summary pass stopped. The report will have no summaries. Run the same command again to resume.')
            else:
                sum_args = ['--summary-ann-dir', str(epk / 'annotations' / 'S1')]
    if pending:
        print('\nThe prompts are written. They wait for the agent that you talk to. For each folder below, answer every file in requests/ '
              'and write the JSON answer to answers/<same name>.json (see the skill file, section "Annotate with the current agent"). '
              'Then run the same command again.')
        for d in pending:
            print('  ', d)
        return 4
    step('stage 3: statistics')
    an = work / 'analysis'
    args = ['--run', a.run, '--run-packets', str(work / 'packets' / 'run'), '--pass', passes[0], '--out', str(an), '--min-kappa', a.min_kappa]
    if len(passes) > 1:
        args += ['--pass2', passes[1]]
    if a.base:
        args += ['--base', a.base, '--base-packets', str(work / 'packets' / 'base'), '--base-pass', passes[0]]
        if len(passes) > 1:
            args += ['--base-pass2', passes[1]]
    rc = analyze.main(args)
    if rc != 0:
        print('A guard failed in stage 3. See the analysis report.'); return 1
    step('stage 4: report')
    rc = report.main(['--stage1', str(work / 'stage1' / 'run'), '--analysis', str(an), '--run-packets', str(work / 'packets' / 'run'),
                 '--pass', passes[0], '--preflight', str(work / 'stage1' / 'run'), '--run-name', a.name, '--base-name', a.base_name,
                 '--out', str(work / 'REPORT.md')] + (['--level', a.level] if a.level else []) + sum_args)
    if rc != 0:
        print(f'\nThe report was written to {work / "REPORT.md"}, but it has a problem (see above). Fix it before you use it.'); return 1
    print(f'\nDone. Read {work / "REPORT.md"} and edit it before you post it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
