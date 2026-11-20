"""Start the isolated, persistent fictional demo. Ctrl+C stops the owned servers."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"
WEB = ROOT / "apps/web"
STATE = ROOT / ".local/demo"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=8010)
    parser.add_argument("--web-port", type=int, default=5180)
    args = parser.parse_args()
    for port in (args.api_port, args.web_port):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                sys.exit(f"Port {port} is in use. Stop the previous demo or choose another port.")
    if not (WEB / "node_modules").is_dir():
        sys.exit("Run npm ci in apps/web first.")
    STATE.mkdir(parents=True, exist_ok=True)
    settings_path = STATE / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(json.dumps({"secret": secrets.token_urlsafe(48),
                                            "domain": f"demo-{secrets.token_hex(4)}.example.com"}), encoding="utf-8")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    accounts = STATE / "accounts.json"
    base = f"http://127.0.0.1:{args.api_port}"
    web_url = f"http://localhost:{args.web_port}"
    env = {**os.environ, "TALVYNZA_ENVIRONMENT": "development", "TALVYNZA_SECRET_KEY": settings["secret"],
           "TALVYNZA_DATABASE_URL": "sqlite:///" + (STATE / "demo.db").as_posix(),
           "TALVYNZA_STORAGE_DIR": str(STATE / "uploads"), "TALVYNZA_DEMO_ACCOUNTS_FILE": str(accounts),
           "TALVYNZA_EMAIL_BACKEND": "console", "TALVYNZA_LOG_JSON": "false", "TALVYNZA_REDIS_URL": "",
           "TALVYNZA_REQUIRE_EMAIL_VERIFICATION": "false", "TALVYNZA_RATE_LIMIT_ENABLED": "false",
           "TALVYNZA_CORS_ORIGINS": web_url, "TALVYNZA_FRONTEND_URL": web_url,
           "TALVYNZA_AI_ENABLED": "true", "TALVYNZA_AI_OLLAMA_URL": "http://127.0.0.1:11434",
           "VITE_API_PROXY": base}
    # Empty Redis URL selects the in-process development limiter; this demo needs no broker.
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=env, check=True)
    children = []
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        with (STATE / "api.log").open("a", encoding="utf-8") as api_log, (STATE / "web.log").open("a", encoding="utf-8") as web_log:
            children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)], cwd=API, env=env, stdout=api_log, stderr=subprocess.STDOUT, **hidden))
            wait_ready(base + "/health/ready", children[0])
            if not accounts.exists():
                print("Preparing fictional people and HR workflows...", flush=True)
                with (STATE / "seed.log").open("w", encoding="utf-8") as seed_log:
                    seeded = subprocess.run([sys.executable, "scripts/seed_demo.py", "--api", base, "--api-log", str(STATE / "api.log"), "--domain", settings["domain"], "--accounts-file", str(accounts)], cwd=API, env=env, stdout=seed_log, stderr=subprocess.STDOUT)
                if seeded.returncode:
                    sys.exit(f"Demo preparation failed. See {STATE / 'seed.log'}. Existing data was preserved.")
            children.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"], cwd=WEB, env=env, stdout=web_log, stderr=subprocess.STDOUT, **hidden))
            wait_ready(web_url, children[1])
            print(f"\nTalvynza is ready: {web_url}\nSign in: {web_url}/login\nData and logs: {STATE}\nKeep this terminal open. Press Ctrl+C to stop.\n", flush=True)
            while all(child.poll() is None for child in children):
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping the demo. Your fictional data is saved.")
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)


def wait_ready(url, process):
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError("Server exited. Check the demo log files.")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Server did not become ready: {url}")


if __name__ == "__main__":
    main()
