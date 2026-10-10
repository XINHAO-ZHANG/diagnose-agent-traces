"""Stage 2b: annotate the packets. One call per unit (or per chunk). Resumable.
Usage: python3 annotate.py --packets PACKETS_DIR --pass-name G1 --model gpt-5.6-luna-high [--backend cursor] --budget-usd 5
Backends (who annotates):
  cursor   (default) the `cursor-agent` program. A cost cap is required. Stops at the cap or at a usage limit.
  command  any program: --command "CMD". The full prompt goes to its stdin. Its stdout must contain the JSON answer.
  manual   the agent that you are talking to. Run once: the prompts are written to annotations/<pass>/requests/<uid>.txt.
           The agent answers each one and writes annotations/<pass>/answers/<uid>.json. Run again: the answers are read.
For command and manual, --model is only a label that is stored in the result. The cost is not tracked.
Output: PACKETS_DIR/annotations/<pass-name>/{units/<uid>.row.json, units/<uid>.rw.json, raw/, status.json}
Use --dry-run first: it prints the unit count and a cost estimate and calls nothing."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import annot_lib as AL

LAST = {}   # the estimate of the last call, for pipeline.py
LOCK = threading.Lock()
STOP = threading.Event()
LIMIT = re.compile(r'usage limit|spend limit', re.I)


class UsageLimit(Exception):
    pass


class Pending(Exception):
    """manual backend: the answer file is not there yet"""


def backend_cursor(args, fn, msg, raw, prices, outd):
    return call(args.agent, args.model, msg, raw, args.timeout, prices, outd)


def backend_command(args, fn, msg, raw, prices, outd):
    t0 = time.time()
    with raw.open('w') as fo, raw.with_suffix('.stderr.log').open('w') as fe:
        p = subprocess.run(args.command, shell=True, input=msg.encode('utf-8'), stdout=fo, stderr=fe, timeout=args.timeout, cwd=str(outd))
    out, err = raw.read_text(), raw.with_suffix('.stderr.log').read_text()[-2000:]
    info = {'rc': p.returncode, 'seconds': round(time.time() - t0, 1), 'usage': None, 'reported_model': 'command', 'tool_events': 0, 'cost_usd': None}
    if p.returncode:
        if LIMIT.search(out + err):
            raise UsageLimit((out + err)[-300:])
        raise RuntimeError(f'command rc={p.returncode} stderr={err[-300:]}', info)
    return AL.parse_json(out), info


PART_CHARS = 40000    # one part must fit in one Read of an agent (about 25,000 tokens)
WRAP = 1200           # the Read tool of some agents cuts very long lines


def wrap(text):
    out = []
    for line in text.split('\n'):
        while len(line) > WRAP:
            out.append(line[:WRAP]); line = line[WRAP:]
        out.append(line)
    return '\n'.join(out)


def render_packet(pk):
    """The unit packet as readable text (real line breaks), in blocks. Same content as the JSON packet."""
    ex = pk['raw_excerpt']
    head = ['UNIT: ' + json.dumps(pk['unit'], ensure_ascii=False), 'FORMAT: ' + ex.get('format', '')]
    if pk.get('chunk'):
        head.append('CHUNK: ' + json.dumps(pk['chunk']))
    blocks = ['\n'.join(head)]
    for r in ex.get('records', []):
        b = [f"##### {r['record_id']} | source line {r['source_line']} | time {r['timestamp']}",
             'turn_stats: ' + json.dumps(r['turn_stats']),
             f"level_steps_executed_in_this_record: {r['level_steps_executed_in_this_record']} | completed_actions_at_record_start: {r['completed_actions_at_record_start']}"]
        for s in r['sections']:
            b.append(f"[section {s['section_index']}: {s['kind']} | source line {s['source_line']}]")
            b.append(s['text'])
        blocks.append(wrap('\n'.join(b)))
    if ex.get('completion_boundary'):
        cb = ex['completion_boundary']
        blocks.append(wrap(f"##### COMPLETION BOUNDARY {cb['record_id']} ({cb['note']})\n" + (cb.get('user_prompt') or '')))
    return blocks


def write_manual_request(outd, stem, msg):
    """Write the instructions as one file and the packet as numbered parts, so that an agent can read all of it."""
    marker = '\n\n## UNIT PACKET\n\n'
    head, packet_json = msg.split(marker, 1)
    blocks = render_packet(json.loads(packet_json))
    pieces = []
    for b in blocks:        # a very long turn is split at line breaks, so that no part is too big for one read
        if len(b) <= PART_CHARS:
            pieces.append(b); continue
        cur_lines, n = [], 0
        for line in b.split('\n'):
            if cur_lines and n + len(line) > PART_CHARS:
                pieces.append('\n'.join(cur_lines)); cur_lines, n = [], 0
            cur_lines.append(line); n += len(line) + 1
        pieces.append('\n'.join(cur_lines))
    parts, cur, size = [], [], 0
    for b in pieces:
        if cur and size + len(b) > PART_CHARS:
            parts.append(cur); cur, size = [], 0
        cur.append(b); size += len(b) + 2
    parts.append(cur)
    req = outd / 'requests'
    req.mkdir(parents=True, exist_ok=True)
    names = [f'{stem}.packet.{i:02d}.txt' for i in range(1, len(parts) + 1)]
    for n, part in zip(names, parts):
        (req / n).write_text('\n\n'.join(part) + '\n', encoding='utf-8')
    (req / f'{stem}.txt').write_text(
        head + marker + 'The unit packet is in the files below, in the same folder. Read ALL of them, in this order. '
        'Long lines were wrapped: a quote must not cross a wrapped line break. Each file starts where the previous one stopped.\n'
        + '\n'.join(f'- {n}' for n in names) + '\n', encoding='utf-8')


def backend_manual(args, fn, msg, raw, prices, outd):
    stem = fn[:-5]
    req, ans = outd / 'requests' / f'{stem}.txt', outd / 'answers' / f'{stem}.json'
    if re.search(r'__c\d+of\d+$', stem):      # a chunk file, not a game id that starts with c (cn04, cd82)
        raise RuntimeError('this unit is split in chunks. The manual backend does not support chunks. Use another backend, or build the packets with a larger --max-input-tokens')
    if not ans.exists():
        if not req.exists():
            write_manual_request(outd, stem, msg)
        raise Pending(stem)
    return AL.parse_json(ans.read_text(encoding='utf-8')), {'rc': 0, 'seconds': 0, 'usage': None, 'reported_model': 'manual', 'tool_events': 0, 'cost_usd': None}


BACKENDS = {'cursor': backend_cursor, 'command': backend_command, 'manual': backend_manual}


def call(agent, model, msg, raw, timeout, prices, cwd):
    t0 = time.time()
    with raw.open('w') as fo, raw.with_suffix('.stderr.log').open('w') as fe:
        # the prompt goes through stdin: a 540 KB prompt passed as an argument returned nothing, with no error
        p = subprocess.run([agent, '-p', '--trust', '--mode', 'ask', '--model', model, '--output-format', 'stream-json'],
                           cwd=str(cwd), input=msg.encode('utf-8'), stdout=fo, stderr=fe, timeout=timeout)
    ev = [json.loads(l) for l in raw.read_text().splitlines() if l.strip().startswith('{')]
    res = next((e for e in reversed(ev) if e.get('type') == 'result'), None)
    init = next((e for e in ev if e.get('type') == 'system'), {})
    tools = [e for e in ev if e.get('type') in ('tool_call', 'tool_use') or 'tool_call' in e.get('subtype', '')]
    info = {'rc': p.returncode, 'seconds': round(time.time() - t0, 1), 'usage': (res or {}).get('usage'),
            'reported_model': init.get('model'), 'tool_events': len(tools)}
    info['cost_usd'] = AL.cost(prices, info['usage'])
    err_text = ((res or {}).get('result') or '') + raw.with_suffix('.stderr.log').read_text()[-2000:]
    if p.returncode or not res or res.get('is_error'):
        if LIMIT.search(err_text):
            raise UsageLimit(err_text[-300:])
        raise RuntimeError(f"agent rc={p.returncode} err={((res or {}).get('result') or '')[:300]}", info)
    return AL.parse_json(res.get('result')), info


def run_one(uid, plan, units, args, pk, outd, prompt_sha, prices, status):
    rowp = outd / 'units' / f'{uid}.row.json'
    if rowp.exists() or STOP.is_set():
        return
    unit = units[uid]
    rec = {'uid': uid, 'model': args.model, 'chunks': len(plan['chunk_files']), 'calls': []}
    t0 = time.time()
    try:
        drafts, summaries, packets = [], [], []
        for i, fn in enumerate(plan['chunk_files'], 1):
            packet = json.loads((pk / 'packets' / fn).read_text())
            if summaries:
                packet['prior_chunks_summary'] = '\n\n'.join(f'[after chunk {j}] {s}' for j, s in enumerate(summaries, 1))
            raw = outd / 'raw' / (fn[:-5] + '.stream.jsonl'); raw.parent.mkdir(parents=True, exist_ok=True)
            d, info = BACKENDS[args.backend](args, fn, AL.message(pk / 'inputs', packet), raw, prices, outd)
            rec['calls'].append(info); drafts.append(d)
            summaries.append(str(d.get('carry_over_summary') or '')[:4000]); packets.append(packet)
        draft = drafts[0] if len(drafts) == 1 else AL.merge(drafts)
        whole = json.loads((pk / 'packets' / plan['chunk_files'][0]).read_text())
        if len(packets) > 1:
            whole['raw_excerpt']['records'] = [x for p in packets for x in p['raw_excerpt']['records']]
        row, rw, fixes, nq, nqv = AL.build_row(unit, whole, draft, args.pass_name,
                                               f"{'cursor-agent' if args.backend == 'cursor' else args.backend} {args.model} ({rec['calls'][0].get('reported_model')})", prompt_sha, args.fmt, args.inputs_sha)
        usage = {}
        for c in rec['calls']:
            for k, v in (c.get('usage') or {}).items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
        costs = [c.get('cost_usd') for c in rec['calls']]
        rec.update(usage=usage, cost_usd=sum(x or 0 for x in costs), seconds=round(time.time() - t0, 1),
                   tool_events=sum(c['tool_events'] for c in rec['calls']))
        (outd / 'units').mkdir(parents=True, exist_ok=True)
        (outd / 'units' / f'{uid}.rw.json').write_text(json.dumps(
            {'uid': uid, 'reasoning_waste': rw, 'runner_fixes': fixes, 'quotes': nq, 'quotes_verified': nqv, 'usage': usage,
             'cost_usd': rec['cost_usd'], 'seconds': rec['seconds'], 'tool_events': rec['tool_events'], 'chunks': rec['chunks'],
             'carry_over_summaries': summaries if rec['chunks'] > 1 else None}, ensure_ascii=False, indent=1))
        rowp.write_text(json.dumps(row, ensure_ascii=False))
        rec.update(status='completed', fixes=len(fixes), quotes=nq, quotes_verified=nqv)
    except Pending:
        rec.update(status='waiting', seconds=0)
    except UsageLimit as e:
        STOP.set(); rec.update(status='usage_limit', error=str(e)[:300], seconds=round(time.time() - t0, 1))
    except Exception as e:
        info = e.args[1] if len(e.args) > 1 and isinstance(e.args[1], dict) else {}
        if info:
            rec['calls'].append(info)
        rec.update(status='failed', error=str(e.args[0] if e.args else e)[:600], seconds=round(time.time() - t0, 1),
                   cost_usd=sum(c.get('cost_usd') or 0 for c in rec['calls']))
    with LOCK:
        if rec['status'] != 'usage_limit':
            status['jobs'][uid] = rec
        status['spent_usd'] = round(sum(j.get('cost_usd') or 0 for j in status['jobs'].values()), 4)
        status['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
        if status['spent_usd'] >= args.budget_usd:
            STOP.set()
        (outd / 'status.json').write_text(json.dumps(status, indent=1))
        print(f"{time.strftime('%H:%M:%S')} {uid} {rec['status']} {rec.get('seconds')}s ${rec.get('cost_usd') or 0:.4f} "
              f"total ${status['spent_usd']:.3f} {rec.get('error', '')[:150]}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--packets', required=True); ap.add_argument('--pass-name', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--backend', choices=sorted(BACKENDS), default='cursor', help='who annotates (see the top of this file)')
    ap.add_argument('--command', help='backend command: a shell command that reads the prompt on stdin and prints the answer')
    ap.add_argument('--budget-usd', type=float, default=None, help='cost cap in dollars (required for the cursor backend)')
    ap.add_argument('--prices', help='in,cache_write,cache_read,out in $ per 1M tokens (needed for a model that is not in the table)')
    ap.add_argument('--agent', default=os.environ.get('CURSOR_AGENT', os.path.expanduser('~/.local/bin/cursor-agent')))
    ap.add_argument('--uids'); ap.add_argument('--uid-file')
    ap.add_argument('--parallel', type=int, default=3); ap.add_argument('--timeout', type=int, default=2400)
    ap.add_argument('--retry-failed', action='store_true'); ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    pk = Path(args.packets)
    if args.backend == 'cursor' and args.budget_usd is None:
        print('FAIL: the cursor backend needs --budget-usd'); return 2
    if args.backend == 'command' and not args.command:
        print('FAIL: --backend command needs --command'); return 2
    if args.budget_usd is None:
        args.budget_usd = float('inf')
    prices = None if args.backend != 'cursor' else tuple(float(x) for x in args.prices.split(',')) if args.prices else AL.PRICES.get(args.model)
    if args.backend == 'cursor' and (prices is None or len(prices) != 4):
        print(f'FAIL: no prices for model {args.model}. Pass --prices in,cache_write,cache_read,out'); return 2
    meta = json.loads((pk / 'units.json').read_text())
    units = {u['uid']: u for u in meta['units']}
    plan = {p['uid']: p for p in json.loads((pk / 'chunk_plan.json').read_text())['units']}
    uids = list(plan)
    if args.uids:
        uids = [u for u in args.uids.split(',') if u in plan]
    elif args.uid_file:
        uids = [l.strip() for l in Path(args.uid_file).read_text().splitlines() if l.strip() in plan]
    outd = pk / 'annotations' / args.pass_name
    sp = outd / 'status.json'
    status = json.loads(sp.read_text()) if sp.exists() else {'jobs': {}}
    todo = [u for u in uids if not (outd / 'units' / f'{u}.row.json').exists()
            and (args.retry_failed or status['jobs'].get(u, {}).get('status') != 'failed')]
    todo.sort(key=lambda u: -plan[u]['est_input_tokens'])
    est_in = sum(plan[u]['est_input_tokens'] for u in todo)
    est = (est_in * prices[0] + len(todo) * AL.AVG_OUTPUT_TOKENS * prices[3]) / 1e6 if prices else 0.0
    LAST.update(est=est, units=len(todo))
    head = f'{len(todo)} units to run, {len(uids) - len(todo)} done or skipped. Model {args.model}. '
    if prices:
        print(head + f'Estimate ${est:.2f} (input at the full input price, output at {AL.AVG_OUTPUT_TOKENS} tokens per unit). Cap ${args.budget_usd}.')
    else:
        print(head + f'Backend {args.backend}: the cost is not tracked. About {est_in:,} input tokens in total.')
    if est > args.budget_usd:
        print('WARNING: the estimate is above the cap. The run will stop at the cap with units left.')
    if args.dry_run:
        return 0
    prompt_sha = meta['prompt_sha256']
    args.fmt = meta.get('format', 'v1.1')
    args.inputs_sha = meta.get('inputs_sha256')
    outd.mkdir(parents=True, exist_ok=True)
    status.update(pass_name=args.pass_name, model=args.model, prompt_sha256=prompt_sha, state='running')
    sp.write_text(json.dumps(status, indent=1))
    with ThreadPoolExecutor(args.parallel) as ex:
        fs = [ex.submit(run_one, u, plan[u], units, args, pk, outd, prompt_sha, prices, status) for u in todo]
        for f in fs:
            f.result()
    spent = status.get('spent_usd', 0)
    waiting = [u for u, j in status['jobs'].items() if j.get('status') == 'waiting']
    if STOP.is_set():
        status['state'] = 'budget_stop' if spent >= args.budget_usd else 'usage_limit_stop'
    elif waiting:
        status['state'] = 'waiting_for_answers'
    else:
        status['state'] = 'finished'
    status['tool_use_flags'] = [u for u, j in status['jobs'].items() if j.get('tool_events')]
    sp.write_text(json.dumps(status, indent=1))
    c = [j['status'] for j in status['jobs'].values()]
    print({'completed': c.count('completed'), 'failed': c.count('failed'), 'spent_usd': spent, 'state': status['state'],
           'units_with_tool_use': len(status['tool_use_flags'])})
    if waiting:
        print(f'{len(waiting)} prompts are waiting. Read {outd}/requests/<uid>.txt, answer with the JSON only, and write '
              f'{outd}/answers/<uid>.json. Then run the same command again.')
        return 4
    return 0 if status['state'] == 'finished' and 'failed' not in c else 1


if __name__ == '__main__':
    sys.exit(main())
