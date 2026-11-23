#!/usr/bin/env python3
r"""verify.py — 量纲三档 / 单位归一数值核验 / LaTeX 等价比对 / 双夹具自测。
用法: dim|num spec.json、equiv '<A>' '<B>'、selftest。不一致记 verdict+warning、退出码 0。"""
import sys, json, ast, math, re
from fractions import Fraction as Fr

DIMS = ['L', 'M', 'T', 'I', 'Th', 'N', 'J']
ZERO = (0,) * 7

def _u(s, f=1.0):
    d = [0] * 7
    for i, x in enumerate(s.split()): d[i] = int(x)
    return tuple(d), f

UNITS = {k: _u(*v) for k, v in {
    'm': ('1',), 'kg': ('0 1',), 'g': ('0 1', 1e-3), 's': ('0 0 1',),
    'A': ('0 0 0 1',), 'K': ('0 0 0 0 1',),
    'N': ('1 1 -2',), 'J': ('2 1 -2',), 'T': ('0 1 -2 -1',),
    'eV': ('2 1 -2', 1.602e-19), '1': ('',)}.items()}
PREFIX = {'k': 1e3, 'c': 1e-2, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9,
          'M': 1e6, 'G': 1e9, 'd': 1e-1}
FUNCS = {'sqrt': math.sqrt, 'exp': math.exp, 'log': math.log10,
         'ln': math.log, 'sin': math.sin, 'cos': math.cos,
         'tan': math.tan, 'pi': math.pi, 'e': math.e}

def unit_dim(ustr):
    u = ustr.strip().replace(' ', '')
    if u in ('', '1'): return ZERO, 1.0
    tot, fac = [0] * 7, 1.0
    for fi, part in enumerate(u.split('/')):
        for tok in part.strip('()').split('*'):
            if not tok: continue
            name, pw = tok.split('^', 1) if '^' in tok else (tok, '1')
            name = name.strip('()'); pw = float(pw)
            if name in UNITS: d, f = UNITS[name]
            elif len(name) > 1 and name[0] in PREFIX and name[1:] in UNITS:
                d, f = UNITS[name[1:]]; f *= PREFIX[name[0]]
            else: raise ValueError('unknown unit: %s' % name)
            s = -1 if fi % 2 else 1
            tot = [t + s * pw * x for t, x in zip(tot, d)]
            fac *= f ** (s * pw)
    return tuple(tot), fac

def show(d):
    p = ['%s^%g' % (DIMS[i], v) for i, v in enumerate(d) if abs(v) > 1e-12]
    return ' '.join(p) or 'dimensionless'

def ev(n, env, dim):
    t = type(n).__name__
    if t == 'Expression': return ev(n.body, env, dim)
    if t == 'Constant': return ZERO if dim else float(n.value)
    if t == 'Name':
        if n.id in FUNCS: return ZERO if dim else FUNCS[n.id]
        if n.id not in env:
            raise ValueError(('no unit declared for' if dim else 'no value for')
                           + ' "%s"' % n.id)
        return unit_dim(env[n.id])[0] if dim else float(env[n.id])
    if t == 'BinOp':
        a, b = ev(n.left, env, dim), ev(n.right, env, dim)
        op = type(n.op)
        if not dim:
            o = op.__name__
            if o == 'Add': return a + b
            if o == 'Sub': return a - b
            if o == 'Mult': return a * b
            if o == 'Div': return a / b
            if o == 'Pow': return a ** b
            raise ValueError('unsupported op')
        if op in (ast.Add, ast.Sub):
            if a != b:
                raise ValueError('add/sub dim mismatch: %s vs %s'
                                 % (show(a), show(b)))
            return a
        if op in (ast.Mult, ast.Div):
            s = 1 if op is ast.Mult else -1
            return tuple(x + s * y for x, y in zip(a, b))
        if op is ast.Pow:
            if b != ZERO: raise ValueError('exponent must be dimensionless')
            return tuple(x * ast.literal_eval(n.right) for x in a)
        raise ValueError('unsupported op')
    if t == 'UnaryOp':
        v = ev(n.operand, env, dim)
        return -v if not dim and type(n.op) is ast.USub else v
    if t == 'Call':
        f = n.func.id if isinstance(n.func, ast.Name) else ''
        if f not in FUNCS or (not dim and f in ('pi', 'e')):
            raise ValueError('unknown function')
        if not dim: return FUNCS[f](*[ev(x, env, dim) for x in n.args])
        d = ev(n.args[0], env, dim)
        if f in ('sin', 'cos', 'tan', 'exp', 'ln', 'log') and d != ZERO:
            raise ValueError('%s() arg must be dimensionless' % f)
        return tuple(x / 2 for x in d) if f == 'sqrt' else ZERO
    raise ValueError('unsupported syntax: %s' % t)

