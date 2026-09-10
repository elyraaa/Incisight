"""Fail when common credential shapes appear in files tracked by the project."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"node_modules", ".venv", ".git", "dist", "__pycache__"}
patterns = [re.compile(r"(?i)(assemblyai_api_key|llm_api_key)[ \t]*=[ \t]*[^\s#]{12,}"), re.compile(r"sk-[A-Za-z0-9_-]{20,}")]
findings=[]
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in SKIP for part in path.parts) or path.name==".env": continue
    try: text=path.read_text(encoding="utf-8")
    except (UnicodeDecodeError,OSError): continue
    for pattern in patterns:
        if pattern.search(text): findings.append(str(path.relative_to(ROOT)))
if findings: raise SystemExit("Potential credentials found: "+", ".join(sorted(set(findings))))
print("No credential patterns found.")
