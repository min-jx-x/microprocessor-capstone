#pragma once
// 튜닝 값 모음 (단일 기준 파일).
// server/ai 의 파이썬 스크립트도 이 파일을 읽어서 같은 값을 쓴다.
// 그래서 아래 형식(#define 이름 숫자 / 배열 한 줄)을 바꾸지 말 것.
//
// 단계(level) 규칙: 0 = 가장 불투명, NUM_LEVELS-1 = 가장 투명

#define NUM_LEVELS 5

// 시간대별 목표 조도 (lux) - 임시값, 팀 합의 후 수정
#define TARGET_SLEEP_LUX 5.0f
#define TARGET_WAKE_LUX 200.0f
#define TARGET_DAY_LUX 500.0f

// 시간대 경계 (시) - 임시값
//   취침: SLEEP_START_HOUR 이상 또는 SLEEP_END_HOUR 미만
//   기상: SLEEP_END_HOUR 이상 WAKE_END_HOUR 미만
//   주간: 그 외
#define SLEEP_START_HOUR 22
#define SLEEP_END_HOUR 6
#define WAKE_END_HOUR 9

// 현재 단계를 유지하는 허용 오차 (투과율 기준). 값이 클수록 단계가 덜 바뀐다.
#define DEADBAND_T 0.05f

// ---- 룩업테이블 (임시 곡선: 필름/드라이버 실측 후 tools/make_lut.py 결과로 교체) ----
// 단계별 투과율 T (0~1)
static const float LUT_T[NUM_LEVELS] = {0.05f, 0.25f, 0.50f, 0.75f, 0.90f};
// 대안 A(PWM -> 0-10V): 단계별 PWM 듀티 (0~255)
static const int LUT_PWM[NUM_LEVELS] = {0, 64, 128, 192, 255};
// 대안 B(탭 전환 + 릴레이): 단계별 릴레이 채널 번호 (0 ~ 채널 수-1)
static const int LUT_TAP[NUM_LEVELS] = {0, 1, 2, 3, 4};