def kinds_of(expr, kinds):
    return sorted({kinds[n.id] for n in ast.walk(ast.parse(expr, mode='eval'))
                   if isinstance(n, ast.Name) and n.id in kinds})

def run_dim(spec):
    units, kinds, out = spec.get('units', {}), spec.get('kinds', {}), []
    for c in spec.get('checks', []):
        r = {'name': c.get('name', c.get('rhs', '?'))}
        try:
            dr = ev(ast.parse(c['rhs'], mode='eval'), units, True)
            r['rhs_dim'] = show(dr)
            if 'lhs' not in c:
                r['verdict'] = r['consistent'] = None
            else:
                dl = ev(ast.parse(c['lhs'], mode='eval'), units, True)
                kl, kr = kinds_of(c['lhs'], kinds), kinds_of(c['rhs'], kinds)
                r['lhs_dim'] = show(dl)
                if dl != dr:
                    r['verdict'] = 'inconsistent'
                    r['dim_diff'] = show(tuple(a - b for a, b in zip(dl, dr)))
                elif kl and kr and kl != kr:
                    r['verdict'] = 'dimensionally-consistent-but-physically-suspect'
                else: r['verdict'] = 'consistent'
                r['consistent'] = r['verdict'] == 'consistent'
        except Exception as ex:
            r['verdict'] = 'inconsistent'; r['consistent'] = False
            r['error'] = str(ex)
        out.append(r)
    return out

def run_num(spec):
    out = []
    for c in spec.get('checks', []):
        r = {'expr': c['expr'],
             'pipeline': ['normalize', 'substitute', 'compare']}
        try:
            vals, normd = {}, {}
            for k, x in c.get('values', {}).items():
                if isinstance(x, dict):
                    vals[k] = float(x['value']) * unit_dim(x.get('unit', '1'))[1]
                    normd[k] = {'from': '%s [%s]' % (x['value'], x['unit']), 'si_value': vals[k]}
                else: vals[k] = float(x)
            if normd: r['normalized'] = normd
            exp = c.get('expected')
            if isinstance(exp, dict):
                exp = float(exp['value']) * unit_dim(exp.get('unit', '1'))[1]
            v = ev(ast.parse(c['expr'], mode='eval'), vals, False)
            r['computed'] = v
            if exp is not None:
                exp = float(exp)
                r['expected'] = exp
                r['abs_err'] = abs(v - exp)
                r['rel_err'] = abs(v - exp) / abs(exp) if exp else (0.0 if v == 0 else float('inf'))
                r['magnitude_ratio'] = (abs(v) / abs(exp)) if exp else None
                r['rtol'] = float(c.get('rtol', 0.01)); r['match'] = r['rel_err'] <= r['rtol']
        except Exception as ex:
            r['error'] = str(ex); r['match'] = False
        out.append(r)
    return out

def lex(s):
    s = s.strip().strip('$')
    s = re.sub(r'\\(?:left|right|bigg?|displaystyle|limits|mathrm|text'
               r'|operatorname|boxed)\b|\\[,;:!]|\\ ', '', s)
    s = s.replace('\\cdot', '*').replace('\\times', '*').replace('\\div', '/')
    s = re.sub(r'\\[dt]?frac\b', r'\\frac', s)
    toks, i = [], 0
    while i < len(s):
        c = s[i]
        if c.isspace(): i += 1; continue
        if c == '\\':
            m = re.match(r'\\([A-Za-z]+|.)', s[i:])
            toks.append(('cmd', m.group(1))); i += m.end(); continue
        if c.isdigit() or c == '.':
            m = re.match(r'\d*\.?\d+', s[i:])
            toks.append(('num', m.group(0))); i += m.end(); continue
        toks.append(('id', c) if c.isalpha() else (c, c)); i += 1
    toks.append(('end', ''))
    return toks

