#!/usr/bin/env python3
# align.py -- bilingual md + 1:1 alignment audit + length-based omission/addition flags. Stdlib only.
import argparse, json, re, sys

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

def load(path):
    out, order = {}, []
    for line in read_text(path).splitlines():
        line = line.strip()
        if line:
            d = json.loads(line)
            if d['id'] not in out:
                order.append(d['id'])
            out[d['id']] = d
    return out, order

def cjk_ratio(s):
    return len(re.findall(r'[\u4e00-\u9fff]', s)) / max(1, len(s))

def main():
    ap = argparse.ArgumentParser(description='bilingual alignment & audit')
    ap.add_argument('src'); ap.add_argument('tgt')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--report'); ap.add_argument('--emit-translation')
    ap.add_argument('--direction', choices=('zh2en', 'en2zh'))
    a = ap.parse_args()
    src, order = load(a.src)
    tgt, _ = load(a.tgt)
    missing = [i for i in order if i not in tgt and src[i].get('translate', True)]
    extra = [i for i in tgt if i not in src]
    notrans = [i for i in order if not src[i].get('translate', True)]
    allsrc = '\n'.join(src[i]['text'] for i in order)
    direction = a.direction or ('zh2en' if cjk_ratio(allsrc) > 0.3 else 'en2zh')
    lo, hi = (0.5, 3.0) if direction == 'zh2en' else (0.3, 1.5)
    parts, tparts, susp = [], [], []
    for i in order:
        s = src[i]
        t = tgt.get(i, {}).get('text', '')
        parts.append('### %s [%s]\n\n**原文**\n\n%s\n\n**译文**\n\n%s\n'
                     % (i, s['type'], s['text'].replace('|', '\\|'),
                        t.replace('|', '\\|')))
        tparts.append(t if s.get('translate', True) and t else s['text'])
        if s.get('translate', True) and s['text'] and t:
            r = len(t) / max(1, len(s['text']))
            if r < lo:
                susp.append({'block': i, 'flag': 'possible_omission', 'ratio': round(r, 3)})
            elif r > hi:
                susp.append({'block': i, 'flag': 'possible_addition', 'ratio': round(r, 3)})
    open(a.out, 'w', encoding='utf-8').write('\n'.join(parts))
    if a.emit_translation:
        open(a.emit_translation, 'w', encoding='utf-8').write('\n\n'.join(tparts) + '\n')
    rep = {'blocks_src': len(order), 'blocks_tgt': len(tgt), 'direction': direction,
           'missing_in_translation': missing, 'extra_in_translation': extra,
           'kept_verbatim': notrans, 'length_suspects': susp,
           'severity': {'critical': len(missing) + len(extra), 'advisory': len(susp)},
           'note': 'advisory: exit 0; read flags.',
           'pass': not missing and not extra}
    s = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.report:
        open(a.report, 'w', encoding='utf-8').write(s + '\n')
    print(s)

if __name__ == '__main__':
    main()
