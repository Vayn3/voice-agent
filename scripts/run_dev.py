from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


def _conda_env_python(env_name: str = "voiceTA") -> str:
    """Locate the Python interpreter of a conda env without relying on `conda run`.

    Falls back to a common Anaconda layout, then to the bare `python` command.
    """
    candidates = []
    try:
        base = subprocess.check_output(
            ["conda", "info", "--base"], stderr=subprocess.DEVNULL
        ).decode().strip()
        candidates.append(os.path.join(base, "envs", env_name, "bin", "python"))
    except Exception:
        pass
    candidates.append(os.path.expanduser(f"~/Software/anaconda3/envs/{env_name}/bin/python"))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return "python"


MYSQL_SECURE_SQL = (
    "ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';"
    "CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'root';"
    "CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'root';"
    "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;"
    "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;"
    "CREATE DATABASE IF NOT EXISTS voiceTA CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    "FLUSH PRIVILEGES;"
)


def _ensure_mysql() -> None:
    """Start the bundled Anaconda MySQL server if it is not already running.

    This keeps `python scripts/run_dev.py` a single-command launch on this machine.
    If no bundled mysqld is found, we assume an external MySQL is already up.
    """
    conda_bin = os.path.expanduser("~/Software/anaconda3/bin")
    mysqld = os.path.join(conda_bin, "mysqld")
    mysqladmin = os.path.join(conda_bin, "mysqladmin")
    if not os.path.exists(mysqld):
        return

    socket_path = "/tmp/voiceta_mysql.sock"
    datadir = ROOT / "data" / "mysql"
    log_path = ROOT / "data" / "mysql.log"
    (ROOT / "data" / "uploads").mkdir(parents=True, exist_ok=True)
    datadir.mkdir(parents=True, exist_ok=True)

    if subprocess.run(
        [mysqladmin, "--socket", socket_path, "-u", "root", "status"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0:
        return  # already running

    if not (datadir / "mysql").exists():
        print("Initializing MySQL data directory (first run)...")
        with open(log_path, "a") as log_file:
            subprocess.run(
                [mysqld, "--initialize-insecure", "--datadir", str(datadir),
                 "--socket", socket_path, "--innodb-use-native-aio=0"],
                stdout=log_file, stderr=subprocess.STDOUT, check=False,
            )

    print("Starting MySQL server...")
    subprocess.Popen(
        [mysqld, "--datadir", str(datadir), "--socket", socket_path,
         "--port", "3306", "--bind-address", "127.0.0.1",
         "--innodb-use-native-aio=0", "--log-error", str(log_path),
         "--pid-file", str(datadir / "mysqld.pid")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(60):
        if subprocess.run(
            [mysqladmin, "--socket", socket_path, "-u", "root", "status"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0:
            break
        time.sleep(1)

    mysql = os.path.join(conda_bin, "mysql")
    try:
        subprocess.run(
            [mysql, "--socket", socket_path, "-u", "root", "-e", MYSQL_SECURE_SQL],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:
        pass


def _free_port(port: int) -> None:
    """Kill any process already listening on the given TCP port (best effort)."""
    try:
        out = subprocess.run(
            ["ss", "-ltnp", "-H", f"sport = :{port}"],
            capture_output=True, text=True,
        ).stdout
        for line in out.splitlines():
            match = re.search(r"pid=(\d+)", line)
            if match:
                subprocess.run(["kill", match.group(1)], check=False)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Voice TA backend and frontend.")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    _ensure_mysql()
    _free_port(args.backend_port)
    _free_port(args.frontend_port)

    if not args.skip_install and not (FRONTEND_DIR / "node_modules").exists():
        print("frontend/node_modules not found. Running npm install first...")
        install = subprocess.run(["npm", "install"], cwd=FRONTEND_DIR)
        if install.returncode != 0:
            return install.returncode

    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = f"http://127.0.0.1:{args.backend_port}"

    backend_cmd = (
        f"{_conda_env_python()} -m uvicorn backend.app.main:app "
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
