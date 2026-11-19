"""Starts a throwaway API for browser tests: fresh SQLite database, migrations applied, then uvicorn."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
for name in ("e2e.db", "e2e-storage"):
    p = root / name
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()

env = {
    **os.environ,
    "TALVYNZA_DATABASE_URL": "sqlite:///./e2e.db",
    "TALVYNZA_STORAGE_DIR": "./e2e-storage",
    "TALVYNZA_REQUIRE_EMAIL_VERIFICATION": "false",
    "TALVYNZA_RATE_LIMIT_ENABLED": "false",
    "TALVYNZA_CORS_ORIGINS": "http://localhost:5174",
    "TALVYNZA_FRONTEND_URL": "http://localhost:5174",
    "TALVYNZA_LOG_JSON": "false",
}
bin_dir = Path(sys.executable).parent
subprocess.run([str(bin_dir / "alembic"), "upgrade", "head"], check=True, env=env)
sys.exit(subprocess.call([str(bin_dir / "uvicorn"), "app.main:app", "--port", "8100"], env=env))
