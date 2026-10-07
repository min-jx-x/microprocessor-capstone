#pragma once
// 단계 번호 -> 실제 출력. 액추에이터 방식이 정해지면 이 파일만 바꾸면 된다.
// 아래 두 줄 중 하나만 활성화한다.
#define ACTUATOR_PWM            // 대안 A / 개발용: D9 PWM 출력 (LED로 시험 가능, 0-10V 변환 모듈 입력으로 연결)
// #define ACTUATOR_RELAY_TAPS  // 대안 B: 탭 전환 릴레이 (한 번에 한 채널만 ON)

#include "params.h"

#ifdef ACTUATOR_PWM
const uint8_t PWM_PIN = 9;

inline void actuatorInit() { pinMode(PWM_PIN, OUTPUT); }
inline void applyLevel(int level) { analogWrite(PWM_PIN, LUT_PWM[level]); }
#endif

#ifdef ACTUATOR_RELAY_TAPS
// 릴레이 채널 핀. 채널 수 >= LUT_TAP 의 최댓값 + 1 이어야 한다. (핀 번호는 배선에 맞게 수정)
const uint8_t RELAY_PINS[NUM_LEVELS] = {4, 5, 6, 7, 8};
const bool RELAY_ACTIVE_LOW = true;       // 모듈에 따라 다름 (확인 필요)
const unsigned long BREAK_BEFORE_MAKE_MS = 50;  // 탭이 동시에 연결(단락)되지 않도록 전부 끄고 잠시 대기

inline void relayWrite(int ch, bool on) {
  bool level = RELAY_ACTIVE_LOW ? !on : on;
  digitalWrite(RELAY_PINS[ch], level ? HIGH : LOW);
}

inline void actuatorInit() {
  for (int i = 0; i < NUM_LEVELS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    relayWrite(i, false);
  }
}

inline void applyLevel(int level) {
  for (int i = 0; i < NUM_LEVELS; i++) relayWrite(i, false);
  delay(BREAK_BEFORE_MAKE_MS);
  relayWrite(LUT_TAP[level], true);
}
#endif
