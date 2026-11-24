"""Run the API server and the worker together for local development.

Cross-platform (Windows + POSIX). Ctrl+C stops both. Used by `make dev`.
"""

from __future__ import annotations

import subprocess
import sys
import time

COMMANDS: dict[str, list[str]] = {
    "api": [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
    "worker": [sys.executable, "-m", "app.worker"],
}


def main() -> int:
    procs = {name: subprocess.Popen(cmd) for name, cmd in COMMANDS.items()}
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
