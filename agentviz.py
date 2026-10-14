#!/usr/bin/env python3
"""Render a Claude Code session transcript as an animated, playable web visualization.

usage: agentviz.py                 # local web UI with a session picker
       agentviz.py --list           # list recent sessions
       agentviz.py <id-prefix|path> # build out/<id>.html and open it
       agentviz.py --test           # self-check
"""
import glob, json, os, re, sys, webbrowser
from functools import lru_cache
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
HERE = Path(__file__).resolve().parent
NOISE = re.compile(r"^\s*<(system-reminder|task-notification|agent-message|local-command|command-|tool|persisted-output|bash-|total)")
CLIP = 180


def clip(s, n=CLIP):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def ts(d):
    t = d.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else None


def target(name, inp):
    """Short label for what a tool touched."""
    if not isinstance(inp, dict):
        return name
    if p := inp.get("file_path") or inp.get("notebook_path"):
        parts = Path(p).parts
        return "/".join(parts[-2:])
    if name == "Bash" and (c := inp.get("command")):
        w = c.strip().split()
        w = [x for x in w if "=" not in x.split("/")[0]] or w  # skip VAR=x prefixes
        return Path(w[0]).name if w else "sh"
    if name in ("Grep", "Glob"):
        return clip(inp.get("pattern"), 28)
    if name in ("WebFetch",) and (u := inp.get("url")):
        return re.sub(r"^https?://([^/]+).*", r"\1", u)
    if name == "WebSearch":
        return "web"
    if name in ("Agent", "Task"):
        return inp.get("subagent_type") or "agent"
    if name == "Skill":
        return inp.get("skill") or "skill"
    if name.startswith("mcp__"):
        return name.split("__")[1]
    return name


def summary(name, inp):
    if not isinstance(inp, dict):
        return ""
    for k in ("description", "command", "file_path", "pattern", "url", "query", "prompt", "skill"):
        if inp.get(k):
            return clip(inp[k])
    return clip(json.dumps(inp, ensure_ascii=False))


def result_text(c):
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return clip(c, 140)


def find_session(arg):
    if os.path.isfile(arg):
        return Path(arg)
    hits = [Path(p) for p in glob.glob(str(ROOT / "*" / f"{arg}*.jsonl"))]
    if not hits:
        raise LookupError(f"no session matching {arg!r}")
    return max(hits, key=lambda p: p.stat().st_mtime)


def subagent_files(main):
    sid = main.stem
    files = sorted((main.parent / sid / "subagents").glob("agent-*.jsonl"))
    for f in sorted(main.parent.glob("agent-*.jsonl")):  # older layout: sidechain files next to main
        try:
            if json.loads(f.open().readline()).get("sessionId") == sid:
                files.append(f)
        except Exception:
            pass
    return files


