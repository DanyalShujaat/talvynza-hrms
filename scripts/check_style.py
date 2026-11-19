"""Fails if tracked text files contain em dashes (U+2014). Run from the repo root: python scripts/check_style.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = ("package-lock.json",)
files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
bad = []
for name in filter(None, files):
    if name.endswith(SKIP) or name.endswith((".png", ".svg", ".ico", ".woff2")):
        continue
    path = ROOT / name
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for n, line in enumerate(text.splitlines(), 1):
        if "\u2014" in line:
            bad.append(f"{name}:{n}: {line.strip()[:100]}")
if bad:
    print("Em dashes are not allowed. Use a comma, colon, period or hyphen instead:\n" + "\n".join(bad))
    sys.exit(1)
print("style check passed")
