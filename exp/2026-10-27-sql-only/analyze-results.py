#!/usr/bin/env python3
"""Verify the completed matched runs and generate their descriptive report."""
import argparse
import hashlib
import json
import math
import statistics
import tarfile
from pathlib import Path


ARMS = ('sql-only', 'mavra')
DATABASES = ('rel-stack', 'rel-trial')
FIELDS = ('model', 'llm', 'reasoning_effort', 'thinking', 'base_url', 'require_model',
          'harness_sha256', 'MAX_LLM_CALLS', 'MAX_VALIDATIONS', 'PATIENCE', 'SAMPLE_SIZE', 'LGB_PARAMS')
EXPECTED_MODEL = 'deepseek/deepseek-v4.1-flash-1017'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot(root):
    provenance = read_json(root / 'run-provenance.json')
    files = provenance['files']
    source = {name: digest for name, digest in files.items() if not name.startswith('results/')}
    inputs = {name: digest for name, digest in files.items() if name.startswith('results/relbench-data/')}
    if not source or len(inputs) != 4:
        raise ValueError('unexpected provenance manifest')
    with tarfile.open(root / 'source-as-run.tar.gz', 'r:gz') as archive:
        for name, expected in source.items():
            try:
                member = archive.extractfile(name)
            except KeyError as error:
                raise ValueError(f'source snapshot missing {name}') from error
            if member is None or hashlib.sha256(member.read()).hexdigest() != expected:
                raise ValueError(f'source snapshot hash mismatch for {name}')
    for name, expected in inputs.items():
        relative = Path(name).relative_to('results/relbench-data')
        path = root / 'inputs' / relative
        if not path.resolve().is_relative_to((root / 'inputs').resolve()) or sha256(path) != expected:
            raise ValueError(f'input manifest hash mismatch for {name}')
    for db in DATABASES:
        for arm in ARMS:
            meta = read_json(root / f'{arm}-{db}-r1/run.json')
            if meta['settings']['harness_sha256'] != files['tools/relbench/harness.py']:
                raise ValueError(f'{db} {arm}: harness differs from source snapshot')
    return {'source_snapshot_files': len(source), 'input_manifests': len(inputs)}


