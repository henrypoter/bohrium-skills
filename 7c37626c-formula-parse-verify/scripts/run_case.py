#!/usr/bin/env python3
"""run_case.py — 启动驱动：解析 source-formulas.xml、写诚实 result.json 骨架。
用法: run_case.py [input_dir=/input] [output_dir=/app/output]。"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formula_parse

def symbol_table(formulas):
    st = {}
    for fo in formulas:
        loc = 'artifacts/source-formulas.xml#' + fo['id']
        for s in fo.get('symbols', []):
            k = (s.get('symbol'), s.get('subscript'), s.get('superscript'))
            if k not in st:
                lat = s.get('symbol') or ''
                if s.get('subscript'): lat += '_{%s}' % s['subscript']
                if s.get('superscript'): lat += '^{%s}' % s['superscript']
                st[k] = dict(symbol=s.get('symbol'), subscript=s.get('subscript'),
                             superscript=s.get('superscript'), latex=lat,
                             occurrences=0, sources=[], meaning=None, unit=None,
                             dimension=None, origin='unknown')
            st[k]['occurrences'] += 1
            if loc not in st[k]['sources']: st[k]['sources'].append(loc)
    return list(st.values())

def main(argv):
    ind = argv[1] if len(argv) > 1 else '/input'
    outd = argv[2] if len(argv) > 2 else '/app/output'
    if not os.path.isdir(ind):
        print('input dir not found: %s' % ind); return 2
    workd = os.environ.get('WORK_DIR', '/app/work')
    for d in (outd, workd): os.makedirs(d, exist_ok=True)

    case_id, contract_keys = 'unknown', []
    cj = os.path.join(ind, 'case.json')
    if os.path.isfile(cj):
        try:
            with open(cj, encoding='utf-8') as f:
                case = json.load(f)
            case_id = str(case.get('case_id') or case.get('id') or 'unknown')
            oc = case.get('output_contract')
            if isinstance(oc, dict): contract_keys = list(oc.keys())
            elif isinstance(oc, list): contract_keys = [str(k) for k in oc]
        except Exception as ex:
            print('warn: case.json unreadable: %s' % ex)

    fx = os.path.join(ind, 'artifacts', 'source-formulas.xml')
    formulas, note = [], 'no source-formulas.xml found'
    if os.path.isfile(fx):
        try:
            formulas = formula_parse.parse_file(fx)
            pp = os.path.join(workd, 'parsed_formulas.json')
            with open(pp, 'w', encoding='utf-8') as f:
                json.dump({'source': fx, 'formulas': formulas}, f,
                          ensure_ascii=False, indent=1)
            note = 'parsed %d formula(s) -> %s' % (len(formulas), pp)
        except Exception as ex:
            note = 'parse failed: %s' % str(ex)[:200]

    syms = symbol_table(formulas)
    result = {
        'case_id': case_id, 'status': 'partial', 'summary': '',
        'formulas': [{'id': fo['id'], 'latex': fo['latex'],
                      'source': 'artifacts/source-formulas.xml#' + fo['id']}
                     for fo in formulas],
        'symbol_table': syms, 'derivation_steps': [],
        'verification': {'dimension_checks': [], 'numeric_checks': [],
                         'equivalence_checks': []},
        'sources': ([{'path': 'artifacts/source-formulas.xml', 'note': note}]
                    if os.path.isfile(fx) else []),
        'uncertainty': [], 'limitations': [],
        'change_log': [{'step': 'init',
                        'note': 'skeleton; ' + note + '; %d symbol(s)' % len(syms)}],
    }
    for k in contract_keys:
        result.setdefault(k, None)
    if not formulas:
        result['uncertainty'].append(
            'insufficient_evidence: 材料不含公式表示（无 MathML/LaTeX/可复算'
            '数据），推导与数值复算只能报告缺失，不得反推公式或填 0。')
        result['limitations'].append(
            'formula representation absent in provided materials')
    rp = os.path.join(outd, 'result.json')
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print('case_id: %s' % case_id)
    print('formulas: %s\nskeleton -> %s' % (note, rp))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
