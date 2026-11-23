#!/usr/bin/env python3
# check_integrity.py SRC TGT [-o report.json] -- numbers/units/years/citations + semantic flags.
import argparse, json, re, sys
from collections import Counter

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

UNIT = (r'(?:wt%|at%|vol%|mol%|ppm|ppb|%|°C|K|MPa|GPa|kPa|Pa|meV|eV|keV|MeV|GeV|'
        r'THz|GHz|MHz|kHz|Hz|kW|mW|W|kV|mV|V|mA|μA|A|kJ|J|mmol|μmol|nmol|mol|'
        r'mM|μM|nM|M|μL|mL|L|μm|nm|mm|cm|km|m|mg|μg|kg|g|ms|μs|ns|min|h|s)')
NUM = r'\d[\d,]*(?:\.\d+)?'
SCALE = {'千': 1e3, '万': 1e4, '亿': 1e8, 'million': 1e6, 'billion': 1e9, 'thousand': 1e3}
CN = dict(zip('零〇一二两三四五六七八九', map(int, '001223456789')))
CNU = {'十': 10, '百': 100, '千': 1e3, '万': 1e4, '亿': 1e8}
CNNUM = r'[零〇一二两三四五六七八九十百千万亿点]+'
CNNUMS = r'[零〇一二两三四五六七八九十百千万亿]+'

def val(s):
    return float(s.replace(',', ''))

def cn_val(s):
    if '点' in s:
        a, b = s.split('点', 1)
        return (cn_val(a) if a else 0) + sum(CN.get(c, 0) / (10.0 ** (i + 1)) for i, c in enumerate(b))
    tot = sec = num = 0.0
    for c in s:
        if c in CN:
            num = CN[c]
        elif c in CNU:
            u = CNU[c]
            if u >= 1e4:
                sec = (sec + num) * u; tot += sec; sec = 0; num = 0
            else:
                sec += (num if num else 1) * u; num = 0
    return tot + sec + num

def quantities(text):
    c, t, notes = Counter(), text, []
    def eat(m, key, note=None):
        c[key] += 1
        if note:
            notes.append(note)
        return t.replace(m.group(0), ' ', 1)
    for m in list(re.finditer(r'百分之\s*(' + CNNUM + r')', t)):
        v = cn_val(m.group(1))
        t = eat(m, 'qty:%g%%' % v, m.group(0) + '=%.6g%%' % v)
    for m in list(re.finditer(r'(' + NUM + r')\s*(千|万|亿|million|billion|thousand)(?![A-Za-z])', t, re.I)):
        v = val(m.group(1)) * SCALE[m.group(2).lower()]
        t = eat(m, 'num:%g' % v, '%s=%g' % (m.group(0).strip(), v))
    for m in list(re.finditer(r'(?<![数几余多0-9A-Za-z])(' + CNNUMS + r')', t)):
        s = m.group(1)
        if re.search(r'[十百千]', s) or (len(s) >= 2 and re.search(r'[万亿]', s)):
            t = eat(m, 'num:%g' % cn_val(s), '%s=%g' % (s, cn_val(s)))
    for m in list(re.finditer('(' + NUM + r')\s*(' + UNIT + r')(?![A-Za-z])', t)):
        t = eat(m, 'qty:%g%s' % (val(m.group(1)), m.group(2)))
    for m in list(re.finditer('(' + NUM + r')\s*(?:–|—|~|～|至|到)\s*(' + NUM + r')', t)):
        t = eat(m, 'range:%g-%g' % (val(m.group(1)), val(m.group(2))))
    for m in list(re.finditer(r'(?<![0-9A-Za-z])((?:19|20)\d{2})(?!\d)年?', t)):
        c['year:' + m.group(1)] += 1
        t = t.replace(m.group(0), ' ', 1)
    for m in re.finditer(NUM, t):
        c['num:%g' % val(m.group(0))] += 1
    return c, notes

RE_NUMCITE = re.compile(r'[\[【](\d+(?:\s*[-–,，]\s*\d+)*)[\]】]')
RE_AY = re.compile(r'[\(（]([A-Z][A-Za-z\-]+)((?:\s+et\s+al\.?)?)[,，]?\s*((?:19|20)\d{2})([a-z]?)[\)）]')
RE_AYZ = re.compile(r'[\(（]([一-鿿]{2,4})(\s*等)?[,，]?\s*((?:19|20)\d{2})([a-z]?)[\)）]')

def citations(text):
    c = Counter()
    for m in RE_NUMCITE.finditer(text):
        c['cite:[' + re.sub(r'\s+', '', m.group(1)).replace('，', ',') + ']'] += 1
    for m in RE_AY.finditer(text):
        c['ay:%s:%s%s' % (m.group(1), m.group(3), m.group(4))] += 1
    for m in RE_AYZ.finditer(text):
        c['ayc:%s%s' % (m.group(3), m.group(4))] += 1
    return c

