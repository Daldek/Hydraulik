"""Find ', )' (empty last actual/dummy argument) in free-form Fortran after joining continuation lines."""
import re, sys, pathlib
for root in sys.argv[1:]:
    for p in pathlib.Path(root).rglob("*"):
        if p.suffix.lower() != ".f90":
            continue
        buf = ""
        for line in p.read_text(errors="replace").splitlines():
            out, q = "", None
            for ch in line:
                if q:
                    if ch == q: q = None
                    out += "x"; continue
                if ch in "'\"": q = ch; out += "x"; continue
                if ch == "!": break
                out += ch
            s = out.strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            if buf and s.startswith("&"):
                s = s[1:]
            if s.endswith("&"):
                buf += s[:-1]; continue
            stmt = buf + s; buf = ""
            if re.search(r",\s*\)", stmt) and not re.search(r"\(\s*/|/\s*\)", stmt):
                print(f"{p}: {stmt[:140]}")
