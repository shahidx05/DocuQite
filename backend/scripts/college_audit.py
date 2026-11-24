import sys
from pathlib import Path

# Delegate to root scripts/college_audit.py
root_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "college_audit.py"
with open(root_script, "r", encoding="utf-8") as f:
    code = f.read()

exec(code, {"__name__": "__main__", "__file__": str(root_script)})
