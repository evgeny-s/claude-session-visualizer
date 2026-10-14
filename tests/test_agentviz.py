"""Self-check. Run: python3 tests/test_agentviz.py  (or pytest)"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentviz.render import render
from agentviz.sessions import find_session, sessions
from agentviz.transcript import parse, parse_text

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo.jsonl"


def test_demo():
    d = parse_text(DEMO.read_text(), "demo")
    assert d["title"] and not d["synthetic"]
    tools = {e["id"] for e in d["events"] if e["k"] == "tool" and e["n"] == "Agent"}
    assert len(d["agents"]) == 4 and all(a["spawn"] in tools for a in d["agents"][1:])
    assert any(e.get("err") for e in d["events"])
    html = render(d)
    assert "</script" not in html.split("const DATA")[1].split("\n")[0]
    assert '<script src=' not in html and '<link rel="stylesheet" href="style.css">' not in html


def test_local_session():
    """Newest local session (one with subagents if any); skipped on machines without sessions."""
    rows = sessions(50)[1]
    pick = next((r for r in rows if r["subs"]), rows[0] if rows else None)
    if not pick:
        return print("no local sessions, skipped")
    f = find_session(pick["id"])
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


def test_sdk_stream():
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
