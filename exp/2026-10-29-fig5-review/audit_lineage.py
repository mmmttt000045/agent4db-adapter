"""Read-only trace audit: distinguish returned, validated and selected memory SQL."""
import collections
import hashlib
import json
import pathlib
import re
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'results/official-20261028'

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def norm(text):
    # Text comparison only, deliberately not a claim of SQL equivalence.
    return re.sub(r'\s+', ' ', text.strip().rstrip(';')).strip()

def read_response(text):
    """Recover only complete top-level fields if the recorded response was capped."""
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        decoder, out, pos = json.JSONDecoder(), {}, 1
        while pos < len(text):
            while pos < len(text) and text[pos] in ' \r\n\t,': pos += 1
            try:
                key, end = decoder.raw_decode(text, pos)
                pos = end
                while pos < len(text) and text[pos].isspace(): pos += 1
                if text[pos] != ':': break
                pos += 1
                while pos < len(text) and text[pos].isspace(): pos += 1
                value, end = decoder.raw_decode(text, pos)
            except (json.JSONDecodeError, IndexError):
                return out, {'incomplete_field': key if 'key' in locals() else None, 'chars':len(text)}
            out[key], pos = value, end
        return out, {'incomplete_field':None, 'chars':len(text)}

def main():
    rows, sources = [], {}
    for dataset in ['rel-stack', 'rel-trial']:
        directory = RESULTS / f'mavra-{dataset}-r1'
        for p in sorted((directory / 'sessions').glob('*.json')):
            if '.partial.' in p.name:
                continue
            sources[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
            s = json.loads(p.read_text(encoding='utf-8'))
            calls, candidates, outputs, decode_errors = {}, [], [], []
            for index, message in enumerate(s['messages']):
                for c in message.get('tool_calls', []):
                    calls[c['id']] = dict(c['function'], tool_i=len(calls))
                if message.get('role') != 'tool':
                    continue
                call = calls[message['tool_call_id']]
                if call['name'] not in ('find_program', 'find_features', 'compose_features'):
                    continue
                out, truncated = read_response(message['content'])
                if truncated:
                    decode_errors.append({'message_index':index, 'tool':call['name'], **truncated,
                                          'recovered_complete_fields':list(out)})
                item = {'message_index': index, 'tool': call['name'], 'keys': list(out),
                        'columns': out.get('columns') or [], 'program': out.get('program'),
                        'has_program_sql': bool(out.get('program_sql')), 'has_compiled_sql': bool(out.get('sql')),
                        'truncated_compiled_sql':bool(truncated and truncated['incomplete_field']=='sql')}
                outputs.append(item)
                for field, kind in [('program_sql', 'raw_program'), ('sql', 'compiled_definitions')]:
                    if isinstance(out.get(field), str) and out[field].strip():
                        candidates.append({'tool': call['name'], 'kind': kind, 'message_index': index,
                                           'tool_i':call['tool_i'], 'sql': out[field], 'sha256': sha(out[field]),
                                           'columns': out.get('columns') or []})
            assert len(calls) == len(s['tools']), (p, len(calls), len(s['tools']))
            validation_matches = []
            for v in s['validations']:
                matching = [c for c in candidates if c['tool_i']<v['tool_i'] and norm(c['sql']) == norm(v.get('sql') or '')]
                validation_matches.append({'tool_i': v['tool_i'], 'val': v.get('val'), 'error': v.get('error'),
                    'leak': v.get('leak'), 'leaking_columns':v.get('leaking_columns'), 'improved': v.get('improved'),
                    'matches': [{k: c[k] for k in ['tool', 'kind', 'message_index', 'sha256']} for c in matching]})
            final = s.get('final_sql') or ''
            matching = [c for c in candidates if final and norm(c['sql']) == norm(final)]
            columns = sorted({v['column'] for c in candidates if c['kind'] == 'compiled_definitions' for v in c['columns']})
            mentioned = [c for c in columns if re.search(r'(?<![\w])'+re.escape(c)+r'(?![\w])', final)]
            row = {'dataset': dataset, 'task': s['task'], 'k': s['k'], 'source': str(p.relative_to(ROOT)),
                   'tools': dict(collections.Counter(t['name'] for t in s['tools'])),
                   'memory_outputs': outputs, 'decode_errors': decode_errors,
                   'validation_matches': validation_matches, 'final_sql_sha256': sha(final) if final else None,
                   'final_match': [{k:c[k] for k in ['tool','kind','message_index','sha256']} for c in matching],
                   'compiled_column_mentions_in_final': mentioned,
                   'compiled_column_mentions_note': 'Name overlap is not provenance: manual equivalent expressions or renamed columns require inspection.',
                   'audit': s.get('audit'), 'final_source': s.get('final_source'),
                   'validation_count': len(s['validations']), 'stop': s.get('stop'), 'learning': s.get('learning'),
                   'test': (s.get('eval') or {}).get('test')}
            rows.append(row)
    summary = {}
    for dataset in ['rel-stack','rel-trial']:
        part = [r for r in rows if r['dataset'] == dataset]
        summary[dataset] = {'sessions':len(part), 'reuse_sessions':sum(r['k']>1 for r in part),
            'external_memory_calls': {name:sum(r['tools'].get(name,0) for r in part) for name in ['find_program','find_features','compose_features']},
            'returned_raw_program_sql':sum(x['has_program_sql'] for r in part for x in r['memory_outputs']),
            'returned_compiled_sql':sum(x['has_compiled_sql'] for r in part for x in r['memory_outputs']),
            'returned_truncated_compiled_sql':sum(x['truncated_compiled_sql'] for r in part for x in r['memory_outputs']),
            'raw_program_validated_sessions':sum(any(any(m['kind']=='raw_program' for m in v['matches']) for v in r['validation_matches']) for r in part),
            'compiled_sql_validated_sessions':sum(any(any(m['kind']=='compiled_definitions' for m in v['matches']) for v in r['validation_matches']) for r in part),
            'compiled_sql_clean_validated_sessions':sum(any(v['leak'] is False and any(m['kind']=='compiled_definitions' for m in v['matches']) for v in r['validation_matches']) for r in part),
            'reuse_compiled_sql_validated_sessions':sum(r['k']>1 and any(any(m['kind']=='compiled_definitions' for m in v['matches']) for v in r['validation_matches']) for r in part),
            'raw_program_exact_final_sessions':sum(any(m['kind']=='raw_program' for m in r['final_match']) for r in part),
            'compiled_sql_exact_final_sessions':sum(any(m['kind']=='compiled_definitions' for m in r['final_match']) for r in part),
            'decode_errors':sum(len(r['decode_errors']) for r in part)}
    manifest = json.loads((ROOT/'exp/2026-10-28-official/source-manifest.json').read_text())
    code = {}
    for rel in ['src/middle/features.rs','src/metric.rs']:
        current = hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
        code[rel] = {'current_sha256':current, 'started_sha256':manifest[rel], 'matches_started':current == manifest[rel]}
    result = {'audited_utc':datetime.now(timezone.utc).isoformat(), 'scope':'All 18 completed MAVRA sessions; read-only, no model calls, no changed scores.',
              'matching':'Exact SQL after whitespace and trailing-semicolon normalization; no inferred semantic equivalence.',
              'summary':summary, 'source_code':code, 'sources_sha256':sources, 'sessions':rows}
    output = pathlib.Path(__file__).with_name('lineage-audit.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'summary':summary,'source_code':code},ensure_ascii=False,indent=2))
    for r in rows:
        print(json.dumps({'dataset':r['dataset'],'task':r['task'],'k':r['k'],
          'outputs':[(x['tool'],x['has_program_sql'],x['has_compiled_sql'],len(x['columns'])) for x in r['memory_outputs']],
          'validations':[(v['tool_i'],[m['kind'] for m in v['matches']],v['val'],v['leak'],v['error']) for v in r['validation_matches']],
          'final':[m['kind'] for m in r['final_match']], 'final_compiled_mentions':r['compiled_column_mentions_in_final']},ensure_ascii=False))

if __name__ == '__main__':
    main()
