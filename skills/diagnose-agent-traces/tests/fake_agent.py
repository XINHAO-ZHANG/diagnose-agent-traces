#!/usr/bin/env python3
"""Test double for `cursor-agent`. Reads the prompt from stdin and prints a stream-json answer.
Env FAKE_MODE: ok (default) | limit (print a usage-limit error) | fail_uid:<text> (fail when the prompt has <text>).
Used to test the runner without a model call and without cost."""
import json, os, sys
msg = sys.stdin.read()
mode = os.environ.get('FAKE_MODE', 'ok')
if mode == 'limit':
    print(json.dumps({'type': 'result', 'is_error': True, 'result': "You've hit your usage limit"})); sys.exit(1)
if mode.startswith('fail_uid:') and mode[9:] in msg:
    print(json.dumps({'type': 'result', 'is_error': True, 'result': 'fake failure'})); sys.exit(1)
packet = json.loads(msg.split('## UNIT PACKET\n\n', 1)[1])
recs = packet['raw_excerpt']['records']
think = next((s['text'] for r in recs for s in r['sections'] if s['kind'] == 'THINKING' and len(s['text']) > 30), '')
v12 = 'two steps' in msg
rw = [dict({'summary': 'The agent looks at the board.', 'reason': 'fake reason'} if v12 else {}, **{'record_id': r['record_id'], 'allocation': {'RW_PRODUCTIVE': 0.6, 'RW_OVERDELIBERATION': 0.4},
       'quote': think[:25] if r is recs[0] else 'this text is not in the trace'}) for r in recs]
fm = {c: {'present': False, 'rationale': 'fake'} for c in ["FM1_REPEATED_EXPLORATION", "FM2_FEEDBACK_NOT_USED",
      "FM3_NO_REVISION_AFTER_CONTRADICTION", "FM4_POST_K_DELAY", "FM5_EXECUTION_DEVIATION", "FM6_TOOL_OR_STATE_ERROR"]}
fm['FM2_FEEDBACK_NOT_USED'] = {'present': True, 'confidence': 'high', 'steps': '1', 'rationale': 'fake',
                               'evidence': [{'record_id': recs[0]['record_id'], 'quote': think[:25]}]}
fm['FM1_REPEATED_EXPLORATION'] = {'present': True, 'rationale': 'fake true without evidence'}
ans = {'milestones': {'K_status': 'unknown', 'S_status': 'unknown'}, 'metrics': {}, 'failure_modes': fm, 'reasoning_waste': rw,
       'other_labels': [], 'notes': 'fake'}
if os.environ.get('FAKE_PLAIN'):      # plain answer on stdout, for the 'command' backend
    print(json.dumps(ans)); sys.exit(0)
print(json.dumps({'type': 'system', 'model': 'fake-model'}))
print(json.dumps({'type': 'result', 'is_error': False, 'result': json.dumps(ans),
                  'usage': {'inputTokens': 1000, 'outputTokens': 500, 'cacheReadTokens': 0, 'cacheWriteTokens': 0}}))
