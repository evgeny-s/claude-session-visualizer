"""Discovering sessions under ~/.claude/projects."""
import glob, json, os, re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .transcript import clip

ROOT = Path.home() / ".claude" / "projects"


def find_session(arg):
    if os.path.isfile(arg):
        return Path(arg)
    hits = [Path(p) for p in glob.glob(str(ROOT / "*" / f"{arg}*.jsonl"))]
    if not hits:
        raise LookupError(f"no session matching {arg!r}")
    return max(hits, key=lambda p: p.stat().st_mtime)


@lru_cache(maxsize=None)
def title_of(path, mtime):
    """(title, subagent count); cached per file version. A /rename (custom-title) beats the auto ai-title."""
    titles = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            if '-title"' in line:
                d = json.loads(line)
                titles[d.get("type")] = d.get("customTitle") or d.get("aiTitle") or d.get("title")
    p = Path(path)
    return titles.get("custom-title") or titles.get("ai-title") or "", len(list((p.parent / p.stem / "subagents").glob("agent-*.jsonl")))


def sessions(n=None, offset=0, q=""):
    """-> (total matching, page of rows). Titles are only read for the page, unless searching."""
    files = sorted((f for f in ROOT.glob("*/*.jsonl") if not f.name.startswith("agent-")),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    home = re.sub(r"[^\w]", "-", str(Path.home()))  # project dirs are cwd paths with non-word chars -> "-"
    proj = lambda f: f.parent.name.removeprefix(home).strip("-") or f.parent.name
    if q := q.lower().strip():  # needs every title; cached after the first search
        files = [f for f in files if q in f"{f.stem} {proj(f)} {title_of(str(f), f.stat().st_mtime)[0]}".lower()]
    out = []
    for f in files[offset:offset + n if n else None]:
        st = f.stat()
        title, subs = title_of(str(f), st.st_mtime)
        out.append({"id": f.stem, "project": proj(f), "title": title,
                    "mtime": st.st_mtime, "kb": st.st_size // 1024, "subs": subs})
    return len(files), out


def list_sessions(n=20):
    for x in sessions(n)[1]:
        when = datetime.fromtimestamp(x["mtime"]).strftime("%m-%d %H:%M")
        print(f"{x['id'][:8]}  {when}  {x['project'][:34]:34}  {clip(x['title'], 60)}")
    print("\nrun: python3 -m claudeviz <id-prefix>")
