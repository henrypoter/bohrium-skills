#!/usr/bin/env python3
# compare.py -- deterministic A/B fixture: simulated raw direct translation vs the
# Skill pipeline output, scored by the SAME qc scripts. Stdlib only.
# HONEST SCOPE: both translations are self-made fixtures, not platform harness
# output. This measures QC-detectable fidelity (terms/numbers/citations/blocks),
# not end-to-end LLM quality. See compare_report.md for boundaries.
import json, os, subprocess, sys, tempfile

H = os.path.dirname(os.path.abspath(__file__))
SK = os.path.normpath(os.path.join(H, '..', 'scripts'))
SRC = ("Perovskite solar cells reached a certified power conversion efficiency of 26.1% in 2023 [12].\n\n"
       "The devices retained 92% of their initial performance after 15000 hours at 85 °C, "
       "but long-term stability does not yet meet industrial requirements (Smith et al., 2022).\n\n"
       "The cost is about 0.5 thousand dollars per square meter, i.e. 20% lower than silicon modules [13].\n\n"
       "Figure 1. Device architecture and energy level diagram.\n")
GL = ("perovskite solar cells\t钙钛矿太阳能电池\t钙钛矿太阳电池\n"
      "power conversion efficiency\t光电转换效率\n"
      "stability\t稳定性\n")
# Simulated raw direct translation WITHOUT the workflow: term drift to a forbidden
# variant, 26.1 rounded to 26, [12] and (Smith et al., 2022) dropped, negation
# reversed, scale slip (0.5 thousand -> 0.5), whole caption block omitted.
BASE = [("B001", "钙钛矿太阳电池在2023年达到26%的认证光电转换效率。"),
        ("B002", "器件在85 °C下15000小时后保持初始性能的92%，长期稳定性满足工业要求。"),
        ("B003", "成本约为每平方米0.5美元，比硅组件低20%[13]。")]
# Translation produced WITH the workflow: locked terms, exact numbers/units,
# citations kept, all blocks aligned.
PIPE = [("B001", "钙钛矿太阳能电池在2023年达成26.1%的认证光电转换效率[12]。"),
        ("B002", "器件在85 °C下经过15000小时后仍保持初始性能的92%，但长期稳定性尚未满足工业要求(Smith et al., 2022)。"),
        ("B003", "成本约为每平方米500美元，即比硅组件低20%[13]。"),
        ("B004", "图1. 器件结构与能级图。")]

def fail(m):
    print('FAIL:', m); sys.exit(1)

def main():
    out_json = sys.argv[1] if len(sys.argv) > 1 else os.path.join(H, 'compare_results.json')
    ch, al, tm, it = [os.path.join(SK, f) for f in
                      ('chunker.py', 'align.py', 'check_terms.py', 'check_integrity.py')]
    with tempfile.TemporaryDirectory() as w:
        wp = lambda n: os.path.join(w, n)
        def run(a):
            r = subprocess.run([sys.executable] + a, cwd=w, capture_output=True, text=True)
            if r.returncode != 0:
                fail('%s -> %d %s' % (a[0], r.returncode, r.stderr[:200]))
        open(wp('src.txt'), 'w', encoding='utf-8').write(SRC)
        open(wp('glossary.tsv'), 'w', encoding='utf-8').write(GL)
        run([ch, 'src.txt', '-o', 'blocks.jsonl'])
        run([tm, 'parse', 'glossary.tsv', '-o', 'glossary.json'])
        def qc(pairs, tag):
            open(wp('tgt.jsonl'), 'w', encoding='utf-8').write(''.join(
                json.dumps({'id': i, 'text': t}, ensure_ascii=False) + '\n' for i, t in pairs))
            run([al, 'blocks.jsonl', 'tgt.jsonl', '-o', 'bi.md', '--report', 'al.json',
                 '--emit-translation', 't.md', '--direction', 'en2zh'])
            run([tm, 'check', '--src', 'src.txt', '--tgt', 't.md',
                 '--glossary', 'glossary.json', '-o', 'tr.json'])
            run([it, 'src.txt', 't.md', '-o', 'in.json'])
            return [json.load(open(wp(n), encoding='utf-8'))
                    for n in ('al.json', 'tr.json', 'in.json')]
        def metrics(reps):
            a, t, i = reps
            ni = i['numeric']; ci = i['citations']
            lost = sum(ni['missing_in_tgt'].values()) + sum(ni['added_in_tgt'].values())
            clost = sum(ci['missing_in_tgt'].values()) + sum(ci['added_in_tgt'].values())
            return {
                'term_consistency': round(t['ok'] / max(1, t['terms_total']), 4),
                'numeric_completeness': round(max(0.0, 1 - lost / max(1, ni['src_items'])), 4),
                'citation_completeness': round(max(0.0, 1 - clost / max(1, ci['src_items'])), 4),
                'omission_rate': round(len(a['missing_in_translation']) / max(1, a['blocks_src']), 4),
                'semantic_flags': len(i['semantic']['flags']),
                'terms_pass': t['pass'], 'integrity_pass': i['pass'], 'align_pass': a['pass']}
        res = {'scope': 'self-made fixtures; QC-detectable fidelity only; '
                        'not a platform harness run',
               'baseline_raw_translation': metrics(qc(BASE, 'base')),
               'skill_pipeline': metrics(qc(PIPE, 'pipe'))}
        open(out_json, 'w', encoding='utf-8').write(
            json.dumps(res, ensure_ascii=False, indent=1) + '\n')
        keys = ['term_consistency', 'numeric_completeness', 'citation_completeness',
                'omission_rate', 'semantic_flags']
        print('| metric | baseline_raw | skill_pipeline |')
        print('|---|---|---|')
        for k in keys:
            print('| %s | %s | %s |' % (k, res['baseline_raw_translation'][k],
                                        res['skill_pipeline'][k]))

if __name__ == '__main__':
    main()
