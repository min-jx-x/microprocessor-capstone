#pragma once
// 튜닝 값 모음 (단일 기준 파일).
// server/ai 의 파이썬 스크립트도 이 파일을 읽어서 같은 값을 쓴다.
// 그래서 아래 형식(#define 이름 숫자 / 배열 한 줄)을 바꾸지 말 것.
//
// 단계(level) 규칙: 0 = 가장 불투명, NUM_LEVELS-1 = 가장 투명

// 4단계 — TEAM PDLC 디밍 컨트롤러 스펙 확정값 (7%/15%/30%/100% 프리셋 고정, 2026-09-30 회신).
// 아날로그 다이얼이 아니라 프리셋 버튼 방식이라 소프트웨어로 더 세분화할 수 없음 (docs/actuator-control-notes.md 참고).
// 실물 리모컨에서 다른 가능성이 확인되면 이 값과 LUT_T를 갱신할 것.
#define NUM_LEVELS 4

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

// ---- 룩업테이블 ----
// 단계별 투과율 T (0~1). 현재 값은 TEAM PDLC가 회신한 프리셋 투과율(7%/15%/30%/100%) 그대로이며,
// 실측(calibration_sweep + tools/make_lut.py)이 끝나면 실측값으로 교체해야 한다.
static const float LUT_T[NUM_LEVELS] = {0.07f, 0.15f, 0.30f, 1.00f};
// 레거시: 0-10V PWM 방식(대안 A)을 쓸 경우의 듀티값. 이번 컨트롤러(버튼 프리셋)엔 쓰지 않음 — actuator.h 참고.
static const int LUT_PWM[NUM_LEVELS] = {0, 85, 170, 255};
// 레거시: 다단 변압기 탭 전환(대안 B)을 쓸 경우의 릴레이 채널 번호. 이번 컨트롤러(버튼 프리셋)엔 쓰지 않음.
static const int LUT_TAP[NUM_LEVELS] = {0, 1, 2, 3};
