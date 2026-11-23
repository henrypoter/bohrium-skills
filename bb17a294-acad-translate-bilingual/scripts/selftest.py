#!/usr/bin/env python3
# selftest.py -- positive+mutation fixtures for QC scripts (stdlib only).
import json, os, subprocess, sys, tempfile
H = os.path.dirname(os.path.abspath(__file__))
SRC = ("Perovskite solar cells reached 26.1% power conversion efficiency in 2023 [12].\n\n"
       "Stability is limited to 15000 hours at 85 °C and does not yet meet targets, "
       "which may hinder commercialization (Smith et al., 2022).\n\n"
       "Figure 1. Device architecture.\n")
GL = ("perovskite solar cells\t钙钛矿太阳能电池\t钙钛矿太阳电池\n"
      "power conversion efficiency\t光电转换效率\nstability\t稳定性\n")
G = [("B001", "钙钛矿太阳能电池达26.1%光电转换效率(2023)[12]。"),
     ("B002", "其稳定性在85 °C下仍限15000小时，未达标，可能阻碍商业化(Smith et al., 2022)。"),
     ("B003", "图1. 器件结构。")]
B = [("B001", "钙钛矿太阳电池达26%光电转换效率(2023)。"),
     ("B002", "其稳定性在85 °C下限150000小时，已达标，阻碍商业化。")]
ZSRC = "该催化剂在二十三亿次循环后仍保持百分之二十的活性提升（张三 等，2020）【3】。\n"
ZTG = "The catalyst retained a 20% activity enhancement after 2.3 billion cycles (Zhang et al., 2020) [3].\n"
ZTB = "The catalyst retained a 20% activity enhancement after 2.3 billion cycles [3].\n"

def ok(c, m):
    if not c:
        print('FAIL:', m); sys.exit(1)

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--help', '-h'):
        print('usage: selftest.py [SCRIPTS_DIR]'); sys.exit(0)
    d = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else H
    ch, al, tm, it = [os.path.join(d, f) for f in
                      ('chunker.py', 'align.py', 'check_terms.py', 'check_integrity.py')]
    with tempfile.TemporaryDirectory() as w:
        wp = lambda n: os.path.join(w, n)
        def run(a):
            r = subprocess.run([sys.executable] + a, cwd=w, capture_output=True, text=True)
            ok(r.returncode == 0, 'exit0: %s -> %d %s' % (a[0], r.returncode, r.stderr[:200]))
            return r
        load = lambda n: json.load(open(wp(n), encoding='utf-8'))
        open(wp('src.txt'), 'w', encoding='utf-8').write(SRC)
        open(wp('glossary.tsv'), 'w', encoding='utf-8').write(GL)
        run([ch, 'src.txt', '-o', 'blocks.jsonl'])
        run([tm, 'parse', 'glossary.tsv', '-o', 'glossary.json'])
        def emit(xs, n):
            open(wp(n), 'w', encoding='utf-8').write(''.join(
                json.dumps({'id': i, 'text': t}, ensure_ascii=False) + '\n' for i, t in xs))
            return n
        def qc(tb, s):
            run([al, 'blocks.jsonl', tb, '-o', 'bi' + s + '.md', '--report', 'al' + s + '.json',
                 '--emit-translation', 't' + s + '.md', '--direction', 'en2zh'])
            run([tm, 'check', '--src', 'src.txt', '--tgt', 't' + s + '.md',
                 '--glossary', 'glossary.json', '-o', 'tr' + s + '.json'])
            run([it, 'src.txt', 't' + s + '.md', '-o', 'in' + s + '.json'])
            return load('al' + s + '.json'), load('tr' + s + '.json'), load('in' + s + '.json')
        r, tr, ir = qc(emit(G, 'tgt_good.jsonl'), 'g')
        ok(r['pass'] and not r['missing_in_translation'], 'align+')
        ok(tr['pass'] and tr['severity']['critical'] == 0, 'terms+')
        ok(ir['pass'] and not ir['semantic']['flags'] and not ir['numeric']['approx_pairs'], 'int+')
        r, tr, ir = qc(emit(B, 'tgt_bad.jsonl'), 'b')
        ok(not r['pass'] and 'B003' in r['missing_in_translation'], 'align-')
        ok('forbidden_variant' in str([i.get('problems') for i in tr['issues']]), 'terms-')
        miss = str(ir['numeric']['missing_in_tgt']) + str(ir['citations']['missing_in_tgt'])
        ok('26.1' in miss and '12' in miss, 'num/cite-')
        ok(any('scale' in x['hint'] for x in ir['numeric']['approx_pairs']), 'scale-')
        ok(any('negation' in f for f in ir['semantic']['flags']), 'neg-')
        open(wp('decisions.tsv'), 'w', encoding='utf-8').write(
            'stability\t+稳定性能\npower conversion efficiency\t-光电转化效率\n')
        run([tm, 'update', 'glossary.tsv', 'decisions.tsv', '-o', 'glossary.v2.tsv'])
        t = open(wp('glossary.v2.tsv'), encoding='utf-8').read()
        ok('+稳定性能' in t and '光电转化效率' in t, 'update-')
        # v4 fixtures: zh2en author-year + Chinese numerals (positive zero false-kill,
        # mutation must-hit), encoding fallback, empty input, missing glossary.
        open(wp('zsrc.txt'), 'w', encoding='utf-8').write(ZSRC)
        open(wp('ztg.txt'), 'w', encoding='utf-8').write(ZTG)
        open(wp('ztb.txt'), 'w', encoding='utf-8').write(ZTB)
        run([it, 'zsrc.txt', 'ztg.txt', '-o', 'zpos.json'])
        z = load('zpos.json')
        ok(z['pass'] and not z['citations']['missing_in_tgt']
           and z['citations']['reconciled_author_year'], 'zh2en-ay+')
        ok(not z['numeric']['missing_in_tgt'] and not z['numeric']['added_in_tgt'],
           'zh2en-num+')
        run([it, 'zsrc.txt', 'ztb.txt', '-o', 'zmut.json'])
        z = load('zmut.json')
        ok(not z['pass'] and 'ayc:2020' in str(z['citations']['missing_in_tgt']),
           'zh2en-ay-')
        open(wp('gbk.txt'), 'wb').write('催化剂在85 °C下稳定15000小时。\n'.encode('gb18030'))
        r = run([ch, 'gbk.txt', '-o', 'gb.jsonl', '--plan', 'gp.json'])
        ok('blocks=1' in r.stdout, 'gb18030+')
        open(wp('empty.txt'), 'w').close()
        r = run([ch, 'empty.txt', '-o', 'eb.jsonl', '--plan', 'ep.json'])
        ok('WARNING' in r.stderr and load('ep.json')['warning'], 'empty+')
        open(wp('bad.bin'), 'wb').write(b'\xff\xff\xff\xfe')
        r = subprocess.run([sys.executable, ch, 'bad.bin'], cwd=w,
                           capture_output=True, text=True)
        ok(r.returncode == 2 and 'cannot decode' in r.stderr, 'badenc-exit2')
        r = subprocess.run([sys.executable, tm, 'check', '--src', 'zsrc.txt',
                            '--tgt', 'ztg.txt', '--glossary', 'nope.json'],
                           cwd=w, capture_output=True, text=True)
        ok(r.returncode == 2 and 'cannot read' in r.stderr, 'noglossary-exit2')
    print('SELFTEST PASS')

if __name__ == '__main__':
    main()
