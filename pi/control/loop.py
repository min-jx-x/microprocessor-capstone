"""제어 루프: 측정 → 판단 → 안정화 → 단계 적용 → 기록.

웹(app.py)과 별도 스레드에서 1초마다 step()을 돈다.
웹은 snapshot()으로 현재 상태를 읽고, set_manual()/set_mode()/set_wake_time()으로 명령만 보낸다.
장치(센서·릴레이)는 바깥에서 넣어 주므로, 같은 코드가 노트북(가짜 장치)과 Pi(실제 장치)에서 돈다.
"""
import os
import statistics
import threading
import time
from collections import deque
from typing import Optional

from pi import config
from pi.control.decide import RulePolicy, load_lut, parse_hhmm
from pi.control.preference import PreferenceStore

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
    def __init__(self, sensor, relays, clock, outdoor=None, store=None, pref=None) -> None:
        self.sensor = sensor
        self.clock = clock
        self.outdoor = outdoor          # 시뮬레이션일 때만 있음 (화면에 바깥 빛 표시용)
        self.store = store
        self.driver = LevelDriver(relays)
        self.stab = Stabilizer()
        self.lut = load_lut()
        # 판단 방식: 규칙은 항상, AI는 모델 파일(config.AI_MODEL_PATH)이 있을 때만
        self.policies = {"rule": RulePolicy(self.lut)}
        self.ai_meta = None
        if os.path.exists(config.AI_MODEL_PATH):
            from pi.ai.policy import AIPolicy
            ai = AIPolicy(self.lut)
            self.policies["ai"] = ai
            self.ai_meta = dict(ai.meta, stale=ai.stale)
        # 실측 lut.json을 넣고 아직 다시 학습하지 않았으면(stale) 규칙으로 시작한다. 웹에서 AI로 바꿀 수는 있음
        self.brain = "ai" if self.ai_meta is not None and not self.ai_meta["stale"] else "rule"

        self.lock = threading.Lock()    # 웹 요청 스레드와 제어 스레드가 상태를 같이 만지므로
        self.mode = "auto"              # auto: 규칙이 단계 결정 / manual: 사용자가 고른 단계 유지
        self.wake_time = config.DEFAULT_WAKE_TIME
        self.level = 0
        self.lux: Optional[float] = None
        self.info = {}
        self.switches = 0               # 단계 전환 횟수 (오탐률 확인용)
        self.sensor_fail = 0            # 센서 연속 실패 횟수
        # 개인 선호 보정. 넘겨주지 않으면 파일에 저장하지 않는 임시 저장소(테스트·시뮬레이션)
        self.pref = pref if pref is not None else PreferenceStore(path=None)
        self._pref_pending = None       # 수동 조작 후 선호 조도를 재는 중이면 {"level", "samples"}
        self.last_learn = None          # 화면 표시용: 마지막으로 배운 내용
        self.learn_enabled = True       # 수동 조작을 선호로 배울지 (웹에서 끄고 켬)
        self.history = deque(maxlen=config.HISTORY_POINTS)

        self.driver.apply(0)            # 시작은 항상 0단계(모두 꺼짐)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ 루프
    def step(self) -> None:
        try:
            lux = self.sensor.read_lux()
        except Exception as e:          # I2C 선 빠짐 등. 루프는 멈추지 않는다
            print("[loop] 센서 오류:", e)
            lux = None
        if lux is None:
            self._on_sensor_fail()
            return
        with self.lock:
            self.sensor_fail = 0
        hour = self.clock.hour()
        vtime = self.clock.now().strftime("%H:%M:%S")
        event = ""
        with self.lock:
            wake = parse_hhmm(self.wake_time)
            # 모든 판단 방식에 매번 값을 넣어 준다 (AI는 최근 4회 기록이 필요하므로,
            # 도중에 바꿔도 바로 동작하게). 실제 적용은 선택된 방식의 답만 쓴다.
            scale = self.pref.scale()
            answers = {k: p.decide(lux, hour, self.level, wake, scale) for k, p in self.policies.items()}
            cand, info = answers[self.brain]
            if self.mode == "auto":
                now = time.monotonic()
                nxt = self.stab.propose(cand, self.level, now)
                if nxt is not None:
                    self.driver.apply(nxt)
                    self.stab.mark_switched(now)
                    event = f"{self.brain} {self.level}->{nxt}"
                    self.level = nxt
                    self.switches += 1
            learned = self._collect_preference(lux, info)
            if learned:
                event = learned
            self.lux = lux
            self.info = dict(info, candidate=cand,
                             answers={k: v[0] for k, v in answers.items()})
            point = {"t": vtime, "hour": round(hour, 3), "lux": lux,
                     "target": info["target"], "level": self.level}
            if self.outdoor is not None:
                point["outdoor"] = round(self.outdoor.last, 1)
            self.history.append(point)
            mode = self.mode if self.mode == "manual" else self.brain
            level = self.level
        if self.store is not None:
            self.store.add(vtime, hour, lux, info["target"], level, mode, event)

    def _collect_preference(self, lux: float, info: dict):
        """수동 조작 뒤 PREF_SETTLE회 측정한 조도의 중앙값을 선호 조도로 보고 학습한다 (lock 안에서 호출)."""
        p = self._pref_pending
        if p is None or self.mode != "manual" or self.level != p["level"]:
            return None
        p["samples"].append(lux)
        if len(p["samples"]) < config.PREF_SETTLE:
            return None
        self._pref_pending = None
        preferred = statistics.median(p["samples"])
        new = self.pref.learn(info["period"], info.get("base_target"), preferred)
        if new is None:                 # 저녁·취침 등 보정 대상이 아닌 시간대
            return None
        self.last_learn = {"period_name": info["period_name"], "preferred": round(preferred),
                           "offset": new, "vtime": self.clock.now().strftime("%H:%M")}
        return f"pref {info['period']} {new:+.3f} ({preferred:.0f}lux)"

    def _on_sensor_fail(self) -> None:
        """한두 번은 현재 단계를 유지하고, 연속 SENSOR_FAIL_LIMIT번이면 0단계(전원 모두 끔)로 둔다."""
        with self.lock:
            self.sensor_fail += 1
            if self.sensor_fail < config.SENSOR_FAIL_LIMIT or self.level == config.SAFE_LEVEL:
                return
            prev = self.level
            self.driver.apply(config.SAFE_LEVEL)
            self.level = config.SAFE_LEVEL
            self.switches += 1
            self.stab.reset()
        print(f"[loop] 센서 {config.SENSOR_FAIL_LIMIT}회 연속 실패 → {config.SAFE_LEVEL}단계로 전환")
        if self.store is not None:
            self.store.add(self.clock.now().strftime("%H:%M:%S"), self.clock.hour(), -1, None,
                           config.SAFE_LEVEL, self.mode, f"sensor_fail {prev}->{config.SAFE_LEVEL}")

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
    def set_manual(self, level: int, learn: bool = True) -> None:
        """사용자가 단계를 직접 고름 → 수동 모드로 바뀌고 즉시 적용.
        이 기록(event='manual')은 나중에 개인 선호 보정의 학습 신호로 쓴다.
        learn=False: 이번 조작은 선호 학습에 쓰지 않는다 (예: 관람객 음성 명령)."""
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
            if self.learn_enabled and learn:    # 다음 측정부터 선호 조도 수집
                self._pref_pending = {"level": level, "samples": []}
            elif not learn:
                self._pref_pending = None       # 이전 조작의 측정도 버린다 (섞이지 않게)
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
            if mode == "auto":
                self._pref_pending = None   # 측정이 끝나기 전에 자동으로 돌아가면 학습하지 않음

    def set_brain(self, name: str) -> None:
        if name not in self.policies:
            raise ValueError("사용할 수 없는 판단 방식")
        with self.lock:
            self.brain = name
            self.stab.reset()

    def set_profile(self, name: str) -> None:
        self.pref.select(name)          # 없는 이름이면 새 사용자
        with self.lock:
            self._pref_pending = None
            self.last_learn = None
            self.stab.reset()

    def set_learning(self, enabled: bool) -> None:
        """수동 조작 학습 켜기/끄기. 끄면 단계를 직접 바꿔도 목표가 바뀌지 않는다 (시연·시험용)."""
        with self.lock:
            self.learn_enabled = bool(enabled)
            if not self.learn_enabled:
                self._pref_pending = None

    def reset_preference(self) -> None:
        self.pref.reset()
        with self.lock:
            self.last_learn = None

    def set_wake_time(self, text: str) -> None:
        parse_hhmm(text)                # 형식이 틀리면 여기서 예외
        with self.lock:
            self.wake_time = text

    def _pref_view(self) -> dict:
        """화면 표시용: 사용자, 시간대별 [기본 목표, 내 목표], 학습 횟수, 마지막 학습 (lock 안에서 호출)."""
        v = self.pref.snapshot()
        base = {"morning": config.TARGET_WAKE_LUX, "day": config.TARGET_DAY_LUX}
        v["targets"] = {g: [b, round(b * (1 + v["offset"][g]))] for g, b in base.items()}
        v["last"] = self.last_learn
        v["measuring"] = self._pref_pending is not None
        v["learn"] = self.learn_enabled
        return v

    def explain(self) -> dict:
        """웹 'AI 설명' 페이지용: 지금 판단의 근거 (규칙 계산, AI 트리 경로, 안정화 진행)."""
        with self.lock:
            info = dict(self.info)
            ai = self.policies.get("ai")
            st = self.stab
            wait = st.min_interval_s - (time.monotonic() - st.last_switch)
            rule = None
            if info.get("t_need") is not None:
                t = info["t_need"]
                rule = {"t_need": t, "deadband": config.DEADBAND_T,
                        "levels": [{"level": i, "t": round(x, 3), "err": round(abs(x - t), 3)}
                                   for i, x in enumerate(self.lut)]}
            return {
                "mode": self.mode,
                "brain": self.brain,
                "level": self.level,
                "lux": self.lux,
                "period_name": info.get("period_name"),
                "target": info.get("target"),
                "answers": info.get("answers", {}),
                "candidate": info.get("candidate"),
                "rule": rule,
                "ai": ai.explain() if ai is not None else None,
                "stab": {"direction": st.direction, "count": st.count, "need": st.stable_count,
                         "wait_s": round(max(0.0, wait), 1)},
                "ai_meta": self.ai_meta,
            }

    def snapshot(self) -> dict:
        with self.lock:
            a, b = config.LEVELS[self.level]
            return {
                "vtime": self.clock.now().strftime("%H:%M:%S"),
                "speed": getattr(self.clock, "speed", 1),
                "mode": self.mode,
                "brain": self.brain,
                "brains": list(self.policies),
                "ai_meta": self.ai_meta,
                "lut_source": config.LUT_SOURCE,
                "pref": self._pref_view(),
                "sensor_fail": self.sensor_fail,
                "sensor_fail_limit": config.SENSOR_FAIL_LIMIT,
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
