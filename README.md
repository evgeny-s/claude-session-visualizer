# ai-viz

Animated, playable visualization of a Claude Code agent session: prompts → agents → tools → targets, with a scrubbable timeline.

```
python3 agentviz.py            # local web UI (127.0.0.1) with a session picker
python3 agentviz.py --list     # list recent sessions
python3 agentviz.py <id|path>  # build a standalone out/<id>.html
python3 agentviz.py --test     # self-check
```

Reads `~/.claude/projects`. The picker also accepts a pasted transcript: Claude Code JSONL, a JSON array, or an Agent SDK stream / run record. Python 3.9+, no dependencies.
