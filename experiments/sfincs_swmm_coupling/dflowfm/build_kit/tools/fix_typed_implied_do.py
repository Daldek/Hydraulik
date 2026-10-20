"""Rewrite F2018 typed implied-do indices '(expr, integer :: i=a, b)' (unsupported by gfortran <= 14)
into classic implied-do '(expr, i=a, b)' and declare 'integer :: i' in the enclosing procedure
when it has no such declaration yet."""
import re, sys

HDR = re.compile(r'^\s*(?:(?:pure|elemental|recursive|impure|module|integer|logical|real(?:\([^)]*\))?|character(?:\([^)]*\))?|type\([^)]*\))\s+)*(subroutine|function)\s+(\w+)', re.I)
END = re.compile(r'^\s*end\s*(subroutine|function)\b', re.I)
TYPED = re.compile(r',\s*integer\s*::\s*(\w+)\s*=', re.I)

for path in sys.argv[1:]:
    lines = open(path).read().split('\n')
    needed = {}  # header line index -> set of names
    for n, line in enumerate(lines):
        for m in TYPED.finditer(line.split('!')[0]):
            var = m.group(1)
            h = n
            while h >= 0 and not HDR.match(lines[h]):
                h -= 1
            e = n
            while e < len(lines) and not END.match(lines[e]):
                e += 1
            body = '\n'.join(l.split('!')[0] for l in lines[h:e])
            declared = re.search(r'^\s*integer\b[^\n]*::[^\n]*\b%s\b(?!\s*=\s*\d+\s*,\s*\w)' % var, body, re.I | re.M)
            # ignore the typed implied-do itself when checking for a declaration
            declared = [d for d in re.finditer(r'^\s*integer\b[^\n]*::([^\n]*)$', body, re.I | re.M)
                        if re.search(r'(^|,)\s*%s\s*(,|$|=)' % var, d.group(1), re.I)]
            if not declared:
                needed.setdefault(h, set()).add(var)
        lines[n] = TYPED.sub(lambda m: ', %s=' % m.group(1), lines[n])
    # insert declarations after 'implicit none' (or after the last USE) of each procedure, bottom-up
    for h in sorted(needed, reverse=True):
        k = h + 1
        while lines[k - 1].rstrip().endswith('&'):
            k += 1
        ins = k
        j = k
        while j < len(lines) and (lines[j].strip() == '' or lines[j].lstrip().startswith('!') or
                                   re.match(r'^\s*(use\b|implicit\s+none)', lines[j], re.I) or
                                   lines[j - 1].rstrip().endswith('&')):
            if re.match(r'^\s*(use\b|implicit\s+none)', lines[j], re.I) or lines[j - 1].rstrip().endswith('&'):
                ins = j + 1
            j += 1
        indent = re.match(r'^(\s*)', lines[ins - 1] if ins > h + 1 else lines[h]).group(1) or '   '
        for var in sorted(needed[h]):
            lines.insert(ins, f'{indent}integer :: {var} ! implied-do index (gfortran does not support F2018 typed implied-do)')
        print(f'{path}: declared {sorted(needed[h])} in procedure at line {h + 1}')
    open(path, 'w').write('\n'.join(lines))