def reconcile_ay(miss, add, notes):
    # （张三 等，2020）↔(Zhang et al., 2020): cross-lingual author-year pairs are
    # matched by year(+suffix); the surname itself is NOT verifiable across
    # languages, so each cancellation is recorded as an advisory note.
    for zk in sorted(k for k in miss if k.startswith('ayc:')):
        tag = zk[4:]
        for ek in sorted(k for k in add if k.startswith('ay:') and k.split(':', 2)[2] == tag):
            n = min(miss[zk], add[ek])
            if n:
                miss[zk] -= n; add[ek] -= n
                notes.append('%s<->%s x%d (author-year zh/en style; year matched, surname unverified)'
                             % (zk, ek, n))
            if not miss[zk]:
                break
    for d in (miss, add):
        for k in [k for k in d if not d[k]]:
            del d[k]

def approx(missing, added):
    def bare(d):
        return [(float(k[4:]), k) for k in d if k.startswith('num:')]
    pairs = []
    for v1, k1 in bare(missing):
        for v2, k2 in bare(added):
            if not (v1 and v2):
                continue
            r = v1 / v2
            if abs(r - 1) < 0.02:
                pairs.append({'src': k1, 'tgt': k2, 'hint': 'rounding/typo', 'ratio': round(r, 6)})
            elif any(abs(r - 10.0 ** k) < 0.02 * (10.0 ** k) for k in range(-6, 7)):
                pairs.append({'src': k1, 'tgt': k2, 'hint': 'scale slip',
                              'ratio': round(r, 6)})
    return pairs

SEM = {'negation': ('没有 无 未 非 不 否'.split(), 'no not never none without non-'.split()),
       'hedge': ('可能 或 约 似乎 估计'.split(), 'may might could likely probably suggest about approximately'.split()),
       'causal': ('导致 因此 由于 因为 造成 引起'.split(), 'cause caused leads led due because therefore'.split())}

def en_count(text, word):
    pat = r'(?<![A-Za-z])' + re.escape(word) + r'(?![A-Za-z])'
    if word == 'no':
        pat = r'(?<![A-Za-z])no(?!\.|\d)'
    return len(re.findall(r'(?i)' + pat, text))

def semantics(src, tgt):
    counts, flags = {}, []
    for label, (zh, en) in SEM.items():
        sz = sum(src.count(w) for w in zh); se = sum(en_count(src, w) for w in en)
        tz = sum(tgt.count(w) for w in zh); te = sum(en_count(tgt, w) for w in en)
        counts[label] = {'src': [sz, se], 'tgt': [tz, te]}
    if sum(counts['negation']['src']) and not sum(counts['negation']['tgt']):
        flags.append('negation possibly dropped')
    if sum(counts['hedge']['src']) and not sum(counts['hedge']['tgt']):
        flags.append('hedges dropped: strength may be overstated')
    if sum(counts['causal']['tgt']) > sum(counts['causal']['src']):
        flags.append('causal language increased')
    return counts, flags

def main():
    ap = argparse.ArgumentParser(description='number/unit/citation integrity + semantic checklist')
    ap.add_argument('src'); ap.add_argument('tgt'); ap.add_argument('-o', '--out')
    a = ap.parse_args()
    s = read_text(a.src)
    t = read_text(a.tgt)
    qs, ns = quantities(RE_NUMCITE.sub(' ', s))
    qt, nt = quantities(RE_NUMCITE.sub(' ', t))
    qmiss, qadd = dict(qs - qt), dict(qt - qs)
    cs, ct = citations(s), citations(t)
    cmiss, cadd = dict(cs - ct), dict(ct - cs)
    ay_notes = []
    reconcile_ay(cmiss, cadd, ay_notes)   # zh src -> en tgt
    reconcile_ay(cadd, cmiss, ay_notes)   # en src -> zh tgt
    counts, flags = semantics(s, t)
    pairs = approx(qmiss, qadd)
    rep = {
        'numeric': {'src_items': sum(qs.values()), 'tgt_items': sum(qt.values()),
                    'missing_in_tgt': qmiss, 'added_in_tgt': qadd,
                    'approx_pairs': pairs, 'normalization_notes': (ns + nt)[:60]},
        'citations': {'src_items': sum(cs.values()), 'tgt_items': sum(ct.values()),
                      'missing_in_tgt': cmiss, 'added_in_tgt': cadd,
                      'reconciled_author_year': ay_notes},
        'semantic': {'counts': counts, 'flags': flags, 'note': 'advisory; not part of pass.'},
        'tolerance_policy': 'exact: year/cite/qty/range; bare: scale equiv + slip flags.',
        'severity': {'critical': len(qmiss) + len(qadd) + len(cmiss) + len(cadd),
                     'major': len(pairs), 'advisory': len(flags)},
        'note': 'advisory: exit 0; read flags.',
    }
    rep['pass'] = not (qmiss or qadd or cmiss or cadd)
    out = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(out + '\n')
    print(out)

if __name__ == '__main__':
    main()
