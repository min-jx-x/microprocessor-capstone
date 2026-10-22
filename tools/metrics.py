"""docs 사양에 맞춘 하드웨어/알고리즘 정량지표 계산 스크립트.

정량지표 항목:
    1. 정확도 (Accuracy): 도달 조도가 해당 시간대(또는 단계) 목표 조도 ±tolerance% 범위 내에 들어온 비율
       - 추가: 평균 절대 오차율 (MAPE, %)
    2. 오탐률 (False Positive Rate): 목표 조도를 이미 만족하고 있는 안정 상태에서 불필요하게 단계 전환이 일어난 비율
    3. 지연시간 (Latency): lux 급변 감지 시점부터 액추에이터(level) 전환 완료까지 걸린 시간 (ms)

입력 CSV 컬럼:
    ms, hour, lux, level

사용법:
    python tools/metrics.py                                  # data/sample_log.csv 분석
    python tools/metrics.py data/sample_log.csv              # 특정 파일 분석
    python tools/metrics.py data/sample_log.csv --incident   # 외부 일사 데이터 -> 투과율(T) 적용 실내 조도로 환산 평가
    python tools/metrics.py data/sample_log.csv --sensor     # BH1750 센서 실측값 직접 평가
    python tools/metrics.py --tolerance 0.15                 # 허용 오차 ±15% 지정
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

# server/ai/params_loader 불러오기
AI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "ai"))
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

try:
    from params_loader import load_params, target_lux as get_target_lux
except ImportError:
    load_params = None
    get_target_lux = None


def get_default_params():
    """params.h 로드 실패 시 적용할 기본 규격 (4단계 기준)."""
    return {
        "NUM_LEVELS": 4,
        "TARGET_SLEEP_LUX": 5.0,
        "TARGET_WAKE_LUX": 200.0,
        "TARGET_DAY_LUX": 500.0,
        "SLEEP_START_HOUR": 22,
        "SLEEP_END_HOUR": 6,
        "WAKE_END_HOUR": 9,
        "DEADBAND_T": 0.05,
        "LUT_T": [0.07, 0.15, 0.30, 1.00],
    }


def resolve_target_lux(df: pd.DataFrame, params: dict, target_lux_map: dict = None) -> pd.Series:
    """각 행의 목표 조도(target_lux)를 결정한다.
    
    1. 사용자가 명시한 target_lux_map 이 있으면 우선 적용
    2. CSV에 hour 컬럼이 있고 시간대 구분이 유효하면 params.h 기반 시간대별 목표 적용
    3. 그 외의 경우 레거시 3단계 또는 4단계 기본 레벨 매핑 적용
    """
    if target_lux_map is not None:
        return df["level"].map(target_lux_map)

    # hour 컬럼 기반 시간대별 목표 판별
    if "hour" in df.columns and get_target_lux is not None and params is not None:
        hours = df["hour"].dropna().astype(int)
        # 시간대가 다양하게 분포되어 있으면 시간대별 목표 적용
        return hours.apply(lambda h: float(get_target_lux(params, h)))

    # 레벨 기반 fallback (4단계: 0->5, 1->200, 2->500, 3->1000 / 3단계: 1->100, 2->250, 3->500)
    num_levels = params.get("NUM_LEVELS", 4) if params else 4
    if num_levels == 4 and df["level"].min() == 0:
        fallback_map = {0: 5.0, 1: 200.0, 2: 500.0, 3: 1000.0}
    else:
        fallback_map = {1: 100.0, 2: 250.0, 3: 500.0}
    return df["level"].map(fallback_map)


def calculate_metrics(
    csv_path: str,
    target_lux_map: dict = None,
    tolerance: float = 0.10,
    is_incident: bool = None,
    lux_step_threshold: float = 100.0,
    max_latency_window_ms: float = 15000.0,
    verbose: bool = True,
):
    """로그 CSV 분석 및 정량지표 자동 계산.

    :param csv_path: 로그 CSV 경로
    :param target_lux_map: level별 목표 조도 매핑 dict (None일 경우 params.h 시간대별 목표 적용)
    :param tolerance: 허용 오차 비율 (0.10 -> ±10%)
    :param is_incident: 외부 입사광 데이터 여부 (True 시 LUT_T 투과율 곱해 실내 조도로 환산 평가)
    :param lux_step_threshold: 급변 감지 lux 변화량 임계값 (기본 100 lux)
    :param max_latency_window_ms: 급변 후 유효 반응 대기 최대 시간 (ms)
    :param verbose: 상세 결과 출력 여부
    """
    if not os.path.exists(csv_path):
        print(f"Error: 파일을 찾을 수 없습니다 -> {csv_path}")
        return None

    # 파라미터 로드
    params = None
    if load_params is not None:
        try:
            params = load_params()
        except Exception:
            params = get_default_params()
    else:
        params = get_default_params()

    df = pd.read_csv(csv_path)
    if df.empty:
        print("Error: CSV 데이터가 비어 있습니다.")
        return None

    # 입사광(incident) 여부 자동 판별 (지정되지 않은 경우)
    # 일반적인 실내 조도는 수백 lux 수준이지만, 기상청 일사량 환산값 등 야외 직사광은 수만 lux(최대 100,000 lux)에 달함
    if is_incident is None:
        is_incident = bool(df["lux"].max() > 10000.0)

    lut_t = [float(x) for x in params.get("LUT_T", [0.07, 0.15, 0.30, 1.00])]
    num_levels = params.get("NUM_LEVELS", len(lut_t))

    # 평가 조도(eval_lux) 계산
    if is_incident:
        # 외부 입사광 * 현재 블라인드 단계의 투과율 T = 실내 도달 조도
        df["t_val"] = df["level"].apply(
            lambda lv: lut_t[int(lv)] if 0 <= int(lv) < len(lut_t) else 1.0
        )
        df["eval_lux"] = df["lux"] * df["t_val"]
        mode_str = "외부 입사광 (투과율 T 적용 실내 도달 조도로 환산 평가)"
    else:
        df["eval_lux"] = df["lux"].astype(float)
        mode_str = "실내 센서(BH1750) 실측 조도 직접 평가"

    # -------------------------------------------------------------
    # 1. 목표 조도 및 정확도 (Accuracy)
    # -------------------------------------------------------------
    df["target_lux"] = resolve_target_lux(df, params, target_lux_map)
    df["lower_bound"] = df["target_lux"] * (1 - tolerance)
    df["upper_bound"] = df["target_lux"] * (1 + tolerance)

    in_range = (df["eval_lux"] >= df["lower_bound"]) & (df["eval_lux"] <= df["upper_bound"])
    accuracy = (in_range.sum() / len(df)) * 100.0 if len(df) > 0 else 0.0

    # 평균 절대 백분율 오차 (MAPE: Mean Absolute Percentage Error)
    valid_targets = df["target_lux"] > 0
    if valid_targets.any():
        errors = (
            (df.loc[valid_targets, "eval_lux"] - df.loc[valid_targets, "target_lux"]).abs()
            / df.loc[valid_targets, "target_lux"]
        ) * 100.0
        mape = float(errors.mean())
    else:
        mape = 0.0

    # -------------------------------------------------------------
    # 2. 오탐률 (False Positive Rate)
    # 정의: 직전 상태가 목표 lux 오차 범위 내에 있었는데도 불필요하게 단계를 변경한 비율
    # -------------------------------------------------------------
    df["level_changed"] = df["level"].diff().abs() > 0
    df["prev_target"] = df["target_lux"].shift(1)
    df["prev_lux"] = df["eval_lux"].shift(1)
    df["prev_in_range"] = (df["prev_lux"] >= df["prev_target"] * (1 - tolerance)) & (
        df["prev_lux"] <= df["prev_target"] * (1 + tolerance)
    )

    unnecessary_switches = int((df["level_changed"] & df["prev_in_range"]).sum())
    total_decisions = max(len(df) - 1, 1)
    fp_rate = (unnecessary_switches / total_decisions) * 100.0

    # -------------------------------------------------------------
    # 3. 지연시간 (Latency)
    # 정의: lux 급변(변화량 >= lux_step_threshold) 발생 시점 -> 대응 단계 전환 완료까지의 시간 (ms)
    # -------------------------------------------------------------
    latencies = []
    df["lux_diff"] = df["eval_lux"].diff().abs()
    change_points = df[df["lux_diff"] >= lux_step_threshold].index

    for idx in change_points:
        t_start = df.loc[idx, "ms"]
        sub_df = df.loc[idx:]
        level_change_df = sub_df[sub_df["level_changed"]]

        if not level_change_df.empty:
            t_end = level_change_df.iloc[0]["ms"]
            latency = t_end - t_start
            if latency <= max_latency_window_ms:
                latencies.append(latency)

    avg_latency = float(np.mean(latencies)) if latencies else 0.0

    # -------------------------------------------------------------
    # 결과 출력
    # -------------------------------------------------------------
    if verbose:
        print("=" * 60)
        print("                 하드웨어 성능 평가 결과              ")
        print("=" * 60)
        print(f"분석 파일 경로     : {csv_path}")
        print(f"평가 조도 모드     : {mode_str}")
        print(f"총 분석 데이터 건수: {len(df)} 건")
        print(f"허용 오차 범위     : ±{int(tolerance * 100)} %")
        print("-" * 60)
        print(f"1. 정확도 (Accuracy): {accuracy:.2f} %  (목표 lux ±{int(tolerance*100)}% 이내 {in_range.sum()}/{len(df)}건)")
        print(f"   - 평균 오차율    : {mape:.2f} %  (MAPE)")
        print(f"2. 오탐률 (FP Rate) : {fp_rate:.2f} %  (불필요한 단계 전환: {unnecessary_switches}회 / 총 {total_decisions}회)")
        print(f"3. 평균 지연시간    : {avg_latency:.2f} ms (급변 대응 감지: {len(latencies)}회)")
        print("=" * 60)

        # 요약 데이터 행 출력
        print(f"{'ms':^7} | {'hour':^5} | {'입력lux':^9} | {'실내도달lux':^11} | {'단계':^4} | {'목표lux':^8} | {'판정':^6}")
        print("-" * 60)
        for _, r in df.iterrows():
            in_mark = "적합" if r["eval_lux"] >= r["lower_bound"] and r["eval_lux"] <= r["upper_bound"] else "미달/초과"
            print(
                f"{int(r['ms']):>7} | {int(r['hour']):>4}시 | {r['lux']:>8.1f} | {r['eval_lux']:>10.1f} | {int(r['level']):>3} | {r['target_lux']:>7.1f} | {in_mark:^6}"
            )
        print("=" * 60 + "\n")

    return {
        "accuracy": accuracy,
        "mape": mape,
        "false_positive_rate": fp_rate,
        "avg_latency_ms": avg_latency,
        "total_rows": len(df),
    }


def main():
    parser = argparse.ArgumentParser(description="로그 CSV 분석 및 정량지표 자동 계산")
    parser.add_argument("csv_path", nargs="?", default="data/sample_log.csv", help="분석할 로그 CSV 파일 경로")
    parser.add_argument("--tolerance", type=float, default=0.10, help="목표 조도 허용 오차 (기본 0.10 -> ±10%%)")
    parser.add_argument("--incident", dest="is_incident", action="store_true", default=None, help="외부 입사광 모드로 평가 (투과율 T 적용)")
    parser.add_argument("--sensor", dest="is_incident", action="store_false", help="실내 센서(BH1750) 실측값 모드로 평가")
    parser.add_argument("--threshold", type=float, default=100.0, help="지연시간 측정을 위한 lux 급변 임계값")
    parser.add_argument("--window-ms", type=float, default=15000.0, help="급변 후 최대 지연시간 인정 윈도우 (ms)")
    args = parser.parse_args()

    calculate_metrics(
        csv_path=args.csv_path,
        tolerance=args.tolerance,
        is_incident=args.is_incident,
        lux_step_threshold=args.threshold,
        max_latency_window_ms=args.window_ms,
        verbose=True,
    )


if __name__ == "__main__":
    main()
