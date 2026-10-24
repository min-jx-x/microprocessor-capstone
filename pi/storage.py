"""SQLite 로그 저장과 CSV 내보내기.

CSV 형식(ms, hour, lux, level)은 tools/metrics.py가 그대로 읽는 형식이다.
"""
import csv
import io
import os
import sqlite3
import threading
import time


class LogStore:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()   # 제어 루프 스레드와 웹 요청이 동시에 쓰지 않게
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS log ("
            " ts REAL, vtime TEXT, hour REAL, lux REAL, target REAL,"
            " level INTEGER, mode TEXT, event TEXT)")
        self.conn.commit()

    def add(self, vtime: str, hour: float, lux: float, target, level: int,
            mode: str, event: str = "") -> None:
        with self.lock:
            self.conn.execute("INSERT INTO log VALUES (?,?,?,?,?,?,?,?)",
                              (time.time(), vtime, hour, lux, target, level, mode, event))
            self.conn.commit()

    def export_csv(self) -> str:
        """metrics.py용 CSV 문자열. ms는 첫 기록부터 지난 시간(밀리초)."""
        with self.lock:
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
            self.conn.execute("DELETE FROM log")
            self.conn.commit()
