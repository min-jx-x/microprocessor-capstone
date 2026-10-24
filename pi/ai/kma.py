"""기상청 ASOS 시간별 일사량 CSV → 하루 밝기 곡선(24칸).

기상자료개방포털에서 받은 파일(data/OBS_ASOS*.csv)을 읽어
(지점, 날짜)마다 0~23시 일사량을 모으고, 전체 최댓값으로 나눠 0~1로 만든다.
곡선의 '모양'만 쓰고 크기는 시연 조명 수준(peak_lux)으로 다시 맞춘다.
"""
import csv
import glob
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


def _read_rows(path: str) -> List[List[str]]:
    for enc in ("cp949", "utf-8-sig", "utf-8"):     # 기상청 파일은 보통 cp949
        try:
            with open(path, encoding=enc) as f:
                return list(csv.reader(f))[1:]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없음: {path}")


def load_profiles(pattern: str = "data/OBS_ASOS*.csv") -> Dict[Tuple[str, str], List[float]]:
    """{(지점명, 날짜): [0시 ... 23시 상대 밝기]}. 파일이 없으면 빈 dict."""
    days: Dict[Tuple[str, str], List[float]] = defaultdict(lambda: [0.0] * 24)
    for path in glob.glob(pattern):
        for row in _read_rows(path):
            if len(row) < 4 or not row[3].strip():
                continue
            name, stamp, mj = row[1], row[2], float(row[3])
            date, hm = stamp.split(" ")
            days[(name, date)][int(hm.split(":")[0])] = mj
    if not days:
        return {}
    peak = max(max(v) for v in days.values()) or 1.0
    return {k: [x / peak for x in v] for k, v in days.items()}


def pick(profiles: Dict, index: int) -> Optional[List[float]]:
    if not profiles:
        return None
    keys = sorted(profiles)
    return profiles[keys[index % len(keys)]]
