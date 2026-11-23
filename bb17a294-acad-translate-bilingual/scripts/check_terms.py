#!/usr/bin/env python3
# check_terms.py -- glossary lifecycle (parse/check/update). Stdlib only.
# parse GLOSSARY -o g.json | check --src S --tgt T --glossary g.json [-o r.json]
# update GLOSSARY DECISIONS.tsv -o OUT.tsv (decisions: src\t+v allow / -v forbid / =tgt retarget)
import argparse, csv, io, json, re, sys

SKIP_HEAD = ('source', 'src', 'term', '原文', '源术语')

def read_text(path):
    try:
        raw = open(path, 'rb').read()
    except OSError as e:
        sys.stderr.write('ERROR: cannot read %s: %s\n' % (path, e)); sys.exit(2)
    for enc in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    sys.stderr.write('ERROR: cannot decode %s as utf-8/gb18030\n' % path); sys.exit(2)

def load_glossary(path):
    raw = read_text(path)
    if re.search(r'^\s*\|', raw, re.M):
        rows = [[c.strip() for c in l.strip('|').split('|')] for l in raw.splitlines()
                if l.strip().startswith('|') and not re.match(r'^\|[\s:\-|]+\|$', l.strip())]
    else:
        dialect = 'excel-tab' if '\t' in raw else 'excel'
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(raw), dialect=dialect)]
    out = []
    for r in rows:
        if len(r) < 2 or not r[0] or r[0].strip('#').lower() in SKIP_HEAD:
            continue
        extra = [x for x in r[2:] if x]
        out.append({'src': r[0], 'tgt': r[1],
                    'forbidden': [x for x in extra if not x.startswith('+')],
                    'allowed': [x.lstrip('+') for x in extra if x.startswith('+')]})
    return out

def count(text, term):
    if re.search(r'[一-鿿]', term):
        return text.count(term)
    pat = r'(?i)(?<![A-Za-z0-9])' + re.escape(term) + r'(?:es|s)?(?![A-Za-z0-9])'
    return len(re.findall(pat, text))

def lines_of(text, term):
    return [i + 1 for i, ln in enumerate(text.splitlines()) if count(ln, term) > 0]

def check(src_text, tgt_text, gl):
    rep = {'terms_total': len(gl), 'ok': 0, 'issues': []}
    for e in gl:
        ns, nt = count(src_text, e['src']), count(tgt_text, e['tgt'])
        na = sum(count(tgt_text, v) for v in e['allowed'])
        cover = nt + na
        problems = []
        if ns > 0 and cover == 0:
            problems.append('missing_in_translation')
        if 0 < cover < ns:
            problems.append('variant_risk: cover %d/%d' % (cover, ns))
        if ns == 0:
            problems.append('not_in_source')
        for f in e['forbidden']:
            k = count(tgt_text, f)
            if k:
                problems.append('forbidden_variant:%s x%d' % (f, k))
        if problems:
            rep['issues'].append({'term': e['src'], 'expect': e['tgt'], 'src_hits': ns,
                                  'tgt_hits': nt, 'src_lines': lines_of(src_text, e['src']),
                                  'tgt_lines': lines_of(tgt_text, e['tgt']),
                                  'problems': problems})
        else:
            rep['ok'] += 1
    crit = [i for i in rep['issues'] if 'missing_in_translation' in i['problems'] or
            any(p.startswith('forbidden_variant') for p in i['problems'])]
    rep['pass'] = not crit
    rep['severity'] = {'critical': len(crit),
                       'major': sum(1 for i in rep['issues'] if any(p.startswith('variant_risk') for p in i['problems'])),
                       'minor': sum(1 for i in rep['issues'] if 'not_in_source' in i['problems'])}
    rep['note'] = 'advisory: exit 0; read flags.'
    return rep

def apply_decisions(rows, decs):
    for d in decs:
        if len(d) < 2 or not d[0].strip() or not d[1].strip():
            continue
        src, val = d[0].strip(), d[1].strip()
        r = next((x for x in rows if x['src'] == src), None)
        if r is None:
            r = {'src': src, 'tgt': '', 'forbidden': [], 'allowed': []}
            rows.append(r)
        if val[0] == '+' and val[1:] and val[1:] not in r['allowed']:
            r['allowed'].append(val[1:])
        elif val[0] == '-' and val[1:] and val[1:] not in r['forbidden']:
            r['forbidden'].append(val[1:])
        elif val[0] == '=' and val[1:]:
            r['tgt'] = val[1:]
    return rows

def main():
    ap = argparse.ArgumentParser(description='glossary parse/check/update')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('parse'); p.add_argument('glossary'); p.add_argument('-o', '--out')
    c = sub.add_parser('check')
    c.add_argument('--src', required=True); c.add_argument('--tgt', required=True)
    c.add_argument('--glossary', required=True); c.add_argument('-o', '--out')
    u = sub.add_parser('update')
    u.add_argument('glossary'); u.add_argument('decisions')
    u.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    if a.cmd == 'parse':
        gl = load_glossary(a.glossary)
        s = json.dumps(gl, ensure_ascii=False, indent=1)
        if a.out:
            open(a.out, 'w', encoding='utf-8').write(s + '\n')
        print('terms=%d' % len(gl))
    elif a.cmd == 'update':
        rows = apply_decisions(load_glossary(a.glossary),
                               [ln.split('\t') for ln in read_text(a.decisions).splitlines() if ln.strip()])
        open(a.out, 'w', encoding='utf-8').write('\n'.join(
            '\t'.join([r['src'], r['tgt']] + ['+' + x for x in r['allowed']] + r['forbidden'])
            for r in rows) + '\n')
        print('updated %d -> %s' % (len(rows), a.out))
    else:
        if a.glossary.endswith('.json'):
            try:
                gl = json.loads(read_text(a.glossary))
            except ValueError as e:
                sys.stderr.write('ERROR: bad glossary json %s: %s\n' % (a.glossary, e)); sys.exit(2)
        else:
            gl = load_glossary(a.glossary)
        rep = check(read_text(a.src), read_text(a.tgt), gl)
        s = json.dumps(rep, ensure_ascii=False, indent=1)
        if a.out:
            open(a.out, 'w', encoding='utf-8').write(s + '\n')
        print(s)

if __name__ == '__main__':
    main()
