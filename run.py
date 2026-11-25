"""One command: python run.py  ->  installs what's missing, builds the UI, serves on http://localhost:8000"""
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
FRONT = ROOT / "frontend"
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PORT = int(os.getenv("PORT", 8000))


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def ensure_python():
    if Path(sys.prefix).resolve() == (ROOT / ".venv").resolve():
        return
    if not VENV_PY.exists():
        print("· Creating virtualenv")
        subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])
    os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])


def ensure_frontend():
    dist = FRONT / "dist" / "index.html"
    src_mtime = max(p.stat().st_mtime for p in (FRONT / "src").rglob("*"))
    if dist.exists() and dist.stat().st_mtime >= src_mtime:
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit("Node.js (npm) is needed to build the interface: https://nodejs.org")
    if not (FRONT / "node_modules").exists():
        print("· Installing interface dependencies")
        subprocess.check_call([npm, "install", "--silent"], cwd=FRONT)
    print("· Building interface")
    subprocess.check_call([npm, "run", "build", "--silent"], cwd=FRONT)


if __name__ == "__main__":
    ensure_python()
    load_env()
    ensure_frontend()
    import uvicorn

    url = f"http://localhost:{PORT}"
    print(f"\n  Skald is running at {url}\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=PORT, log_level="warning")