def load_database(root, db):
    gate = read_json(root / f'{db}-summary.json')
    if gate['database'] != db or len(gate['sources']) != 32:
        raise ValueError(f'{db}: unexpected gate or source count')
    # Gate paths are relative to the experiment's working directory; retain only their
    # location within the selected root so the audit works after a verified copy.
    for name, expected in gate['sources'].items():
        suffix = Path(name).parts
        if len(suffix) < 4 or suffix[:2] != ('results', 'sql-only-20261027'):
            raise ValueError(f'{db}: unexpected source path {name}')
        path = root.joinpath(*suffix[2:])
        if not path.resolve().is_relative_to(root.resolve()) or sha256(path) != expected:
            raise ValueError(f'{db}: source hash mismatch for {path}')

    data, metas = {}, {}
    for arm in ARMS:
        path = root / f'{arm}-{db}-r1'
        meta = read_json(path / 'run.json')
        if meta.get('arm') != arm or meta.get('run') != 1 or not meta.get('finished') or meta.get('error') or meta.get('smoke'):
            raise ValueError(f'{db} {arm}: incomplete or mismatched run')
        if meta['settings'].get('llm') != 'happy' or meta['settings'].get('base_url') != 'https://happycoding.xyz/v1':
            raise ValueError(f'{db} {arm}: unexpected gateway')
        if meta['settings'].get('require_model') != EXPECTED_MODEL:
            raise ValueError(f'{db} {arm}: unexpected model')
        cfg = meta['settings']['arm_config']
        if cfg.get('middle_mode') != 'relbench-mavra' or cfg.get('parallel_ok'):
            raise ValueError(f'{db} {arm}: unexpected base configuration')
        if arm == 'sql-only' and (not cfg.get('sql_memory') or cfg.get('feature_memory') or cfg.get('extractor')):
            raise ValueError(f'{db}: SQL-only information boundary not recorded')
        if arm == 'mavra' and (not cfg.get('feature_memory') or not cfg.get('extractor') or cfg.get('sql_memory')):
            raise ValueError(f'{db}: MAVRA feature memory not recorded')
        cutoffs = meta['cutoffs']
        if [c['k'] for c in cutoffs] != list(range(1, 6)) or any(len(c['order']) != 3 for c in cutoffs):
            raise ValueError(f'{db} {arm}: incorrect cutoff matrix')
        expected = {(task, c['k']) for c in cutoffs for task in c['order']}
        if len(expected) != 15 or len({t for t, _ in expected}) != 3:
            raise ValueError(f'{db} {arm}: incorrect task matrix')
        rows = {}
        for file in sorted((path / 'sessions').glob('*.json')):
            if file.name.endswith('.partial.json'):
                raise ValueError(f'{db} {arm}: unfinished session {file}')
            s = read_json(file)
            key = (s['task'], s['k'])
            if key in rows or s.get('arm') != arm or s.get('error') or s.get('stop') == 'llm_error':
                raise ValueError(f'{db} {arm}: duplicate or interrupted session {file}')
            if not s.get('llm') or any(x.get('model') != EXPECTED_MODEL for x in s['llm']):
                raise ValueError(f'{db} {arm}: response model mismatch in {file}')
            if (s.get('audit') or {}).get('result') != 'clean' or (s.get('eval') or {}).get('test') is None:
                raise ValueError(f'{db} {arm}: missing clean solution or test score in {file}')
            if (s.get('learning') or {}).get('error'):
                raise ValueError(f'{db} {arm}: learning error in {file}')
            total = s['totals']
            if total['tokens'] != total['input_tokens'] + total['output_tokens'] or total['tokens_with_learning'] != total['tokens'] + total['learn_tokens']:
                raise ValueError(f'{db} {arm}: inconsistent token accounting in {file}')
            rows[key] = s
        if set(rows) != expected:
            raise ValueError(f'{db} {arm}: session matrix mismatch')
        data[arm], metas[arm] = rows, meta

    for field in FIELDS:
        if metas[ARMS[0]]['settings'].get(field) != metas[ARMS[1]]['settings'].get(field):
            raise ValueError(f'{db}: different {field}')
    timelines = [[(c['k'], c['test_timestamp'], c['order']) for c in metas[a]['cutoffs']] for a in ARMS]
    if timelines[0] != timelines[1]:
        raise ValueError(f'{db}: different timeline or task order')
    for a, b in zip(metas['sql-only']['cutoffs'], metas['mavra']['cutoffs']):
        for task in a['order']:
            for metric in ('val', 'test'):
                x, y = a['reference'][task].get(metric), b['reference'][task].get(metric)
                if x is None or y is None or not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError(f'{db}: inconsistent reference score for {task}, k{a["k"]}, {metric}')

    out = {'source_files_verified': len(gate['sources']), 'sessions': {}, 'aggregates': {}, 'quality': {}, 'targets': {}}
    for arm in ARMS:
        out['sessions'][arm] = [dict(task=s['task'], k=s['k'], test=s['eval']['test'], target=s.get('target'),
                                    target_detail=s.get('target_detail'), stop=s['stop'], validations=len(s['validations']),
                                    higher=s['higher_is_better'], tokens=s['totals']['tokens_with_learning'],
                                    learning_tokens=s['totals']['learn_tokens'], llm_calls=s['totals']['llm_calls'],
                                    tool_calls=s['totals']['tool_calls']) for _, s in sorted(data[arm].items())]
    for label, valid_k in [('all', set(range(1, 6))), ('reuse', set(range(2, 6)))] + [(f'k{k}', {k}) for k in range(1, 6)]:
        arms = {}
        for arm in ARMS:
            rs = [s for s in data[arm].values() if s['k'] in valid_k]
            totals = {field: sum(s['totals'][field] for s in rs)
                      for field in ('tokens_with_learning', 'learn_tokens', 'llm_calls', 'tool_calls', 'llm_retry_seconds')}
            arms[arm] = {'n': len(rs), **totals}
            if label in ('all', 'reuse'):
                old = gate['aggregates'][label][arm]
                for expected_name, current_name in (('tokens', 'tokens_with_learning'), ('learning_tokens', 'learn_tokens'),
                                                    ('llm_calls', 'llm_calls'), ('tool_calls', 'tool_calls')):
                    if old[expected_name] != totals[current_name]:
                        raise ValueError(f'{db} {arm} {label}: aggregate mismatch for {expected_name}')
        out['aggregates'][label] = {**arms, 'mavra_relative_to_sql':
                                    arms['mavra']['tokens_with_learning'] / arms['sql-only']['tokens_with_learning'] - 1}
    for task in sorted({t for t, _ in data['sql-only']}):
        s = [data['sql-only'][(task, k)] for k in range(1, 6)]
        m = [data['mavra'][(task, k)] for k in range(1, 6)]
        if any(x['higher_is_better'] != s[0]['higher_is_better'] for x in s + m):
            raise ValueError(f'{db} {task}: inconsistent metric direction')
        higher = s[0]['higher_is_better']
        means = {arm: statistics.mean(data[arm][(task, k)]['eval']['test'] for k in range(1, 6)) for arm in ARMS}
        outside = [k for k in range(1, 6)
                   if not (data['mavra'][(task, k)]['eval']['test'] >= data['sql-only'][(task, k)]['eval']['test'] - .01 if higher
                           else data['mavra'][(task, k)]['eval']['test'] <= data['sql-only'][(task, k)]['eval']['test'] * 1.02)]
        out['quality'][task] = {'metric': 'AUC' if higher else 'MAE', 'mean': means, 'outside_tolerance_cutoffs': outside}
    comparisons = [(data['sql-only'][(t, k)].get('target'), data['mavra'][(t, k)].get('target'))
                   for t in {t for t, _ in data['sql-only']} for k in range(2, 6)]
    both = [(x, y) for x, y in comparisons if x is not None and y is not None]
    out['targets'] = {'reuse_sessions': len(comparisons), 'both_present': len(both),
                      'different': sum(not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12) for x, y in both),
                      'at_least_one_missing': len(comparisons) - len(both)}
    if db == 'rel-trial':
        # Post-hoc diagnostic only: retain the outlier in every primary total above.
        key = ('site-success', 4)
        remaining = {arm: out['aggregates']['reuse'][arm]['tokens_with_learning'] - data[arm][key]['totals']['tokens_with_learning']
                     for arm in ARMS}
        out['posthoc_sensitivity'] = {'excluded_task': key[0], 'excluded_cutoff': key[1],
                                     'excluded_pair': {arm: {'tokens': data[arm][key]['totals']['tokens_with_learning'],
                                                             'target_detail': data[arm][key].get('target_detail'),
                                                             'llm_calls': data[arm][key]['totals']['llm_calls'],
                                                             'validations': len(data[arm][key]['validations'])}
                                                       for arm in ARMS},
                                     'remaining_tokens': remaining,
                                     'mavra_relative_to_sql': remaining['mavra'] / remaining['sql-only'] - 1}
    return out


