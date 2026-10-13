import os
import sys
import numpy as np
import pandas as pd


def calculate_metrics(csv_path: str, target_lux_map: dict = None, tolerance: float = 0.10):
    """
    로그 CSV 분석 및 메트릭 자동 계산 함수
    
    :param csv_path: 로그 CSV 파일 경로 (컬럼: ms, hour, lux, level)
    :param target_lux_map: 각 level(단계)별 기준 목표 lux (미지정 시 기본값 적용)
    :param tolerance: 허용 오차 비율 (기본값 0.10 -> ±10%)
    """
    if not os.path.exists(csv_path):
        print(f"Error: 파일을 찾을 수 없습니다 -> {csv_path}")
        return

    # CSV 데이터 로드
    df = pd.read_csv(csv_path)

    # 기본 목표 Lux 매핑 (프로젝트 정의에 맞게 변경 가능)
    # 예: level 1 -> 100 lux, level 2 -> 250 lux, level 3 -> 500 lux
    if target_lux_map is None:
        target_lux_map = {1: 100, 2: 250, 3: 500}

    # -------------------------------------------------------------
    # 1. 정확도 (Accuracy)
    # 정의: 측정 lux가 해당 단계(level)의 목표 lux ±10% 안에 들어온 비율
    # -------------------------------------------------------------
    df["target_lux"] = df["level"].map(target_lux_map)
    df["lower_bound"] = df["target_lux"] * (1 - tolerance)
    df["upper_bound"] = df["target_lux"] * (1 + tolerance)

    # 오차 범위 이내 유효 여부 판별
    in_range = (df["lux"] >= df["lower_bound"]) & (df["lux"] <= df["upper_bound"])
    accuracy = (in_range.sum() / len(df)) * 100 if len(df) > 0 else 0.0

    # -------------------------------------------------------------
    # 2. 오탐률 (False Positive Rate / Unnecessary Transitions)
    # 정의: 목표 lux 범위를 완전히 충족하고 있는 안정적 상태에서
    #       불필요하게 단계(level) 전환이 발생한 횟수 / 전체 판단 횟수
    # -------------------------------------------------------------
    df["level_changed"] = df["level"].diff().abs() > 0

    # 전 상태의 lux가 이전 단계의 목표 오차 범위 안이었는데도 레벨이 바뀌었는지 측정
    # (급변 상황이 아닌 안정 상태에서의 잘못된 레벨 전환 탐지)
    df["prev_target"] = df["target_lux"].shift(1)
    df["prev_lux"] = df["lux"].shift(1)
    df["prev_in_range"] = (df["prev_lux"] >= df["prev_target"] * (1 - tolerance)) & (
        df["prev_lux"] <= df["prev_target"] * (1 + tolerance)
    )

    unnecessary_switches = (df["level_changed"] & df["prev_in_range"]).sum()
    total_decisions = len(df) - 1 if len(df) > 1 else 1
    fp_rate = (unnecessary_switches / total_decisions) * 100

    # -------------------------------------------------------------
    # 3. 지연시간 (Latency)
    # 정의: lux 급변 시점 -> 대응하는 level 전환 완료 시점까지의 시간 (ms)
    # -------------------------------------------------------------
    latencies = []
    
    # lux 임계값 변화량이 큰 지점(급변 시점) 감지
    df["lux_diff"] = df["lux"].diff().abs()
    # 예: lux 변화가 100 이상 급격하게 일어난 지점을 급변 시점으로 판단
    change_points = df[df["lux_diff"] >= 100].index

    for idx in change_points:
        t_start = df.loc[idx, "ms"]
        
        # 급변 발생 지점(idx) 또는 그 직후 레벨이 변경된 지점 찾기
        sub_df = df.loc[idx:]
        level_change_df = sub_df[sub_df["level_changed"]]

        if not level_change_df.empty:
            t_end = level_change_df.iloc[0]["ms"]
            latency = t_end - t_start
            latencies.append(latency)

    avg_latency = float(np.mean(latencies)) if latencies else 0.0

    # -------------------------------------------------------------
    # 결과 출력
    # -------------------------------------------------------------
    print("=" * 45)
    print("            하드웨어 성능 평가 결과          ")
    print("=" * 45)
    print(f"총 분석 데이터 수  : {len(df)} 건")
    print(f"1. 정확도 (Accuracy): {accuracy:.2f} %  (목표 lux ±{int(tolerance*100)}% 이내)")
    print(f"2. 오탐률 (FP Rate)  : {fp_rate:.2f} %  (불필요한 단계 전환: {unnecessary_switches}회)")
    print(f"3. 평균 지연시간     : {avg_latency:.2f} ms")
    print("=" * 45)

    return {
        "accuracy": accuracy,
        "false_positive_rate": fp_rate,
        "avg_latency_ms": avg_latency,
    }


if __name__ == "__main__":
    # 실행 시 파일 경로 인자를 받거나, 기본 sample_log.csv 경로 사용
    target_csv = sys.argv[1] if len(sys.argv) > 1 else "data/sample_log.csv"
    calculate_metrics(target_csv)