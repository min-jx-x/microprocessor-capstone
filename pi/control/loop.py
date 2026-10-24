"""제어 루프: 측정 → 판단 → 안정화 → 단계 적용 → 기록.

웹(app.py)과 별도 스레드에서 1초마다 step()을 돈다.
웹은 snapshot()으로 현재 상태를 읽고, set_manual()/set_mode()/set_wake_time()으로 명령만 보낸다.
장치(센서·릴레이)는 바깥에서 넣어 주므로, 같은 코드가 노트북(가짜 장치)과 Pi(실제 장치)에서 돈다.
"""
import threading
import time
from collections import deque
from typing import Optional

from pi import config
from pi.control.decide import decide_rule, load_lut, parse_hhmm

# 대현이 만든 정식 모듈이 있으면 그것을, 없으면 임시 버전을 쓴다.
try:
    from pi.control.levels import LevelDriver          # type: ignore
except ImportError:
    from pi.control.placeholders import LevelDriver
try:
    from pi.control.stabilizer import Stabilizer       # type: ignore
except ImportError:
    from pi.control.placeholders import Stabilizer


class Controller:
    def __init__(self, sensor, relays, clock, outdoor=None, store=None) -> None:
        self.sensor = sensor
        self.clock = clock
        self.outdoor = outdoor          # 시뮬레이션일 때만 있음 (화면에 바깥 빛 표시용)
        self.store = store
        self.driver = LevelDriver(relays)
        self.stab = Stabilizer()
        self.lut = load_lut()

        self.lock = threading.Lock()    # 웹 요청 스레드와 제어 스레드가 상태를 같이 만지므로
        self.mode = "auto"              # auto: 규칙이 단계 결정 / manual: 사용자가 고른 단계 유지
        self.wake_time = config.DEFAULT_WAKE_TIME
        self.level = 0
        self.lux: Optional[float] = None
        self.info = {}
        self.switches = 0               # 단계 전환 횟수 (오탐률 확인용)
        self.history = deque(maxlen=config.HISTORY_POINTS)

        self.driver.apply(0)            # 시작은 항상 0단계(모두 꺼짐)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ 루프
    def step(self) -> None:
        lux = self.sensor.read_lux()
        if lux is None:                 # 센서 오류: 이번 회차는 건너뛰고 현재 단계 유지
            return
        hour = self.clock.hour()
        vtime = self.clock.now().strftime("%H:%M:%S")
        event = ""
        with self.lock:
            cand, info = decide_rule(lux, hour, self.level, self.lut,
                                     parse_hhmm(self.wake_time))
            if self.mode == "auto":
                now = time.monotonic()
                nxt = self.stab.propose(cand, self.level, now)
                if nxt is not None:
                    self.driver.apply(nxt)
                    self.stab.mark_switched(now)
                    event = f"auto {self.level}->{nxt}"
                    self.level = nxt
                    self.switches += 1
            self.lux, self.info = lux, dict(info, candidate=cand)
            point = {"t": vtime, "hour": round(hour, 3), "lux": lux,
                     "target": info["target"], "level": self.level}
            if self.outdoor is not None:
                point["outdoor"] = round(self.outdoor.last, 1)
            self.history.append(point)
            mode, level = self.mode, self.level
        if self.store is not None:
            self.store.add(vtime, hour, lux, info["target"], level, mode, event)

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self.step()
            except Exception as e:      # 한 번 실패해도 루프는 계속 돈다
                print("[loop] step 오류:", e)
            self._stop.wait(max(0.0, config.SAMPLE_PERIOD_S - (time.monotonic() - t0)))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.driver.apply(0)

    # ------------------------------------------------------------------ 웹 명령
    def set_manual(self, level: int) -> None:
        """사용자가 단계를 직접 고름 → 수동 모드로 바뀌고 즉시 적용.
        이 기록(event='manual')은 나중에 개인 선호 보정의 학습 신호로 쓴다."""
        if not 0 <= level < config.NUM_LEVELS:
            raise ValueError("단계 범위 밖")
        with self.lock:
            prev = self.level
            self.mode = "manual"
            self.driver.apply(level)
            self.level = level
            if prev != level:
                self.switches += 1
            self.stab.reset()
            lux, hour = self.lux, self.clock.hour()
            target = self.info.get("target")
        if self.store is not None and lux is not None:
            self.store.add(self.clock.now().strftime("%H:%M:%S"), hour, lux, target,
                           level, "manual", f"manual {prev}->{level}")

    def set_mode(self, mode: str) -> None:
        if mode not in ("auto", "manual"):
            raise ValueError("mode는 auto 또는 manual")
        with self.lock:
            self.mode = mode
            self.stab.reset()           # 자동으로 돌아올 때 이전 연속 횟수는 버린다

    def set_wake_time(self, text: str) -> None:
        parse_hhmm(text)                # 형식이 틀리면 여기서 예외
        with self.lock:
            self.wake_time = text

    def snapshot(self) -> dict:
        with self.lock:
            a, b = config.LEVELS[self.level]
            return {
                "vtime": self.clock.now().strftime("%H:%M:%S"),
                "speed": getattr(self.clock, "speed", 1),
                "mode": self.mode,
                "level": self.level,
                "films": {"A": a, "B": b},
                "lux": self.lux,
                "info": self.info,
                "wake_time": self.wake_time,
                "switches": self.switches,
                "num_levels": config.NUM_LEVELS,
                "sim": self.outdoor is not None,
                "history": list(self.history),
            }
