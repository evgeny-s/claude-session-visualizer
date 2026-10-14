"""usage: python3 -m agentviz                  # local web UI with a session picker
       python3 -m agentviz --list           # list recent sessions
       python3 -m agentviz <id-prefix|path> # build a standalone out/<id>.html and open it
"""
import sys, webbrowser
from pathlib import Path

from .render import build
from .server import serve
from .sessions import ROOT, find_session, list_sessions
from .transcript import parse, parse_text


def main(a):
    if not a:
        return serve()
    if a[0] in ("-h", "--help"):
        return print(__doc__)
    if a[0] == "--list":
        return list_sessions()
    try:
        p = Path(a[0]).expanduser()
        if p.is_file() and ROOT not in p.resolve().parents:  # exported / SDK transcript, not a session file
            out = build(parse_text(p.read_text(), p.stem))
        else:
            out = build(parse(find_session(a[0])))
    except (LookupError, ValueError) as e:
        sys.exit(str(e))
    print(out)
    webbrowser.open(out.as_uri())


main(sys.argv[1:])
