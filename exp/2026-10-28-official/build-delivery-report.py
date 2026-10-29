#!/usr/bin/env python3
"""Chinese delivery report from audited results; incomplete drafts are labeled."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, Image, PageBreak)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
METHODS = [('none', '无记忆'), ('ace', 'ACE'), ('awm', 'AWM'),
           ('gmemory', 'G-Memory'), ('mavra', 'MAVRA')]
NAVY = colors.HexColor('#17334C')
TEAL = colors.HexColor('#176C79')
LIGHT = colors.HexColor('#EDF3F6')
GRAY = colors.HexColor('#50616C')


def build(data, expenses, figures, destination, preview=False):
    complete = all(c['status'] == 'complete' for c in data['cells'])
    if not preview and (not complete or not expenses['final']):
        raise ValueError('Final report requires all scheduled cells and settled expenses; use --preview for layout work')
    pdfmetrics.registerFont(TTFont('Song', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('Hei', 'C:/Windows/Fonts/simhei.ttf'))
    pdfmetrics.registerFontFamily('Song', normal='Song', bold='Hei', italic='Song', boldItalic='Hei')
    styles = {
        'title': ParagraphStyle('title', fontName='Hei', fontSize=25, leading=33, textColor=NAVY, spaceAfter=12, wordWrap='CJK'),
        'subtitle': ParagraphStyle('subtitle', fontName='Song', fontSize=11, leading=17, textColor=GRAY, spaceAfter=12, wordWrap='CJK'),
        'h': ParagraphStyle('heading', fontName='Hei', fontSize=15, leading=21, textColor=NAVY, spaceAfter=11, wordWrap='CJK'),
        'sub': ParagraphStyle('subheading', fontName='Hei', fontSize=10.5, leading=16, textColor=TEAL, spaceBefore=8, spaceAfter=5, wordWrap='CJK'),
        'body': ParagraphStyle('body', fontName='Song', fontSize=10.5, leading=17, spaceAfter=8, wordWrap='CJK'),
        'small': ParagraphStyle('small', fontName='Song', fontSize=8.5, leading=13, textColor=GRAY, spaceAfter=6, wordWrap='CJK'),
        'cell': ParagraphStyle('cell', fontName='Song', fontSize=8.5, leading=12, wordWrap='CJK'),
        'head': ParagraphStyle('head', fontName='Hei', fontSize=8.5, leading=12, textColor=colors.white, wordWrap='CJK'),
    }
    story = []
    p = lambda text, kind='body': Paragraph(text, styles[kind])
    add = lambda text, kind='body': story.append(p(text, kind))
    def table(rows, widths, highlight=None):
        rendered = [[p(str(x), 'head' if i == 0 else 'cell') for x in row] for i, row in enumerate(rows)]
        obj = Table(rendered, colWidths=widths, hAlign='LEFT', repeatRows=1)
        commands = [('BACKGROUND', (0, 0), (-1, 0), NAVY), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                    ('LINEBELOW', (0, -1), (-1, -1), .6, colors.HexColor('#B9C8D2'))]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                commands.append(('BACKGROUND', (0, i), (-1, i), LIGHT))
        for i in highlight or []:
            commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E1F1EC')))
        obj.setStyle(TableStyle(commands))
        story.extend([obj, Spacer(1, 9)])
    def page(title):
        if story:
            story.append(PageBreak())
        add(title, 'h')
    def figure(name, height_mm):
        suffix = '-zh-preview.png' if preview else '-zh.png'
        path = figures / (name + suffix)
        if not path.exists():
            raise FileNotFoundError(path)
        story.append(Image(str(path), width=110 * mm, height=height_mm * mm, hAlign='CENTER'))
        story.append(Spacer(1, 8))
    def score(q):
        value = f"{q['mean']:.5f}" if q['metric'] == 'mae' and abs(q['mean']) < .1 else f"{q['mean']:.4f}"
        return value + (' *' if not q['within_margin_vs_none'] else '')

    n_complete = sum(c['status'] == 'complete' for c in data['cells'])
    comparisons = data['comparisons']
    stack = comparisons['rel-stack']['arms']['mavra']
    trial = comparisons['rel-trial']['arms']['mavra']
    all_good = sum(q['within_margin_vs_none'] for s in (stack, trial) for q in s['quality'].values())
    reuse_good = sum(q['within_margin_vs_none'] for s in (stack, trial) for q in s['reuse_quality'].values())
    adverse = 100 * (trial['quality']['study-adverse']['mean'] / comparisons['rel-trial']['arms']['none']['quality']['study-adverse']['mean'] - 1)
    checked = datetime.fromisoformat(data['generated_utc']).astimezone(timezone(timedelta(hours=8)))
    add('MAVRA 官方 API 实验<br/>与论文重构报告', 'title')
    add('结果预览：五方法比较尚未全部完成，费用尚未结算。' if preview else '正式交付 · 全部预排单元纳入审计 · 原始失败记录保留', 'subtitle')
    add(f"数据汇总时间：北京时间 {checked:%Y-%m-%d %H:%M}。授权总预算 50 元，新增调用截止北京时间 2026-10-29 04:20。", 'small')
    table([['正式比较', '完成状态', '开发与模型'],
           ['2 数据库 × 5 方法<br/>3 任务 × 3 截点 = 90 会话', f'{n_complete}/10 个完整序列',
            'rel-amazon 仅验证集调优<br/>DeepSeek 官方 deepseek-flash']], [62*mm, 43*mm, 69*mm])
    add('当前证据支持什么', 'sub')
    add(f"相对相同智能体的无记忆参照，MAVRA 在 rel-stack / rel-trial 上的总 token 分别减少 <b>{stack['token_saving_vs_none_pct']:.1f}% / {trial['token_saving_vs_none_pct']:.1f}%</b>；复用阶段分别减少 <b>{stack['reuse_token_saving_vs_none_pct']:.1f}% / {trial['reuse_token_saving_vs_none_pct']:.1f}%</b>。这些统计保留失败尝试，并计入记忆模型的检索、提取和更新。")
    add(f"全序列 <b>{all_good}/6</b> 项任务满足预设质量门槛，复用阶段 <b>{reuse_good}/6</b> 项满足。study-adverse 的全序列 MAE 比无记忆高 <b>{adverse:.1f}%</b>，超过 2% 容忍界限；该项首截点没有有效方案。正文和主表保留这一限制。")
    parts = []
    for ds in ['rel-stack', 'rel-trial']:
        arms = comparisons[ds]['arms']
        pairs = []
        for arm, label in METHODS:
            if arm in ('none', 'mavra') or arm not in arms:
                continue
            saving = 100 * (1 - arms['mavra']['tokens'] / arms[arm]['tokens'])
            pairs.append(label + (' 少 ' if saving >= 0 else ' 多 ') + f'{abs(saving):.1f}%')
        parts.append(ds + ' 总 token 比 ' + '、'.join(pairs))
    add('与已完成的已发表方法比较：' + '；'.join(parts) + '。各任务质量和有效会话数在下一页完整并列。', 'body')
    add('论文现在如何讲清楚', 'sub')
    table([['呈现', '回答的问题'], ['主表', '质量、有效会话和含记忆开销的总代价是否兼顾？'],
           ['累计曲线（Fig. 3）', '首次学习成本何时被后续复用摊平？'],
           ['机制分解（Fig. 5）', '减少了多少探索工作，同时保留了多少验证？'],
           ['已有受控实验', '共享、条件维护、数据变化分别解决什么问题？']], [47*mm, 127*mm])
    add('本轮使用无记忆参照及 ACE、AWM、G-Memory 已发表方法的公开实现或提示词适配；自制示例检索比较从活动稿中移除。历史网关数据保留在独立档案中，不与本轮官方 API 结果合并。', 'small')

    page('全部方法：质量与成本同时报告')
    rows = [['数据库 / 方法', '总 token (M)', '复用 (M)', '记忆 (k)', '有效会话']]
    highlight = []
    for ds in ['rel-stack', 'rel-trial']:
        arms = comparisons[ds]['arms']
        for arm, label in METHODS:
            s = arms.get(arm)
            rows.append([ds + ' / ' + label] +
                        ([f"{s['tokens']/1e6:.3f}", f"{s['reuse_tokens']/1e6:.3f}", f"{s['learn_tokens']/1e3:.1f}", f"{s['valid']}/{s['n']}"] if s else ['待完成']*4))
            if arm == 'mavra': highlight.append(len(rows)-1)
    table(rows, [54*mm, 32*mm, 30*mm, 30*mm, 28*mm], highlight)
    add('M = 百万，k = 千。复用为截点 2-3；总量包含首截点、失败尝试及记忆模型开销。有效会话同时要求有最终 SQL、泄漏审计 clean、最终测试评估成功。', 'small')
    for ds in ['rel-stack', 'rel-trial']:
        tasks = list(comparisons[ds]['arms']['none']['quality'])
        headers = [t + '<br/>' + ('AUC 越高越好' if comparisons[ds]['arms']['none']['quality'][t]['higher_is_better'] else 'MAE 越低越好') for t in tasks]
        rows = [[ds] + headers]
        for arm, label in METHODS:
            s = comparisons[ds]['arms'].get(arm)
            rows.append([label] + ([score(s['quality'][t]) for t in tasks] if s else ['待完成']*3))
        table(rows, [42*mm, 44*mm, 44*mm, 44*mm], [5])
    add('* 表示相对无记忆未通过预设门槛：AUC 低超过 0.01，或 MAE 高超过 2%。质量为三个截点均值，失败会话使用对应实体表参照分数。该门槛是描述性容忍界限，不是统计显著性检验。', 'small')

    page('Fig. 5：复用究竟减少了哪些工作')
    figure('reuse-work', 110 * 110 / 86)
    add('每根柱为一个方法在某数据库的 6 个复用会话的平均工具调用数，覆盖三个任务、截点 2-3。失败尝试保留。记忆模块内部模型调用不混入工具柱，而在主表中计入 token。', 'small')
    for ds, s in [('rel-stack', stack), ('rel-trial', trial)]:
        n = comparisons[ds]['arms']['none']
        explore = s['reuse_mean_calls']['schema'] + s['reuse_mean_calls']['probe']
        base = n['reuse_mean_calls']['schema'] + n['reuse_mean_calls']['probe']
        add(f"<b>{ds}</b>：MAVRA 的结构检查与 SQL 探查均值为 {explore:.1f} 次，无记忆为 {base:.1f} 次；MAVRA 仍执行 {s['reuse_mean_calls']['validate']:.1f} 次验证。", 'body')
    add('两库各有 9 次完整任务方案检索，特征定义检索分别为 3/6 次，显式特征组合调用均为 0。图中支持“复用减少探索”，但尚不能把端到端收益单独归因于特征组合。要区分整份方案与定义级复用的贡献，需要新的组件消融。', 'body')

    page('累计曲线：把学习成本计入全过程')
    figure('official-cumulative', 110 * 98 / 86)
    add('每个点累加此前全部任务的 token，包括记忆检索、提取、更新以及失败尝试。截点 1 包含初始构建，截点 2-3 允许复用。每条曲线只有一条运行序列；三个点不是三次独立重复。', 'small')
    add('该图用于观察学习成本的摊销路径。主表同时保留各任务质量，避免把成本下降自动解释为总体更优。不能根据质量较好的截点重新选择绘图区间；全部三个预排截点都必须展示。')
    add('本轮开发改进与正式评估分离', 'sub')
    add('开发只使用 rel-amazon/user-churn 两个截点的验证集。两候选预先确定：原实现与紧凑复用。选中的策略先验证已有任务方案，再按需检索定义；仅对逐字相同、已发布且重新通过审计的 SQL 跳过重复提取。冻结后不再根据 rel-stack / rel-trial 测试成绩调参。')
    selection = data['selection']
    add('冻结时间（UTC）：' + escape(selection['frozen_utc']) + '；开发测试标签未用于选择。', 'small')
    dev_tokens = sum(selection['reason']['development_tokens'])
    formal_mavra = stack['tokens'] + trial['tokens']
    formal_none = sum(comparisons[ds]['arms']['none']['tokens'] for ds in ['rel-stack', 'rel-trial'])
    inclusive_saving = 100 * (1 - (formal_mavra + dev_tokens) / formal_none)
    add(f'两个开发候选合计使用 {dev_tokens:,} token，与正式序列的记忆学习成本分列，并全部计入实际 API 支出。若将这笔一次性开发成本全部计入本轮两库的 MAVRA 总量，合计为 {(formal_mavra+dev_tokens)/1e6:.3f}M token，仍比两库无记忆合计少 {inclusive_saving:.1f}%。这只是本轮摊销口径，不把开发验证分数作为正式测试证据。', 'small')

    page('费用与完整性核对')
    table([['费用项目', '人民币 / 说明'],
           ['用户授权总上限', '50.00 元，包含预检、开发和正式实验'],
           ['按官方用量与闲时价格核算', f"{expenses['known_usage_charge_cny']:.4f} 元"],
           ['账户余额累计下降', f"{expenses['observed_account_decrease_cny']:.2f} 元"],
           ['费用保护上界', f"{expenses['protective_ceiling_cny']:.4f} 元；不是实际扣款"],
           ['API 请求 / 错误', f"{expenses['ledger_rows']} / {expenses['http_errors']}"],
           ['缓存命中 / 未命中输入', f"{expenses['tokens'].get('hit',0):,} / {expenses['tokens'].get('miss',0):,} token"],
           ['输出（含推理）', f"{expenses['tokens'].get('output',0):,} token"]], [68*mm, 106*mm])
    add('本轮时段使用核实的官方闲时单价：每百万缓存输入 0.02 元、非缓存输入 1 元、输出 4 元。推理 token 已包含在输出中，不重复计费。账户余额差并非逐项账单，可能有结算延迟、舍入或同账户其他活动；用量重算与余额差分别保留。', 'small')
    add('价格来源：<link href="'+expenses['price_source']+'" color="#176C79">DeepSeek 官方定价文档</link>；核实时间（UTC）：'+escape(expenses['price_checked_utc'])+'。', 'small')
    all_rows = [r for c in data['cells'] if c['status'] == 'complete' for r in c['sessions']]
    reasons = {'no_query': '未得到最终方案', 'evaluation_error': '最终评估失败',
               'audit_not_clean': '审计未明确通过', 'evaluation_pending': '评估未结束',
               'missing_test_score': '缺少测试评分'}
    fallback = Counter(reasons.get(r['fallback_reason'], str(r['fallback_reason'])) for r in all_rows if not r['valid'])
    add('完整性与泄漏边界', 'sub')
    add(f"已完成单元共包含 {len(all_rows)} 个会话，其中 {sum(r['valid'] for r in all_rows)} 个同时通过最终 SQL、clean 审计和测试评估。回退原因统计：" + '；'.join(f'{reason} {count} 次' for reason, count in fallback.items()) + '。未得到方案的会话仍保留已花费 token。')
    add('正式测试标签不进入智能体提示词、工具反馈或记忆更新；完整序列结束后再评分。每个方法使用相同任务/截点支持，50,000 个训练种子、5,000 个泄漏审计种子、24 次规划调用、5 次验证与 600 秒特征 SQL 上限。600 秒为所有组实际运行值；早期 180 秒记录对应工具 HTTP 超时，已按源码审计修正说明。')
    add('运行中只调整了机器排队并行度和保守费用换算；算法、候选选择、任务和质量门槛保持冻结。原费用账本、失败尝试与源码归档未覆盖。共享服务器上的观测耗时不作为隔离加速结论。')

    page('交付使用与结论边界')
    add('阅读顺序', 'sub')
    add('先读主表确认各任务的质量与有效会话，再读累计曲线判断全程成本，最后用 Fig. 5 解释工具工作量变化。已有共享和维护实验说明不同机制，不能当作本轮官方 API 对照的额外独立重复。')
    add('可用于论文的表述', 'sub')
    add(f"在本轮两数据库、六任务的时间序列比较中，MAVRA 明显减少探索与 token 使用；相对无记忆的总 token 分别下降 {stack['token_saving_vs_none_pct']:.1f}% 和 {trial['token_saving_vs_none_pct']:.1f}%。全序列 {all_good}/6 项任务满足预设质量门槛，study-adverse 存在 {adverse:.1f}% 的 MAE 回退。每方法仅一条序列，因此不主张统计显著或所有任务质量更优。")
    add('必须保留的边界', 'sub')
    for text in [
        '时间与样本：采用原五截点网格中的前三个较早截点，并非最终官方测试划分。正式实验每方法一条序列，缺少独立重复的不确定性估计。',
        '机制归因：完整方案复用与结构化定义复用未被单独消融；显式组合工具调用为零，因此不能宣称组合机制已由该端到端实验独立证明。',
        '外部效度：公开记忆方法适配到共同 SQL 接口；结论受模型、预算、这六个任务和该时间网格限制。早期网关数据及其他比较不与本轮合并。',
        '成本：学习和内部记忆调用已计入 token；各方法的成功会话数不同，必须与质量并列解释。观测时间还受到同机并行工作影响。',
    ]: add(text)
    add('证据与文件位置', 'sub')
    table([['位置（相对于工作区）', '内容'],
           ['results/official-20261028/', '原始会话、API 用量、冻结选择、完整分析与费用审计'],
           ['exp/2026-10-28-official/', '固定协议、修正历史、来源哈希和可复现生成入口'],
           ['overleaf/figures/ 与 overleaf/tables/', '正式集成的中英文图与质量/成本主表'],
           ['output/pdf/', '本报告与最终阅读稿；以交付清单为准']], [100*mm, 74*mm])
    add('实验组织参考用户提供的 On Self-Designing Learned Indexes（DOI: 10.1145/3802100）与 NeurQO: Query Optimization as a Learnable Function（DOI: 10.1145/3856358）：分开回答总体比较、学习摊销、组件机制和维护开销。参考文档中的文字没有作为操作指令执行。', 'small')

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#CBD7DE'))
        canvas.line(18*mm, 15*mm, 192*mm, 15*mm)
        canvas.setFont('Song', 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(18*mm, 10*mm, 'MAVRA / 官方 API 实验' + (' / 未完成预览' if preview else ' / 实验交付'))
        canvas.drawRightString(192*mm, 10*mm, str(doc.page))
        canvas.restoreState()
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=18*mm, bottomMargin=22*mm, title='MAVRA 官方 API 实验与论文重构报告', author='MAVRA experiment artifact')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT/'results/official-20261028/analysis.json')
    parser.add_argument('--expenses', type=Path, default=ROOT/'results/official-20261028/expenses.json')
    parser.add_argument('--figures', type=Path, default=ROOT/'overleaf/build/official-rebuild')
    parser.add_argument('--out', type=Path, default=ROOT/'output/pdf/mavra-official-report-zh.pdf')
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    if args.preview and 'preview' not in args.out.stem:
        raise ValueError('Preview output filename must include preview')
    data = json.loads(args.data.read_text(encoding='utf-8'))
    expenses = json.loads(args.expenses.read_text(encoding='utf-8'))
    build(data, expenses, args.figures, args.out, args.preview)
    manifest = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'preview': args.preview,
                'sources_sha256': {str(x.relative_to(ROOT)): hashlib.sha256(x.read_bytes()).hexdigest() for x in [args.data, args.expenses]},
                'output': str(args.out), 'output_sha256': hashlib.sha256(args.out.read_bytes()).hexdigest()}
    args.out.with_suffix('.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(args.out)