def parse(main):
    """-> dict with agents, events (sorted by time), title."""
    agents = [{"id": "main", "label": "main", "type": "main", "parent": None, "spawn": None}]
    sources = [("main", main, {})]
    for f in subagent_files(main):
        meta = {}
        mf = f.with_suffix(".meta.json")
        if mf.exists():
            meta = json.loads(mf.read_text())
        aid = f.stem.removeprefix("agent-")
        agents.append({"id": aid, "label": meta.get("description") or aid, "type": meta.get("agentType") or "agent",
                       "parent": None, "spawn": meta.get("toolUseId")})
        sources.append((aid, f, meta))

    events, tools, seen_msg, title = [], {}, set(), None
    first_prompt = {}
    for aid, f, _ in sources:
        first_user = True
        for line in f.open():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "ai-title" and aid == "main":
                title = d.get("aiTitle") or d.get("title") or title
            if d.get("type") not in ("user", "assistant") or d.get("isMeta"):
                continue
            if aid == "main" and d.get("isSidechain"):
                continue
            t = ts(d)
            if t is None:
                continue
            m = d.get("message") or {}
            content = m.get("content")
            if d["type"] == "user":
                blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
                for b in blocks:
                    if b.get("type") == "tool_result":
                        tid = b.get("tool_use_id")
                        if tid in tools:
                            tools[tid]["end"] = t
                            tools[tid]["err"] = bool(b.get("is_error"))
                            tools[tid]["out"] = result_text(b.get("content"))
                    elif b.get("type") == "text" and b.get("text"):
                        txt = b["text"]
                        if first_user and aid != "main":
                            first_prompt[aid] = txt
                        elif NOISE.match(txt):
                            kind = re.match(r"\s*<([a-z-]+)", txt).group(1)
                            events.append({"k": "sys", "a": aid, "t": t, "x": kind})
                        else:
                            events.append({"k": "prompt", "a": aid, "t": t, "x": clip(txt, 300)})
                    elif b.get("type") == "image":
                        events.append({"k": "prompt", "a": aid, "t": t, "x": "[image]"})
                    first_user = False
                first_user = False
            else:
                mid = m.get("id")
                u = m.get("usage") or {}
                if mid and mid not in seen_msg and u:
                    seen_msg.add(mid)
                    events.append({"k": "tok", "a": aid, "t": t, "o": u.get("output_tokens") or 0,
                                   "i": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                                   + (u.get("cache_creation_input_tokens") or 0)})
                for b in content or []:
                    bt = b.get("type")
                    if bt == "text" and b.get("text", "").strip():
                        events.append({"k": "say", "a": aid, "t": t, "x": clip(b["text"], 300)})
                    elif bt == "thinking":
                        events.append({"k": "think", "a": aid, "t": t, "x": clip(b.get("thinking"), 200)})
                    elif bt == "tool_use":
                        n, inp = b.get("name", "?"), b.get("input")
                        e = {"k": "tool", "a": aid, "t": t, "id": b.get("id"), "n": n,
                             "tg": target(n, inp), "x": summary(n, inp), "end": None, "err": False, "out": ""}
                        if n in ("Agent", "Task") and isinstance(inp, dict):
                            e["prompt"] = inp.get("prompt", "")
                        tools[e["id"]] = e
                        events.append(e)

    # link subagents to the tool_use that spawned them (meta id, else matching prompt text)
    for a in agents[1:]:
        sp = tools.get(a["spawn"])
        if not sp:
            fp = first_prompt.get(a["id"], "")
            sp = next((e for e in tools.values() if e.get("prompt") and e["prompt"] == fp), None)
        if sp:
            a["spawn"], a["parent"] = sp["id"], sp["a"]
            if a["label"] == a["id"]:
                a["label"] = clip(sp["x"], 40)
        else:
            a["spawn"], a["parent"] = None, "main"
    for e in tools.values():
        e.pop("prompt", None)

    events.sort(key=lambda e: e["t"])
    for a in agents:  # lane span from the agent's own events (background agents return early)
        ts_ = [e["t"] for e in events if e["a"] == a["id"]]
        a["t0"], a["t1"] = (min(ts_), max(ts_)) if ts_ else (None, None)
    agents = [a for a in agents if a["t0"] is not None]
    return {"id": main.stem, "title": title or main.parent.name, "agents": agents, "events": events}


@lru_cache(maxsize=None)
def title_of(path, mtime):
    """(ai-title, subagent count); cached per file version."""
    title = ""
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"ai-title"' in line:
                d = json.loads(line)
                title = d.get("aiTitle") or d.get("title") or title
    p = Path(path)
    return title, len(list((p.parent / p.stem / "subagents").glob("agent-*.jsonl")))


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
    print("\nrun: agentviz.py <id-prefix>")


def render(data):
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return (HERE / "viz.html").read_text().replace("/*__DATA__*/null", blob)


def build(data):
    html = render(data)
    out = HERE / "out" / f"{data['id']}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    return out


def test():
    """Self-check: a synthetic SDK stream always; plus the newest local session (one with subagents if any)."""
    rows = sessions(50)[1]
    pick = next((r for r in rows if r["subs"]), rows[0] if rows else None)
    if pick:
        test_session(find_session(pick["id"]))
    else:
        print("no local sessions, skipping real-session checks")
    test_sdk()
    print("ok")


def test_session(f):
    d = parse(f)
    main_tools = [e for e in d["events"] if e["k"] == "tool" and e["a"] == "main"]
    msg_ids, raw_tools = set(), 0
    for line in f.open():
        x = json.loads(line)
        if x.get("type") == "assistant" and not x.get("isSidechain"):
            c = x["message"].get("content")
            raw_tools += sum(1 for b in c if b.get("type") == "tool_use") if isinstance(c, list) else 0
            if x["message"].get("usage"):
                msg_ids.add(x["message"]["id"])
    assert len(main_tools) == raw_tools, (len(main_tools), raw_tools)
    ids = {e["id"] for e in d["events"] if e["k"] == "tool" and e["n"] in ("Agent", "Task")}
    assert all(a["spawn"] in ids for a in d["agents"][1:] if a["spawn"]), d["agents"]
    assert sum(1 for e in d["events"] if e["k"] == "tok" and e["a"] == "main") == len(msg_ids)
    d2 = parse_text(f.read_text(), "pasted-t")
    assert sum(e["k"] == "tool" and e["a"] == "main" for e in d2["events"]) == raw_tools
    arr = "[" + ",".join(l for l in f.read_text().splitlines() if l.strip()) + "]"
    assert len(parse_text(arr, "pasted-t")["events"]) == len(d2["events"])
    try:
        parse_text('{"type":"mode"}', "x")
        raise AssertionError("empty transcript accepted")
    except ValueError:
        pass
    assert "</script" not in build(d).read_text().split("const DATA")[1].split("\n")[0]


