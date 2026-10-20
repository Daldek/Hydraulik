"""Heuristic: find local POINTER variables (not dummies, no '=> null()' init) whose first use in the
procedure body is reallocP(...)/associated(...)/deallocate(...) - i.e. their association status is
undefined at that point (works by luck with ifx, crashes with gfortran)."""
import re, sys, pathlib
HDR = re.compile(r'^\s*(?:(?:pure|elemental|recursive|impure|module)\s+)*(?:(?:integer|logical|real|double precision|character|type\s*\([^)]*\))(?:\s*\([^)]*\))?\s+)?(subroutine|function)\s+(\w+)\s*(\(([^)]*)\))?', re.I)
END = re.compile(r'^\s*end\s*(subroutine|function)\b', re.I)
DECL = re.compile(r'^\s*[^!]*\bpointer\b[^!]*::\s*(.*)$', re.I)
for root in sys.argv[1:]:
    for p in pathlib.Path(root).rglob('*'):
        if p.suffix.lower() not in ('.f90',) or '/test' in str(p):
            continue
        lines = p.read_text(errors='replace').split('\n')
        i = 0
        while i < len(lines):
            m = HDR.match(lines[i])
            if m and not lines[i].lstrip().lower().startswith('end'):
                # collect header incl. continuation
                hdr = lines[i]; k = i
                while hdr.rstrip().endswith('&'):
                    k += 1; hdr = hdr.rstrip()[:-1] + lines[k].lstrip().lstrip('&')
                am = re.search(r'\(([^)]*)\)', hdr[hdr.lower().find(m.group(1).lower()):])
                args = {a.strip().lower() for a in (am.group(1).split(',') if am else [])}
                j = k + 1
                while j < len(lines) and not END.match(lines[j]) and not HDR.match(lines[j]):
                    j += 1
                body = [l.split('!')[0] for l in lines[k + 1:j]]
                ptrs = {}
                for n, l in enumerate(body):
                    d = DECL.match(l)
                    if d and 'intent' not in l.lower() and not re.match(r'^\s*procedure', l, re.I):
                        for item in re.split(r',(?![^()]*\))', d.group(1)):
                            nm = re.match(r'\s*(\w+)', item)
                            if nm and '=>' not in item and nm.group(1).lower() not in args:
                                ptrs[nm.group(1).lower()] = n
                for nm, dn in ptrs.items():
                    pat = re.compile(r'\b%s\b' % nm, re.I)
                    for n in range(dn + 1, len(body)):
                        l = body[n]
                        if not pat.search(l) or DECL.match(l):
                            continue
                        low = l.lower()
                        if re.search(r'(nullify\s*\([^)]*\b%s\b|\b%s\b\s*(\([^)]*\))?\s*=>\s*null\s*\()' % (nm, nm), low):
                            break
                        if not re.search(r'(reallocp|realloc)\s*\(\s*%s\b|associated\s*\(\s*%s\b|deallocate\s*\(\s*%s\b' % (nm, nm, nm), low):
                            continue
                        if re.search(r'(reallocp|realloc)\s*\(\s*%s\b|associated\s*\(\s*%s\b|deallocate\s*\(\s*%s\b' % (nm, nm, nm), low):
                            print(f'{p}:{k + 2 + n}: {nm}: {l.strip()[:100]}')
                        break
                i = j
                continue
            i += 1