class TP:  # LaTeX(-lite) 解析器
    def __init__(self, s): self.t = lex(s); self.i = 0
    def peek(self): return self.t[self.i]
    def next(self): tok = self.t[self.i]; self.i += 1; return tok
    def parse(self):
        n = self.expr()
        if self.peek()[0] != 'end': raise ValueError('trailing input')
        return n
    def expr(self):
        n = self.term()
        while self.peek()[0] in ('+', '-'):
            op = self.next()[0]
            n = ('add' if op == '+' else 'sub', n, self.term())
        return n
    def term(self):
        n = self.power()
        while True:
            k = self.peek()[0]
            if k == '*': self.next(); n = ('mul', n, self.power())
            elif k == '/': self.next(); n = ('div', n, self.power())
            elif k in ('num', 'id', '(', '{', 'cmd'):
                n = ('mul', n, self.power())
            else: break
        return n
    def power(self):
        n = self.atom()
        if self.peek()[0] == '_':
            self.next()
            if n[0] != 'sym': raise ValueError('bad subscript')
            n = ('sym', n[1] + '_' + flatname(self.group()))
        if self.peek()[0] == '^':
            self.next(); n = ('pow', n, self.group())
        return n
    def group(self):
        if self.peek()[0] == '{':
            self.next(); e = self.expr()
            if self.next()[0] != '}': raise ValueError('missing }')
            return e
        return self.power()
    def atom(self):
        k, v = self.next()
        if k == 'num': return ('num', Fr(v))
        if k == 'id': return ('sym', v)
        if k in ('(', '{'):
            e = self.expr()
            if self.next()[0] != (')' if k == '(' else '}'):
                raise ValueError('unbalanced')
            return e
        if k == '-': return ('neg', self.power())
        if k == 'cmd':
            if v == 'frac': return ('div', self.group(), self.group())
            if v == 'sqrt': return ('pow', self.group(), ('num', Fr(1, 2)))
            if v in ('exp', 'ln', 'log', 'sin', 'cos', 'tan'):
                return ('call', v, self.group())
            return ('sym', v)
        raise ValueError('bad token %s' % (v,))

def flatname(n):
    if n[0] == 'sym': return n[1]
    if n[0] == 'num': return '%g' % float(n[1])
    return ''.join(flatname(c) for c in n[1:] if isinstance(c, tuple))

def mul_c(items):
    flat = []
    for n in items: flat.extend(n[1] if n[0] == 'mul' else [n])
    coeff, rest = Fr(1), {}
    for n in flat:
        if n[0] == 'num': coeff *= n[1]; continue
        b, p = (n[1], n[2][1]) if n[0] == 'pow' and n[2][0] == 'num' else (n, Fr(1))
        rest[b] = rest.get(b, Fr(0)) + p
    out = [b if p == 1 else ('pow', b, ('num', p))
           for b, p in sorted(rest.items(), key=lambda kv: repr(kv[0])) if p]
    if not out: return ('num', coeff)
    if coeff == 0: return ('num', Fr(0))
    if coeff != 1: out.insert(0, ('num', coeff))
    return out[0] if len(out) == 1 else ('mul', tuple(out))

def add_c(items):
    flat = []
    for n in items: flat.extend(n[1] if n[0] == 'add' else [n])
    const, terms = Fr(0), {}
    for n in flat:
        if n[0] == 'num': const += n[1]
        else: terms[n] = terms.get(n, 0) + 1
    out = [('num', const)] if const else []
    for b in sorted(terms, key=repr):
        out.append(b if terms[b] == 1 else mul_c([('num', Fr(terms[b])), b]))
    if not out: return ('num', Fr(0))
    return out[0] if len(out) == 1 else ('add', tuple(out))

def neg_c(n):
    if n[0] == 'add': return add_c([neg_c(x) for x in n[1]])
    return mul_c([('num', Fr(-1)), n])

def pow_c(b, e):
    if e[0] == 'num':
        if e[1] == 0: return ('num', Fr(1))
        if e[1] == 1: return b
        if b[0] == 'num' and e[1].denominator == 1: return ('num', b[1] ** e[1])
    if b == ('sym', 'e'): return ('func', 'exp', e)
    return ('pow', b, e)

def canon(n):
    t = n[0]
    if t in ('num', 'sym'): return n
    if t == 'neg': return mul_c([('num', Fr(-1)), canon(n[1])])
    if t == 'add': return add_c([canon(n[1]), canon(n[2])])
    if t == 'sub': return add_c([canon(n[1]), neg_c(canon(n[2]))])
    if t == 'mul': return mul_c([canon(n[1]), canon(n[2])])
    if t == 'div': return mul_c([canon(n[1]), pow_c(canon(n[2]), ('num', Fr(-1)))])
    if t == 'pow': return pow_c(canon(n[1]), canon(n[2]))
    if t == 'call': return ('func', n[1], canon(n[2]))
    raise ValueError('bad node %r' % (n,))

