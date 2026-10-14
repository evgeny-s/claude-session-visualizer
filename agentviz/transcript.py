"""Transcript parsing: Claude Code session files and pasted / Agent SDK transcripts -> timeline events."""
import json, re, tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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


def parse_text(text, name):
    """Parse a pasted transcript: Claude Code JSONL, a JSON array of entries, or an Agent SDK
    stream (entries without timestamps, subagents via parent_tool_use_id), optionally wrapped
    in an object with a "transcript" list (e.g. a run record with createdAt/durationMs)."""
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