def write_report(path, data):
    lines = [
        '# SQL-only 与 MAVRA：完成结果与独立核验', '',
        '**采用状态：内部探索，暂不纳入论文。** 本批经第三方网关运行，服务质量和稳定性有待进一步验证。', '',
        '2026-10-28 08:06（北京时间）完成。两组使用同一 happycoding 模型与代码，从空记忆开始；每库各 3 个任务、5 个截点。',
        '以下成本包含所有会话及 MAVRA 的学习 token。墙钟时间受共享服务器与网关重试影响，不用于隔离加速主张。', '',
        '| 数据库 | 截点 | SQL-only token | MAVRA token | MAVRA 相对变化 | SQL-only / MAVRA LLM 调用 |',
        '| --- | --- | ---: | ---: | ---: | ---: |',
    ]
    for db in DATABASES:
        for scope, label in [('all', '1–5'), ('reuse', '2–5')]:
            a = data[db]['aggregates'][scope]
            s, m = a['sql-only'], a['mavra']
            lines.append(f'| {db} | {label} | {s["tokens_with_learning"]:,} | {m["tokens_with_learning"]:,} | '
                         f'{a["mavra_relative_to_sql"]:+.1%} | {s["llm_calls"]} / {m["llm_calls"]} |')
    lines += ['', '每个截点的 token：', '',
              '| 数据库 | 截点 | SQL-only | MAVRA |', '| --- | ---: | ---: | ---: |']
    for db in DATABASES:
        for k in range(1, 6):
            a = data[db]['aggregates'][f'k{k}']
            lines.append(f'| {db} | {k} | {a["sql-only"]["tokens_with_learning"]:,} | {a["mavra"]["tokens_with_learning"]:,} |')
    lines += ['', '## 预测质量', '',
              '分数为五个截点的平均；AUC 越高越好，MAE 越低越好。末列逐截点使用 AUC 不低于 SQL-only 减 0.01、'
              '或 MAE 不高于 SQL-only 的 102% 作为描述性容差。', '',
              '| 数据库 | 任务 | 指标 | SQL-only | MAVRA | MAVRA 超出容差的截点 |',
              '| --- | --- | --- | ---: | ---: | --- |']
    for db in DATABASES:
        for task, quality in data[db]['quality'].items():
            outside = ', '.join(str(k) for k in quality['outside_tolerance_cutoffs']) or '无'
            lines.append(f'| {db} | {task} | {quality["metric"]} | {quality["mean"]["sql-only"]:.5f} | '
                         f'{quality["mean"]["mavra"]:.5f} | {outside} |')
    sensitivity = data['rel-trial']['posthoc_sensitivity']
    s, m = sensitivity['excluded_pair']['sql-only'], sensitivity['excluded_pair']['mavra']
    remaining = sensitivity['remaining_tokens']
    lines += ['', '## 事后敏感性分析', '',
              f'rel-trial 的 site-success 截点 4：SQL-only 使用 {s["tokens"]:,} token（{s["llm_calls"]} 次 LLM 调用、'
              f'{s["validations"]} 次验证）；上一期 SQL 两次重拟合均因 600 秒 SQL 超时，故该会话无目标。'
              f'对应 MAVRA 使用 {m["tokens"]:,} token（{m["llm_calls"]} 次 LLM 调用、{m["validations"]} 次验证），且有目标。',
              f'事后仅为衡量这一对会话的影响，若从各自 12 个复用会话中暂时排除此对，SQL-only 为 '
              f'{remaining["sql-only"]:,} token，MAVRA 为 {remaining["mavra"]:,} token，MAVRA 相对'
              f'{sensitivity["mavra_relative_to_sql"]:+.1%}；这不是替代主结果的预设分析。', '',
              '## 核验与解释', '',
              f'核验 64 个已归档哈希（60 个会话和 4 个 run.json），以及 {data["_verification"]["source_snapshot_files"]} 个源码归档文件'
              f'和 {data["_verification"]["input_manifests"]} 个输入清单／时间线；所有会话的模型标识、成本账目、'
              '干净审计和测试分数均通过检查，未发现学习错误。两组各自在上一期方案上设定目标，规则一致但目标值不一定一致。', '']
    for db in DATABASES:
        t = data[db]['targets']
        lines.append(f'- {db}：12 个复用会话中，{t["both_present"]} 个两组目标均存在，其中 {t["different"]} 个目标值不同；'
                     f'{t["at_least_one_missing"]} 个至少一组目标缺失。')
    lines += ['', '每库每组只有一条随时间推进的序列；数据展示描述性成本与质量差异，'
              '不能视为独立重复、统计显著性或统计非劣。该对照比较完整 MAVRA 与只保存任务 SQL 的方案，'
              '未单独隔离结构化定义、跨任务共享和维护各自的作用。与论文原有 DeepSeek 官方 API 主实验分开报告。', '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_tex(path, data):
    stack, trial = data['rel-stack'], data['rel-trial']
    q = lambda d, task, arm: d['quality'][task]['mean'][arm]
    values = {
        'SqlStackMore': f'{stack["aggregates"]["reuse"]["mavra_relative_to_sql"] * 100:.1f}',
        'SqlTrialSaved': f'{-trial["aggregates"]["reuse"]["mavra_relative_to_sql"] * 100:.1f}',
        'SqlStackAllMore': f'{stack["aggregates"]["all"]["mavra_relative_to_sql"] * 100:.1f}',
        'SqlTrialAllSaved': f'{-trial["aggregates"]["all"]["mavra_relative_to_sql"] * 100:.1f}',
        'SqlStackOnly': f'{stack["aggregates"]["reuse"]["sql-only"]["tokens_with_learning"] / 1e6:.3f}',
        'SqlStackMavra': f'{stack["aggregates"]["reuse"]["mavra"]["tokens_with_learning"] / 1e6:.3f}',
        'SqlTrialOnly': f'{trial["aggregates"]["reuse"]["sql-only"]["tokens_with_learning"] / 1e6:.3f}',
        'SqlTrialMavra': f'{trial["aggregates"]["reuse"]["mavra"]["tokens_with_learning"] / 1e6:.3f}',
        'SqlTrialOutlierOnly': f'{trial["posthoc_sensitivity"]["excluded_pair"]["sql-only"]["tokens"] / 1e6:.3f}',
        'SqlTrialOutlierMavra': f'{trial["posthoc_sensitivity"]["excluded_pair"]["mavra"]["tokens"] / 1e6:.3f}',
        'SqlTrialExclMore': f'{trial["posthoc_sensitivity"]["mavra_relative_to_sql"] * 100:.1f}',
    }
    for prefix, database, task in [('SqlPostVotes', stack, 'post-votes'), ('SqlUserBadge', stack, 'user-badge'),
                                   ('SqlUserEngagement', stack, 'user-engagement'), ('SqlSiteSuccess', trial, 'site-success'),
                                   ('SqlStudyAdverse', trial, 'study-adverse'), ('SqlStudyOutcome', trial, 'study-outcome')]:
        for suffix, arm in [('Only', 'sql-only'), ('Mavra', 'mavra')]:
            values[prefix + suffix] = f'{q(database, task, arm):.4f}'
    lines = ['% Generated by exp/2026-10-27-sql-only/analyze-results.py; do not edit.']
    lines += [f'\\newcommand{{\\{name}}}{{{value}}}' for name, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path('results/sql-only-20261027'))
    ap.add_argument('--out', type=Path, default=Path('exp/2026-10-27-sql-only'))
    ap.add_argument('--tex-out', type=Path, help='optional explicit location for TeX macros; disabled by default')
    a = ap.parse_args()
    status = read_json(a.root / 'status.json')
    if status.get('state') != 'completed' or status.get('exit_code') != 0:
        raise ValueError('the full experiment is not complete')
    data = {db: load_database(a.root, db) for db in DATABASES}
    data['_verification'] = verify_snapshot(a.root)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'verified-results.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    write_report(a.out / 'verified-results.md', data)
    if a.tex_out:
        write_tex(a.tex_out, data)
    print(f'Validated 60 sessions, 64 run hashes, {data["_verification"]["source_snapshot_files"]} source files and '
          f'{data["_verification"]["input_manifests"]} input manifests; wrote {a.out / "verified-results.md"}' +
          (f' and {a.tex_out}' if a.tex_out else ''))


if __name__ == '__main__':
    main()
