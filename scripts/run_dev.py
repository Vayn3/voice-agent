from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Voice TA backend and frontend.")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    if not args.skip_install and not (FRONTEND_DIR / "node_modules").exists():
        print("frontend/node_modules not found. Running npm install first...")
        install = subprocess.run(["npm", "install"], cwd=FRONTEND_DIR)
        if install.returncode != 0:
            return install.returncode

    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = f"http://127.0.0.1:{args.backend_port}"

    backend_cmd = (
        "conda run -n voiceTA python -m uvicorn backend.app.main:app "
        f"--reload --host 127.0.0.1 --port {args.backend_port}"
    )
    frontend_cmd = f"npm run dev -- --port {args.frontend_port}"

    print("Starting Voice TA development services...")
    print(f"Backend:  http://127.0.0.1:{args.backend_port}")
    print(f"Frontend: http://localhost:{args.frontend_port}")
    print("Press Ctrl+C in this terminal to stop both services.")

    processes = [
        subprocess.Popen(backend_cmd, cwd=ROOT, env=env, shell=True),
        subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR, env=env, shell=True),
    ]

    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    stop_processes(processes)
                    return code
            _sleep()
    except KeyboardInterrupt:
        print("\nStopping Voice TA development services...")
        stop_processes(processes)
        return 0


def _sleep() -> None:
    import time

    time.sleep(1)


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    sys.exit(main())
