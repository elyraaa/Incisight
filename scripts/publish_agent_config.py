"""Compile the reviewable config into the current Voice Agent session.update shape.

The current AssemblyAI Voice Agent API is configured per WebSocket session, so
'publishing' means producing the exact payload the browser sends, not mutating a
remote persistent agent. Secrets are neither read nor written by this script.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = json.loads((root / "agent-config.json").read_text(encoding="utf-8"))
required = {"name", "voice", "system_prompt", "input", "output"}
missing = required - config.keys()
if missing: raise SystemExit(f"Missing agent config fields: {sorted(missing)}")
payload = {"type": "session.update", "session": {key: config[key] for key in ("system_prompt", "greeting", "input", "output")}}
target = root / "agent-session-update.json"
target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {target}. Runtime tool schemas and incident keyterms are merged by frontend/src/voice.ts.")

