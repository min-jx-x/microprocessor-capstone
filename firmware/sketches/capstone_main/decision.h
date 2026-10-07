#pragma once
// 단계 결정 로직. Arduino 의존성이 없는 순수 C++ 이라 PC에서도 테스트할 수 있다.
//
//   int decide(float lux, int hour, int cur)
//     lux  : BH1750 측정값 (필름 뒤쪽 = 실내 조도)
//     hour : 현재 시각 (0~23)
//     cur  : 현재 단계 (0 = 가장 불투명 ... NUM_LEVELS-1 = 가장 투명)
//     반환 : 다음 단계
//
// 방식 (룩업테이블 기반):
//   1) 필름에 들어오는 빛(입사광)을 추정:  incident = lux / T[cur]
//   2) 필요한 투과율:                       T_need = 목표 lux / incident
//   3) T 가 T_need 에 가장 가까운 단계를 선택
//   4) 현재 단계의 오차가 최적 단계 오차 + DEADBAND_T 이하이면 현재 단계 유지
//
// AI 모델을 쓰려면 이 파일을 include 하기 전에 USE_ML_MODEL 을 정의하고,
// server/ai/train.py 가 생성한 model.h 를 이 폴더에 둔다.

#include "params.h"

static inline float decision_absf(float x) { return x < 0 ? -x : x; }

static inline float target_lux(int hour) {
  if (hour >= SLEEP_START_HOUR || hour < SLEEP_END_HOUR) return TARGET_SLEEP_LUX;
  if (hour < WAKE_END_HOUR) return TARGET_WAKE_LUX;
  return TARGET_DAY_LUX;
}

static inline int clamp_level(int level) {
  if (level < 0) return 0;
  if (level > NUM_LEVELS - 1) return NUM_LEVELS - 1;
  return level;
}

static inline int decide_rule(float lux, int hour, int cur) {
  cur = clamp_level(cur);
  float t_cur = LUT_T[cur];
  float incident = lux / t_cur;                            // LUT_T 는 0보다 커야 한다
  float denom = incident > 1.0f ? incident : 1.0f;         // 어두울 때 0 나눗셈/폭주 방지
  float t_need = target_lux(hour) / denom;

  int best = 0;
  float best_err = decision_absf(LUT_T[0] - t_need);
  for (int i = 1; i < NUM_LEVELS; i++) {
    float err = decision_absf(LUT_T[i] - t_need);
    if (err < best_err) {
      best = i;
      best_err = err;
    }
  }
  float cur_err = decision_absf(t_cur - t_need);
  if (cur_err <= best_err + DEADBAND_T) return cur;
  return best;
}

#ifdef USE_ML_MODEL
#include "model.h"  // int ml_predict(float lux, int hour, int cur)
static inline int decide(float lux, int hour, int cur) {
  return clamp_level(ml_predict(lux, hour, clamp_level(cur)));
}
#else
static inline int decide(float lux, int hour, int cur) { return decide_rule(lux, hour, cur); }
#endif
