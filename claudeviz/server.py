"""Local web UI: session picker + player. Binds 127.0.0.1 only: transcripts are private."""
import json, re, sys, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .render import REPO, render
from .sessions import find_session, sessions
from .transcript import parse, parse_text

DEMO = REPO / "examples" / "demo.jsonl"


def serve(port=8765):
    pasted = {}  # ponytail: in-memory, lost on restart; fine for a local viewer

    class H(BaseHTTPRequestHandler):
        def send(self, code, body, ctype="text/html; charset=utf-8", **hdr):
            body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in hdr.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlsplit(self.path)
            path, qs = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if path == "/":
                    latest = sessions(1)[1]
                    self.send(302, "", Location=f"/s/{latest[0]['id']}#pick" if latest else "/demo#pick")
                elif path == "/demo":
                    self.send(200, render(parse_text(DEMO.read_text(), "demo")))
                elif path == "/api/sessions":
                    total, rows = sessions(min(200, int(qs.get("limit", 50))), int(qs.get("offset", 0)), qs.get("q", ""))
                    self.send(200, json.dumps({"total": total, "items": rows}), "application/json")
                elif (m := re.fullmatch(r"/p/(\d+)", path)) and m[1] in pasted:
                    self.send(200, pasted[m[1]])
                elif (m := re.fullmatch(r"/s/([\w-]+)", path)):  # no slashes/dots: ids only, never paths
                    self.send(200, render(parse(find_session(m[1]))))
                else:
                    self.send(404, "not found")
            except LookupError as e:
                self.send(404, str(e))
            except ValueError:
                self.send(400, "bad request")

        def do_POST(self):
            if self.path != "/api/paste":
                return self.send(404, "not found")
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200 * 1024 * 1024:
                return self.send(413, "too large")
            try:
                key = str(len(pasted) + 1)
                pasted[key] = render(parse_text(self.rfile.read(n).decode("utf-8", "replace"), f"pasted-{key}"))
                self.send(200, json.dumps({"url": f"/p/{key}"}), "application/json")
            except Exception as e:  # bad paste -> readable error in the modal, not a dropped connection
                self.send(400, f"can't parse transcript: {type(e).__name__}: {e}", "text/plain; charset=utf-8")

        def log_message(self, *a):
            pass

    for p in range(port, port + 20):  # first free port in a fixed range -> same URL across restarts
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), H)  # local only: transcripts are private
            break
        except OSError:
            continue
    else:
        sys.exit(f"ports {port}-{port + 19} are all busy")
    url = f"http://127.0.0.1:{srv.server_port}/"
    print(url, "(ctrl+c to stop)", flush=True)
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
