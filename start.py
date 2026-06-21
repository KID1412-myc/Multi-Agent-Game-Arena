"""
MAGA Arena Launcher
====================
One-click launcher. Starts backend + frontend, opens browser.
"""

# 🔧 在所有 import 之前：强制 socket 只走 IPv4
import socket as _socket
_orig = _socket.getaddrinfo
def _v4(host, port, family=0, *a, **kw):
    return _orig(host, port, _socket.AF_INET, *a, **kw)
_socket.getaddrinfo = _v4

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent


def check(cmd: list[str], label: str) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        ver = r.stdout.strip() or r.stderr.strip()
        print(f"  {label}: {ver}")
        return True
    except FileNotFoundError:
        print(f"  [ERROR] {label} not found!")
        return False


def main():
    os.chdir(ROOT)

    print()
    print("  ============================================")
    print("    MAGA Arena v1.0 Launcher")
    print("  ============================================")
    print()

    # ── 1. Check environment ──
    print("[1/4] Checking environment...")

    if not check([sys.executable, "--version"], "Python"):
        input("Press Enter to exit...")
        sys.exit(1)

    if not check(["node", "--version"], "Node.js"):
        input("Press Enter to exit...")
        sys.exit(1)

    print("  OK")

    # ── 2. Check .env ──
    print()
    print("[2/4] Checking .env...")
    env_path = ROOT / ".env"

    if not env_path.exists():
        print("  .env not found, copying from .env.example...")
        example = ROOT / ".env.example"
        if example.exists():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print("  Opening Notepad - fill in your API keys, save, then close.")
        print("  If using relay, you only need RELAY_API_KEY and RELAY_API_BASE.")
        subprocess.Popen(["notepad", str(env_path)]).wait()
    else:
        print("  .env found - OK")

    # ── 3. Check dependencies ──
    print()
    print("[3/4] Checking dependencies...")

    # Python deps (quick check)
    try:
        import fastapi  # noqa
        print("  Python packages - OK")
    except ImportError:
        print("  Installing Python packages...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "pydantic", "httpx", "jinja2", "pyyaml", "fastapi",
             "uvicorn", "websockets", "python-dotenv", "-q"],
            check=True,
        )
        print("  Done")

    # Frontend deps
    node_modules = ROOT / "frontend" / "node_modules"
    postcss_plugin = ROOT / "frontend" / "node_modules" / "@tailwindcss" / "postcss"
    if not node_modules.exists() or not postcss_plugin.exists():
        print("  Installing frontend packages (first time, may take a while)...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        subprocess.run([npm_cmd, "install"], cwd=ROOT / "frontend", check=True, shell=(sys.platform == "win32"))
        print("  Done")
    else:
        print("  npm packages - OK")

    # ── 4. Launch ──
    print()
    print("[4/4] Launching services...")
    print("  Backend window will open (keep it open)")
    print("  Frontend window will open (keep it open)")
    print()

    # Backend — its own visible console window (via run.py wrapper, IPv4 patch included)
    subprocess.Popen(
        ["cmd", "/k", f"cd /d {ROOT} && title MAGA Backend && {sys.executable} run.py"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    time.sleep(2)

    # Frontend — its own visible console window
    subprocess.Popen(
        ["cmd", "/k", f"cd /d {ROOT / 'frontend'} && title MAGA Frontend && npm.cmd run dev"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    # Wait and open browser
    print("  Waiting for frontend...")
    time.sleep(5)
    webbrowser.open("http://localhost:5173")

    print()
    print("  ============================================")
    print("    Backend : http://localhost:8000")
    print("    Frontend: http://localhost:5173")
    print()
    print("    Close the two MAGA windows to stop.")
    print("    Or press Ctrl+C here + close the windows.")
    print("  ============================================")
    print()
    input("  Press Enter to exit this launcher...")


if __name__ == "__main__":
    main()
