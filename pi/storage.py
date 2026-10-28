"""SQLite 로그 저장과 CSV 내보내기.

CSV 형식(ms, hour, lux, level)은 tools/metrics.py가 그대로 읽는 형식이다.

1초마다 commit하면 SD카드에 쓰기가 너무 많아서, 기록을 메모리에 모았다가
config.LOG_COMMIT_S마다 한 번에 저장하고, config.LOG_KEEP_DAYS보다 오래된 기록은 지운다.
"""
import csv
import io
import os
import sqlite3
import threading
import time

from pi import config

DAY_S = 24 * 3600


class LogStore:
    def __init__(self, path: str, commit_s: float = config.LOG_COMMIT_S,
                 keep_days: float = config.LOG_KEEP_DAYS) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()   # 제어 루프 스레드와 웹 요청이 동시에 쓰지 않게
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS log ("
            " ts REAL, vtime TEXT, hour REAL, lux REAL, target REAL,"
            " level INTEGER, mode TEXT, event TEXT)")
        self.conn.commit()
        self.commit_s, self.keep_days = commit_s, keep_days
        self.pending = []              # 아직 저장하지 않은 기록
        self.last_commit = time.monotonic()
        self.last_prune = 0.0          # 시작할 때 한 번 정리
        with self.lock:
            self._flush()

    def add(self, vtime: str, hour: float, lux: float, target, level: int,
            mode: str, event: str = "") -> None:
        with self.lock:
            self.pending.append((time.time(), vtime, hour, lux, target, level, mode, event))
            if event or time.monotonic() - self.last_commit >= self.commit_s:
                self._flush()

    def _flush(self) -> None:
        """모아 둔 기록을 한 번에 저장하고, 하루에 한 번 오래된 기록을 지운다 (lock 안에서 호출)."""
        if self.pending:
            self.conn.executemany("INSERT INTO log VALUES (?,?,?,?,?,?,?,?)", self.pending)
            self.pending.clear()
        now = time.time()
        if self.keep_days > 0 and now - self.last_prune >= DAY_S:
            self.conn.execute("DELETE FROM log WHERE ts < ?", (now - self.keep_days * DAY_S,))
            self.last_prune = now
        self.conn.commit()
        self.last_commit = time.monotonic()

    def flush(self) -> None:
        with self.lock:
            self._flush()

    def close(self) -> None:
        """남은 기록을 저장하고 닫는다. 프로그램을 끌 때 부른다."""
        with self.lock:
            self._flush()
            self.conn.close()

    def export_csv(self) -> str:
        """metrics.py용 CSV 문자열. ms는 첫 기록부터 지난 시간(밀리초)."""
        with self.lock:
            self._flush()
            rows = self.conn.execute("SELECT ts, hour, lux, level FROM log ORDER BY ts").fetchall()
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["ms", "hour", "lux", "level"])
        t0 = rows[0][0] if rows else 0
        for ts, hour, lux, level in rows:
            w.writerow([int((ts - t0) * 1000), int(hour), lux, level])
        return out.getvalue()

    def clear(self) -> None:
        with self.lock:
            self.pending.clear()
            self.conn.execute("DELETE FROM log")
            self.conn.commit()
