"""개인 선호 보정 (사용자별 목표 조도 학습).

AI(결정트리)는 '목표에 어떻게 빨리 맞출지'를 정하고, 이 파일은 '목표를 얼마로 할지'를 사람마다 맞춘다.

학습 신호: 사용자가 웹에서 단계를 직접 바꾼 뒤 안정된 실내 조도 = 그 사람이 원하는 밝기
학습 방식: 시간대(아침·주간)마다 목표 대비 비율(보정값)을 이동평균으로 조금씩 옮긴다
  보정값 ← (1 - α) × 보정값 + α × (선호 조도 / 기본 목표 - 1)
  α = PREF_ALPHA(0.3): 한 번 조작으로 차이의 30%만 반영 → 실수 한 번에 크게 흔들리지 않음
  보정값은 ±PREF_MAX(30%) 안으로 제한
미리 학습할 데이터는 필요 없다. 쓰면서 배우는 온라인 학습이다.
사용자별 프로필로 저장하고(pi/data/preferences.json), Pi를 껐다 켜도 유지된다.
"""
import json
import os
import threading
from typing import Dict, Optional

from pi import config

# 보정하는 시간대 묶음. 기상 준비(ramp)는 아침 보정을 같이 쓴다. 저녁·취침은 목표가 없어 보정 안 함
GROUP = {"ramp": "morning", "morning": "morning", "day": "day"}
GROUP_NAMES = {"morning": "아침", "day": "주간"}
DEFAULT_PROFILE = "기본"


def _empty() -> dict:
    return {"offset": {g: 0.0 for g in GROUP_NAMES}, "count": {g: 0 for g in GROUP_NAMES}}


class PreferenceStore:
    def __init__(self, path: Optional[str] = config.PREF_PATH, alpha: float = config.PREF_ALPHA,
                 max_offset: float = config.PREF_MAX) -> None:
        """path=None이면 파일에 저장하지 않는다 (시뮬레이션·테스트용)."""
        self.path, self.alpha, self.max_offset = path, alpha, max_offset
        self.lock = threading.Lock()
        self.active = DEFAULT_PROFILE
        self.profiles: Dict[str, dict] = {DEFAULT_PROFILE: _empty()}
        self._load()

    # ---------------------------------------------------------------- 파일
    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            for name, p in d.get("profiles", {}).items():
                prof = _empty()
                prof["offset"].update({k: float(v) for k, v in p.get("offset", {}).items() if k in GROUP_NAMES})
                prof["count"].update({k: int(v) for k, v in p.get("count", {}).items() if k in GROUP_NAMES})
                self.profiles[name] = prof
            if d.get("active") in self.profiles:
                self.active = d["active"]
        except (OSError, ValueError, TypeError) as e:
            print(f"[pref] {self.path} 읽기 실패, 새로 시작: {e}")

    def _save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"active": self.active, "profiles": self.profiles}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)      # 쓰는 도중 전원이 꺼져도 파일이 깨지지 않게

    # ---------------------------------------------------------------- 사용
    def scale(self) -> Dict[str, float]:
        """현재 사용자의 시간대별 목표 배율. {"ramp": 1.1, "morning": 1.1, "day": 0.9}"""
        with self.lock:
            off = self.profiles[self.active]["offset"]
            return {period: 1.0 + off[g] for period, g in GROUP.items()}

    def learn(self, period: str, base_target: float, preferred_lux: float) -> Optional[float]:
        """수동 조작 한 번을 반영. 반영한 새 보정값(비율)을 돌려주고, 보정 대상이 아니면 None."""
        g = GROUP.get(period)
        if g is None or base_target is None or base_target <= 0 or preferred_lux is None:
            return None
        wanted = preferred_lux / base_target - 1.0
        wanted = max(-self.max_offset, min(self.max_offset, wanted))
        with self.lock:
            p = self.profiles[self.active]
            new = (1 - self.alpha) * p["offset"][g] + self.alpha * wanted
            p["offset"][g] = round(max(-self.max_offset, min(self.max_offset, new)), 4)
            p["count"][g] += 1
            self._save()
            return p["offset"][g]

    def select(self, name: str) -> None:
        """사용자 선택. 없는 이름이면 새 프로필을 만든다."""
        name = name.strip()
        if not name or len(name) > 20:
            raise ValueError("이름은 1~20자")
        with self.lock:
            self.profiles.setdefault(name, _empty())
            self.active = name
            self._save()

    def reset(self) -> None:
        """현재 사용자의 보정을 0으로."""
        with self.lock:
            self.profiles[self.active] = _empty()
            self._save()

    def snapshot(self) -> dict:
        with self.lock:
            p = self.profiles[self.active]
            return {"active": self.active, "profiles": sorted(self.profiles),
                    "offset": dict(p["offset"]), "count": dict(p["count"])}
