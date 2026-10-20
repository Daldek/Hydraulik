"""Add 'use precision, only: dp' to module procedures that use the dp kind but do not import it
(ifx accepted these; gfortran reports 'Missing kind-parameter')."""
import re, sys
HDR = re.compile(r'^\s*(?:(?:pure|elemental|recursive|impure|module)\s+)*(subroutine|function)\s+(\w+)', re.I)
END = re.compile(r'^\s*end\s*(subroutine|function)\b', re.I)
for path in sys.argv[1:]:
    lines = open(path).read().split('\n')
    i, todo = 0, []
    while i < len(lines):
        if HDR.match(lines[i]) and not lines[i].lstrip().lower().startswith('end'):
            j = i + 1
            while j < len(lines) and not END.match(lines[j]):
                j += 1
            body = '\n'.join(l.split('!')[0] for l in lines[i:j])
            uses_dp = re.search(r'(_dp\b|kind\s*=\s*dp\b|\(\s*dp\s*\))', body, re.I)
            has_dp = re.search(r'^\s*use\s+precision\b[^\n]*\bdp\b|^\s*use\s+precision\s*$', body, re.I | re.M)
            if uses_dp and not has_dp:
                k = i
                while lines[k].rstrip().endswith('&'):
                    k += 1
                todo.append((k + 1, HDR.match(lines[i]).group(2)))
            i = j
        i += 1
    for k, name in reversed(todo):
        indent = re.match(r'^(\s*)', lines[k - 1]).group(1) + '   '
        lines.insert(k, f'{indent}use precision, only: dp')
        print(f'{path}: added dp import to {name}')
    open(path, 'w').write('\n'.join(lines))
