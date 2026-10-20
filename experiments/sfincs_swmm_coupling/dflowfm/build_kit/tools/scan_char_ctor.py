"""Scan Fortran sources for array constructors of character literals with differing
lengths and no type-spec (accepted by Intel ifx, rejected by gfortran)."""
import re, sys, pathlib

lit = re.compile(r"""'(?:[^']|'')*'|"(?:[^"]|"")*\"""")
ctor = re.compile(r"(\[|\(/)([^\[\]]*?)(\]|/\))")

def joined_statements(text):
    buf = ""
    for line in text.splitlines():
        code = line
        # strip trailing comments (naive, ignores ! inside strings handled below)
        out, q = "", None
        for ch in code:
            if q:
                out += ch
                if ch == q: q = None
            elif ch in "'\"":
                q = ch; out += ch
            elif ch == "!":
                break
            else:
                out += ch
        s = out.rstrip()
        if s.endswith("&"):
            buf += s[:-1]
            continue
        st = s.lstrip()
        if buf and st.startswith("&"):
            st = st[1:]
        buf += st if buf else s
        yield buf
        buf = ""

for root in sys.argv[1:]:
    for p in pathlib.Path(root).rglob("*"):
        if p.suffix.lower() not in (".f90", ".f"):
            continue
        try:
            text = p.read_text(errors="replace")
        except Exception:
            continue
        for stmt in joined_statements(text):
            for m in ctor.finditer(stmt):
                body = m.group(2)
                if "::" in body:
                    continue
                items = [i.strip() for i in re.split(r",(?=(?:[^'\"]|'[^']*'|\"[^\"]*\")*$)", body)]
                if len(items) < 2 or not all(lit.fullmatch(i) for i in items):
                    continue
                lens = {len(i) - 2 for i in items}
                if len(lens) > 1:
                    print(f"{p}: {stmt.strip()[:160]}")