def test_sdk():
    sdk = [{"type": "system", "subtype": "init"},
           {"type": "user", "parent_tool_use_id": None, "message": {"content": "check the pods"}},
           {"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m1", "usage": {"output_tokens": 0}, "content": [
               {"type": "tool_use", "id": "toolu_A", "name": "Task", "input": {"description": "scan logs", "prompt": "go"}}]}},
           {"type": "user", "parent_tool_use_id": "toolu_A", "message": {"content": "go"}},
           {"type": "assistant", "parent_tool_use_id": "toolu_A", "message": {"id": "m2", "content": [
               {"type": "tool_use", "id": "toolu_B", "name": "Bash", "input": {"command": "kubectl get pods"}}]}},
           {"type": "user", "parent_tool_use_id": "toolu_A", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "ok"}]}},
           {"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m3", "usage": {"output_tokens": 0}, "content": [{"type": "text", "text": "done"}]}},
           {"type": "result", "duration_ms": 5000, "usage": {"output_tokens": 42, "input_tokens": 7}}]
    d3 = parse_text(json.dumps({"transcript": sdk, "issueId": "run-x", "createdAt": "2026-10-14T09:00:00Z"}), "pasted-sdk")
    assert d3["synthetic"] and d3["title"] == "run-x"
    assert [a["spawn"] for a in d3["agents"]] == [None, "toolu_A"], d3["agents"]
    assert sum(e["o"] for e in d3["events"] if e["k"] == "tok") == 42
    assert [e["k"] for e in d3["events"] if e["a"] == "main" and e["k"] != "tok"] == ["prompt", "tool", "say"]
    assert d3["events"][-1]["t"] - d3["events"][0]["t"] == 5


def parse_text(text, name):
    """Parse a pasted transcript: Claude Code JSONL, a JSON array of entries, or an Agent SDK
    stream (entries without timestamps, subagents via parent_tool_use_id), optionally wrapped
    in an object with a "transcript" list (e.g. a run record with createdAt/durationMs)."""
    import tempfile
    from collections import defaultdict
    t = text.strip()
    try:
        doc = json.loads(t)
    except ValueError:
        doc = [json.loads(l) for l in t.splitlines() if l.strip()]
    run = doc if isinstance(doc, dict) and isinstance(doc.get("transcript"), list) else {}
    entries = run.get("transcript") or (doc if isinstance(doc, list) else [doc])
    entries = [e for e in entries if isinstance(e, dict)]

    synthetic = not any(e.get("timestamp") for e in entries)
    if synthetic:  # ponytail: even spacing over the run's duration; real per-step timing isn't recorded
        steps = [e for e in entries if e.get("type") in ("user", "assistant")]
        res = next((e for e in entries if e.get("type") == "result"), {})
        t0 = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00")).timestamp() if run.get("createdAt") else datetime.now().timestamp()
        dur = (run.get("durationMs") or res.get("duration_ms") or len(steps) * 1000) / 1000
        for i, e in enumerate(steps):
            e["timestamp"] = datetime.fromtimestamp(t0 + dur * i / max(1, len(steps) - 1)).astimezone().isoformat()
        # SDK streams often report zero per-message usage; put the run total on the last assistant message
        asst = [e for e in steps if e.get("type") == "assistant" and not e.get("parent_tool_use_id")]
        if asst and res.get("usage") and not any((e.get("message") or {}).get("usage", {}).get("output_tokens") for e in asst):
            asst[-1]["message"]["usage"] = res["usage"]

    groups = defaultdict(list)
    for e in entries:
        groups[e.get("parent_tool_use_id")].append(e)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / f"{name}.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in groups.pop(None, [])))
        sub = Path(d) / name / "subagents"
        for tid, es in groups.items():
            sub.mkdir(parents=True, exist_ok=True)
            aid = re.sub(r"\W", "_", str(tid))
            (sub / f"agent-{aid}.jsonl").write_text("\n".join(json.dumps(e) for e in es))
            (sub / f"agent-{aid}.meta.json").write_text(json.dumps({"toolUseId": tid}))
        data = parse(f)
        tmpname = Path(d).name
    if not any(e["k"] != "tok" for e in data["events"]):
        raise ValueError("no user/assistant entries found")
    if data["title"] == tmpname:
        data["title"] = run.get("issueId") or "pasted transcript"
    data["synthetic"] = synthetic
    return data


def serve(port=8765):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            from urllib.parse import parse_qs, urlsplit
            u = urlsplit(self.path)
            path, qs = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if path == "/":
                    latest = sessions(1)[1]
                    if not latest:
                        return self.send(404, "no sessions found")
                    self.send(302, "", Location=f"/s/{latest[0]['id']}#pick")
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


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        serve()
    elif a[0] == "--list":
        list_sessions()
    elif a[0] == "--test":
        test()
    else:
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