def tex_form(s):
    depth, cut = 0, None
    for i, ch in enumerate(s):
        if ch in '({': depth += 1
        elif ch in ')}': depth -= 1
        elif ch == '=' and depth == 0: cut = i; break
    if cut is None: return canon(TP(s).parse())
    return add_c([canon(TP(s[:cut]).parse()),
                  neg_c(canon(TP(s[cut + 1:]).parse()))])

def run_equiv(a, b):
    r = {'a': a, 'b': b}
    try:
        ca, cb = tex_form(a), tex_form(b)
        r['equivalent'] = bool(ca == cb or ca == neg_c(cb))
    except Exception as ex:
        r['equivalent'] = False; r['error'] = str(ex)
    return r

def selftest():
    U = {'v_esc': 'm/s', 'G': 'm^3/(kg*s^2)', 'M': 'kg', 'R': 'm'}
    V = {'G': 6.674e-11, 'M': 5.972e24, 'R': 6.371e6}
    dm = lambda u, l, r, k=None: run_dim(
        {'units': u, 'kinds': k or {}, 'checks': [{'lhs': l, 'rhs': r}]})[0]
    nm = lambda v, x=None: run_num({'checks': [dict(
        {'expr': 'sqrt(2*G*M/R)', 'values': v},
        **({'expected': x} if x is not None else {}))]})[0]
    eq = lambda a, b: run_equiv(a, b)['equivalent']
    cases = [
        ('positive', 'dim-ok', dm(U, 'v_esc', 'sqrt(2*G*M/R)')['verdict'], 'consistent'),
        ('positive', 'num-norm',
         nm(dict(V, R={'value': 6371, 'unit': 'km'}),
            {'value': 11.2, 'unit': 'km/s'}).get('match'), True),
        ('positive', 'eq-frac', eq(r'\frac{2 G M}{R}', '2 M G / R'), True),
        ('positive', 'eq-exp', eq(r'e^{-\frac{x^{2}}{2 \sigma^{2}}}',
         r'\exp(-x^2/(2\sigma^2))'), True),
        ('positive', 'eq-swap', eq(r'v_{esc} = \sqrt{\frac{2 G M}{R}}',
         r'\sqrt{2 M G / R} = v_{esc}'), True),
        ('mutant', 'dim-bad',
         dm({'h': 'm', 'g': 'm/s^2'}, 'h', 'sqrt(2*g*h)')['verdict'], 'inconsistent'),
        ('mutant', 'kind-suspect',
         dm({'E': 'J', 'tau': 'N*m'}, 'E', 'tau',
            {'E': 'energy', 'tau': 'torque'})['verdict'],
         'dimensionally-consistent-but-physically-suspect'),
        ('mutant', 'num-bad', nm(V, 5.0).get('match'), False),
        ('mutant', 'undef-sym', 'error' in nm({'G': 1.0}), True),
        ('mutant', 'undef-unit', 'error' in dm({'a': 'm'}, 'a', 'b'), True),
        ('mutant', 'rewrite-ok', eq(r'\frac{2 G M}{R}', r'2*M*G/R'), True)]
    npass = 0
    for tag, name, got, want in cases:
        ok = got == want
        npass += ok
        print('%s [%s] %s' % ('PASS' if ok else 'FAIL', tag, name))
    print('selftest: %d/%d passed' % (npass, len(cases)))
    return 0 if npass == len(cases) else 1

def main(argv):
    if len(argv) < 2: print(__doc__); return 2
    m = argv[1]
    if m == 'selftest': return selftest()
    if m == 'equiv' and len(argv) >= 4:
        r = run_equiv(argv[2], argv[3])
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r['equivalent'] else 1
    if m in ('dim', 'num') and len(argv) >= 3:
        try:
            with open(argv[2], encoding='utf-8') as f: spec = json.load(f)
        except Exception as ex:
            print(json.dumps({'mode': m, 'error': str(ex)}, ensure_ascii=False))
            return 2
        res = run_dim(spec) if m == 'dim' else run_num(spec)
        out = {'mode': m, 'results': res}
        n = sum(1 for r in res if r.get('consistent') is False
                or r.get('match') is False)
        if n: out['warning'] = '%d check(s) NOT passed (verdicts recorded)' % n
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(__doc__); return 2

if __name__ == '__main__':
    sys.exit(main(sys.argv))
