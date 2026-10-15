"""Render parsed data into a single self-contained HTML page (ui/ files inlined)."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def render(data):
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (UI / "index.html").read_text()
    html = html.replace('<link rel="stylesheet" href="style.css">', "<style>\n" + (UI / "style.css").read_text() + "</style>")
    for js in ("app.js", "picker.js"):
        code = (UI / js).read_text().replace("/*__DATA__*/null", blob)
        html = html.replace(f'<script src="{js}"></script>', "<script>\n" + code + "</script>")
    return html


def build(data, out_dir=REPO / "out"):
    out = Path(out_dir) / f"{data['id']}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(data))
    return out
