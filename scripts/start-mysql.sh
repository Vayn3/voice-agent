#!/usr/bin/env bash
# Start the local MySQL 8.4 server (Anaconda build) used by Voice-TA.
# Run this if MySQL is not already running (e.g. after a reboot), then run:
#   python scripts/run_dev.py
set -u
CONDA_BIN="$HOME/Software/anaconda3/bin"
MYSQLD="$CONDA_BIN/mysqld"
MYSQLADMIN="$CONDA_BIN/mysqladmin"
MYSQL="$CONDA_BIN/mysql"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATADIR="$ROOT_DIR/data/mysql"
SOCKET=/tmp/voiceta_mysql.sock
LOG="$ROOT_DIR/data/mysql.log"

if [ ! -x "$MYSQLD" ]; then
  echo "mysqld not found at $MYSQLD; please install MySQL or adjust CONDA_BIN." >&2
  exit 1
fi

mkdir -p "$DATADIR" "$ROOT_DIR/data/uploads"

if "$MYSQLADMIN" --socket="$SOCKET" -u root status >/dev/null 2>&1; then
  echo "MySQL is already running."
  exit 0
fi

if [ ! -d "$DATADIR/mysql" ]; then
  echo "Initializing MySQL data directory (first run)..."
  "$MYSQLD" --initialize-insecure --datadir="$DATADIR" --socket="$SOCKET" --innodb-use-native-aio=0 >> "$LOG" 2>&1
fi

echo "Starting MySQL server..."
setsid "$MYSQLD" --datadir="$DATADIR" --socket="$SOCKET" --port=3306 --bind-address=127.0.0.1 --innodb-use-native-aio=0 --log-error="$LOG" --pid-file="$DATADIR/mysqld.pid" >/dev/null 2>&1 < /dev/null &

for i in $(seq 1 60); do
  "$MYSQLADMIN" --socket="$SOCKET" -u root status >/dev/null 2>&1 && break
  sleep 1
done

# First-time secure: set root password and create database (idempotent).
if "$MYSQL" --socket="$SOCKET" -u root -e "SELECT 1" >/dev/null 2>&1; then
  "$MYSQL" --socket="$SOCKET" -u root -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'root'; CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'root'; CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'root'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION; CREATE DATABASE IF NOT EXISTS voiceTA CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; FLUSH PRIVILEGES;" 2>/dev/null
fi

echo "MySQL is ready on 127.0.0.1:3306 (user: root / password: root)."
