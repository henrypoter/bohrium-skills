#!/usr/bin/env python3
# chunker.py INPUT [-o blocks.jsonl] [--plan plan.json] [--max-chars 1200] -- structural blocks + request plan. Stdlib only.
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

RE_HEAD  = re.compile(r'^\s{0,3}#{1,6}\s+\S')
RE_CAP   = re.compile(r'^\s*((fig(ure)?s?|table|scheme|chart|equation|eq)\s*\.?\s*\d+|'
                      r'图\s*\d+|表\s*\d+|式\s*[\(（])', re.I)
RE_TBL   = re.compile(r'^\s*\|.*\|\s*$')
RE_FENCE = re.compile(r'^\s*```')
RE_REFH  = re.compile(r'^\s{0,3}#*\s*(references|bibliography|参考文献)\s*[:：]?\s*$', re.I)
RE_MATH  = re.compile(r'^\s*(\$\$.*\$\$|\\\[.*\\\])\s*$', re.S)

def split_blocks(text):
    paras = re.split(r'\n[ \t]*\n', text.replace('\r\n', '\n'))
    out, in_refs, n = [], False, 0
    for p in paras:
        t = p.strip('\n')
        if not t.strip():
            continue
        lines = [l for l in t.split('\n') if l.strip()]
        first = lines[0]
        if RE_REFH.match(first):
            in_refs = True
        n += 1
        if RE_FENCE.match(first) or RE_MATH.match(t.strip()):
            typ = 'code'
        elif len(lines) == 1 and (RE_HEAD.match(first) or RE_REFH.match(first)):
            typ = 'heading'
        elif all(RE_TBL.match(l) for l in lines):
            typ = 'table'
        elif RE_CAP.match(first):
            typ = 'caption'
        elif in_refs:
            typ = 'reference'
        else:
            typ = 'paragraph'
        out.append({'id': 'B%03d' % n, 'type': typ,
                    'translate': typ != 'code', 'text': t.strip()})
    return out

def make_plan(blks, max_chars):
    chunks, cur, size = [], [], 0
    for b in blks:
        if not b['translate']:
            continue
        l = len(b['text'])
        if l > max_chars:
            if cur:
                chunks.append({'ids': cur, 'oversize': False}); cur, size = [], 0
            chunks.append({'ids': [b['id']], 'oversize': True})
            continue
        if cur and size + l > max_chars:
            chunks.append({'ids': cur, 'oversize': False}); cur, size = [], 0
        cur.append(b['id']); size += l
    if cur:
        chunks.append({'ids': cur, 'oversize': False})
    return chunks

def main():
    ap = argparse.ArgumentParser(description='structural chunker for academic translation')
    ap.add_argument('input')
    ap.add_argument('-o', '--blocks', default='blocks.jsonl')
    ap.add_argument('--plan', default='plan.json')
    ap.add_argument('--max-chars', type=int, default=1200)
    a = ap.parse_args()
    text = read_text(a.input)
    blks = split_blocks(text)
    if not blks:
        print('WARNING: empty input, 0 blocks; mark status="failed" or "partial" '
              'with reason in result.json', file=sys.stderr)
    with open(a.blocks, 'w', encoding='utf-8') as f:
        for b in blks:
            f.write(json.dumps(b, ensure_ascii=False) + '\n')
    chunks = make_plan(blks, a.max_chars)
    with open(a.plan, 'w', encoding='utf-8') as f:
        json.dump({'max_chars': a.max_chars, 'n_blocks': len(blks),
                   'n_chunks': len(chunks), 'chunks': chunks,
                   'warning': None if blks else 'empty input: 0 blocks'}, f,
                  ensure_ascii=False, indent=1)
    over = sum(1 for c in chunks if c['oversize'])
    print('blocks=%d chunks=%d oversize=%d' % (len(blks), len(chunks), over))
    if over:
        print('WARNING: oversize blocks must be re-split by sentence before requesting',
              file=sys.stderr)

if __name__ == '__main__':
    main()
