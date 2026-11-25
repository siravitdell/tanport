"""Run the API server, the worker and the Next.js dev server together for local development.

Cross-platform (Windows + POSIX). Ctrl+C stops all of them. Used by `make dev`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def commands() -> dict[str, tuple[list[str], Path | None]]:
    cmds: dict[str, tuple[list[str], Path | None]] = {
        "api": (
            [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
            None,
        ),
        "worker": ([sys.executable, "-m", "app.worker"], None),
    }
    npm = shutil.which("npm")  # npm.cmd on Windows
    if npm is None:
        print("[dev] npm not found: starting without the web app", flush=True)
    elif not (FRONTEND / "node_modules").is_dir():
        print("[dev] frontend/node_modules missing (run `make install`): no web app", flush=True)
    else:
        cmds["web"] = ([npm, "run", "dev"], FRONTEND)
    return cmds


def main() -> int:
    procs = {name: subprocess.Popen(cmd, cwd=cwd) for name, (cmd, cwd) in commands().items()}
    try:
        while True:
            for name, proc in procs.items():
                code = proc.poll()
                if code is not None:
                    print(f"[dev] {name} exited with code {code}; stopping the rest", flush=True)
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in procs.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
