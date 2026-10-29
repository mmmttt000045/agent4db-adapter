"""Check the exact experiment model, tool round trip, and database templates; never log credentials."""
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, 'tools/relbench')
import harness

expected = 'deepseek/deepseek-v4.1-flash-1017'
env = harness.load_env()
client = harness.Llm(env, 'happy')
if client.model != 'deepseek-v4.1-flash' or client.require != expected:
    raise RuntimeError('unexpected requested/required model')
if client.effort != 'low' or client.thinking != 'enabled':
    raise RuntimeError('unexpected inference settings')

with harness.psycopg.connect(harness.base_url(env['AGENTDB_URL']) + '/postgres', autocommit=True) as con:
    names = {r[0] for r in con.execute("SELECT datname FROM pg_database WHERE datname IN "
                                       "('relbench_stack_t1', 'relbench_trial_t1')")}
if names != {'relbench_stack_t1', 'relbench_trial_t1'}:
    raise RuntimeError('one or more prepared database templates are missing')

messages = [{'role': 'user', 'content': 'Call get_number before replying, then report the number.'}]
tools = [{'type': 'function', 'function': {'name': 'get_number', 'description': 'Get a number.',
         'parameters': {'type': 'object', 'properties': {}, 'required': []}}}]
first = client.chat(messages, tools, max_tokens=512)
message = first.pop('message')
calls = message.get('tool_calls') or []
if len(calls) != 1 or calls[0]['function']['name'] != 'get_number':
    raise RuntimeError('model tool invocation failed')
messages.append(client.history(message))
messages.append({'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': '42'})
second = client.chat(messages, tools, max_tokens=512)
answer = second.pop('message').get('content') or ''
if '42' not in answer:
    raise RuntimeError('model tool round trip failed')
report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
          'provider': 'happy', 'requested_model': client.model, 'required_response_model': expected,
          'thinking': client.thinking, 'reasoning_effort': client.effort,
          'templates': sorted(names), 'tool_round_trip': True, 'responses': [first, second],
          'python': platform.python_version()}
path = Path('results/sql-only-20261027/preflight.json')
path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
