"""firmware/sketches/capstone_main/params.h 를 읽어 파이썬에서 같은 값을 쓰게 한다.
펌웨어와 학습 데이터가 어긋나지 않도록 값을 한 곳(params.h)에서만 관리한다.
"""
import re

import numpy as np

PARAMS_PATH = "firmware/sketches/capstone_main/params.h"


def _array(txt: str, name: str):
    m = re.search(name + r"\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", txt)
    if not m:
        raise ValueError(f"params.h 에서 {name} 배열을 찾지 못함")
    items = [s.strip().rstrip("f") for s in m.group(1).split(",") if s.strip()]
    return [float(x) for x in items]


def load_params(path: str = PARAMS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    p = {m.group(1): float(m.group(2)) for m in re.finditer(r"#define\s+(\w+)\s+([0-9.]+)f?\b", txt)}
    p["LUT_T"] = [np.float32(x) for x in _array(txt, "LUT_T")]
    p["LUT_PWM"] = [int(x) for x in _array(txt, "LUT_PWM")]
    p["LUT_TAP"] = [int(x) for x in _array(txt, "LUT_TAP")]
    p["NUM_LEVELS"] = int(p["NUM_LEVELS"])
    assert len(p["LUT_T"]) == p["NUM_LEVELS"], "LUT_T 길이가 NUM_LEVELS 와 다름"
    return p


def target_lux(p: dict, hour: int) -> np.float32:
    if hour >= int(p["SLEEP_START_HOUR"]) or hour < int(p["SLEEP_END_HOUR"]):
        return np.float32(p["TARGET_SLEEP_LUX"])
    if hour < int(p["WAKE_END_HOUR"]):
        return np.float32(p["TARGET_WAKE_LUX"])
    return np.float32(p["TARGET_DAY_LUX"])


def decide_rule(p: dict, lux: float, hour: int, cur: int) -> int:
    """decision.h 의 decide_rule() 과 같은 계산 (float32 로 맞춤)."""
    n = p["NUM_LEVELS"]
    T = p["LUT_T"]
    cur = max(0, min(n - 1, int(cur)))
    lux = np.float32(lux)
    incident = lux / T[cur]
    denom = incident if incident > np.float32(1.0) else np.float32(1.0)
    t_need = target_lux(p, hour) / denom
    best, best_err = 0, abs(T[0] - t_need)
    for i in range(1, n):
        err = abs(T[i] - t_need)
        if err < best_err:
            best, best_err = i, err
    cur_err = abs(T[cur] - t_need)
    if cur_err <= best_err + np.float32(p["DEADBAND_T"]):
        return cur
    return best
