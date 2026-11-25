"""Run the API server, the worker and the Next.js dev server together for local development.

Cross-platform (Windows + POSIX). Ctrl+C stops all of them. Used by `make dev`.

Code reload is done here, not with `uvicorn --reload`: on Windows uvicorn restarts its server
with a console-wide Ctrl+C event, which also kills every other process in the terminal. Instead,
when a .py file under app/ changes, the API and the worker are restarted (the worker needs the
new code too). Next.js reloads itself.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
WATCH = BACKEND / "app"
WINDOWS = sys.platform == "win32"
POLL_S = 0.5


@dataclass
class Proc:
    name: str
    cmd: list[str]
    cwd: Path | None = None
    reload: bool = False  # restart when backend code changes
    popen: subprocess.Popen[bytes] | None = field(default=None, init=False)

    def start(self) -> None:
        self.popen = subprocess.Popen(self.cmd, cwd=self.cwd)

    def stop(self) -> None:
        if self.popen is None or self.popen.poll() is not None:
            return
        if WINDOWS:
            # the whole tree: `next dev` and the uv launcher run child processes
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(self.popen.pid)],
                capture_output=True,
                check=False,
            )
        else:
            self.popen.terminate()
        try:
            self.popen.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.popen.kill()


def log(message: str) -> None:
    print(f"[dev] {message}", flush=True)


def snapshot() -> dict[Path, float]:
    return {p: p.stat().st_mtime for p in WATCH.rglob("*.py")}


def processes() -> list[Proc]:
    py = sys.executable
    procs = [
        Proc("api", [py, "-m", "uvicorn", "app.main:app", "--port", "8000"], reload=True),
        Proc("worker", [py, "-m", "app.worker"], reload=True),
    ]
    npm = shutil.which("npm")  # npm.cmd on Windows
    if npm is None:
        log("npm not found: starting without the web app")
    elif not (FRONTEND / "node_modules").is_dir():
        log("frontend/node_modules missing (run `make install`): no web app")
    else:
        procs.append(Proc("web", [npm, "run", "dev"], FRONTEND))
    return procs


def main() -> int:
    procs = processes()
    for proc in procs:
        proc.start()
    seen = snapshot()
    try:
        while True:
            time.sleep(POLL_S)
            for proc in procs:
                code = proc.popen.poll() if proc.popen else None
                if code is not None:
                    log(f"{proc.name} exited with code {code}; stopping the rest")
                    return code or 1
            current = snapshot()
            if current != seen:
                changed = sorted(
                    str(p.relative_to(BACKEND))
                    for p in current.keys() | seen.keys()
                    if current.get(p) != seen.get(p)
                )
                log(f"changed: {', '.join(changed[:5])}; restarting api + worker")
                seen = current
                for proc in procs:
                    if proc.reload:
                        proc.stop()
                        proc.start()
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in procs:
            proc.stop()


if __name__ == "__main__":
    raise SystemExit(main())
