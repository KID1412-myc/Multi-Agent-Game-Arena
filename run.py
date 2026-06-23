"""
MAGA Server Runner — 确保每次启动都是最新代码
"""
import socket as _s
_o = _s.getaddrinfo
_s.getaddrinfo = lambda h, p, f=0, *a, **kw: _o(h, p, _s.AF_INET, *a, **kw)

import os, sys, shutil, pathlib, signal

# ── 杀掉占用端口的旧进程 ──
PORT = int(os.getenv("SERVER_PORT", "8000"))
my_pid = os.getpid()

if sys.platform == "win32":
    import ctypes
    try:
        out = os.popen(f'netstat -ano | findstr ":{PORT}" | findstr "LISTENING"').read()
        for line in out.strip().split("\n"):
            parts = line.strip().split()
            pid_str = parts[-1] if parts else ""
            if pid_str.isdigit():
                pid = int(pid_str)
                if pid != my_pid:
                    ctypes.windll.kernel32.TerminateProcess(
                        ctypes.windll.kernel32.OpenProcess(1, 0, pid), 0)
    except Exception:
        pass

# ── 清缓存 ──
root = pathlib.Path(__file__).parent
for pyc in root.rglob("__pycache__"):
    try:
        shutil.rmtree(pyc)
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import importlib
importlib.invalidate_caches()

if __name__ == "__main__":
    import uvicorn, webbrowser, threading

    def _open_browser():
        import time as _time
        _time.sleep(1.5)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
