#!/usr/bin/env python3
"""formula_parse.py — MathML→LaTeX 还原 + 符号清单（纯标准库，不猜语义）。
用法: <xml> [--json F]。"""
import sys, json, re
import xml.etree.ElementTree as ET

GREEK = {c: '\\' + n for c, n in zip(
    'αβγδεζηθικλμνξπρστφχψωΓΔΘΛΞΠΣΦΨΩ',
    ('alpha beta gamma delta varepsilon zeta eta theta iota kappa lambda mu nu '
     'xi pi rho sigma tau varphi chi psi omega Gamma Delta Theta Lambda Xi Pi '
     'Sigma Phi Psi Omega').split())}
OPS = {'∑': '\\sum', '∫': '\\int', '∏': '\\prod', '∂': '\\partial',
       '∇': '\\nabla', '∞': '\\infty', '±': '\\pm', '×': '\\times',
       '·': '\\cdot', '−': '-', '≤': '\\le', '≥': '\\ge', '≠': '\\ne',
       '≈': '\\approx', '∝': '\\propto', '→': '\\to', '∈': '\\in'}

def tag(e):
    return e.tag.split('}', 1)[-1]

def text_of(e):
    t = (e.text or '').strip()
    return GREEK.get(t, OPS.get(t, t))

def grp(s):
    return '{%s}' % s if len(s) > 1 and not s.startswith('{') else s

def latex(e):
    t, k = tag(e), list(e)
    if t in ('mi', 'mn', 'mo', 'mtext'): return text_of(e)
    if t == 'annotation': return ''
    if t == 'mfrac' and len(k) >= 2:
        return '\\frac{%s}{%s}' % (latex(k[0]).strip(), latex(k[1]).strip())
    if t in ('msup', 'msub', 'msubsup', 'munderover', 'munder', 'mover') and k:
        seps = {'msup': '^', 'msub': '_', 'msubsup': '_^',
                'munderover': '_^', 'munder': '_', 'mover': '^'}[t]
        out = grp(latex(k[0]).strip())
        for s, c in zip(seps, k[1:]):
            out += s + grp(latex(c).strip())
        return out
    if t == 'msqrt' and k:
        return '\\sqrt{%s}' % ' '.join(latex(c) for c in k).strip()
    if t == 'mfenced':
        return '\\left%s %s \\right%s' % (e.get('open', '('),
            ' '.join(latex(c) for c in k), e.get('close', ')'))
    if t == 'mtable':
        rows = [' & '.join(latex(c) for c in r) for r in k if tag(r) == 'mtr']
        return '\\begin{matrix} %s \\end{matrix}' % ' \\\\ '.join(rows)
    return ' '.join(x for x in (latex(c) for c in k) if x)

def collect_symbols(e, out=None):
    if out is None: out = []
    t, k = tag(e), list(e)
    if t == 'mi':
        s = (e.text or '').strip()
        if s: out.append({'symbol': s, 'subscript': '', 'superscript': ''})
        return out
    if t in ('msub', 'msup', 'msubsup') and k and tag(k[0]) == 'mi':
        b = (k[0].text or '').strip()
        s_, p_ = '', ''
        for c in k[1:]:
            txt = ''.join(c.itertext()).strip()
            if t in ('msub', 'msubsup') and not s_: s_ = txt
            elif t in ('msup', 'msubsup'): p_ = txt
        if b:
            out.append({'symbol': b, 'subscript': s_, 'superscript': p_})
        return out
    for c in k:
        collect_symbols(c, out)
    return out

def parse_file(path):
    root = ET.parse(path).getroot()
    nodes = [e for e in root.iter() if tag(e) == 'math'] or [root]
    return [{'id': e.get('id') or 'formula-%d' % (i + 1),
             'latex': re.sub(r'\s+', ' ', latex(e)).strip(),
             'symbols': collect_symbols(e)} for i, e in enumerate(nodes)]

def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    formulas = parse_file(argv[1])
    if '--json' in argv:
        jpath = argv[argv.index('--json') + 1]
        with open(jpath, 'w', encoding='utf-8') as f:
            json.dump({'source': argv[1], 'formulas': formulas}, f,
                      ensure_ascii=False, indent=1)
        print('wrote %s (%d formulas)' % (jpath, len(formulas)))
        return 0
    for fo in formulas:
        print('== %s == %s' % (fo['id'], fo['latex']))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
