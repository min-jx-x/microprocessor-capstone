#pragma once
// 단계 번호 -> 실제 출력. 액추에이터 방식이 정해지면 이 파일만 바꾸면 된다.
// 아래 중 하나만 활성화한다.
#define ACTUATOR_RELAY_BUTTON   // 대안 C: TEAM PDLC 디밍 컨트롤러 — 개별 프리셋 버튼 4개를 릴레이로 누름 (확정, 2026-10-07)
// #define ACTUATOR_PWM         // 대안 A: 0-10V 디밍 (이번 컨트롤러엔 해당 없음, 참고용으로 남겨둠)
// #define ACTUATOR_RELAY_TAPS  // 대안 B: 다단 변압기 탭 전환 (DIY, 현재 방식 아님)

#include "params.h"

#ifdef ACTUATOR_RELAY_BUTTON
// TEAM PDLC 디밍 컨트롤러의 프리셋 버튼 4개(7% / 15% / 30% / 100%, 레벨당 1개) 접점을 릴레이로
// 순간 단락시켜 "버튼을 눌렀다"를 시뮬레이션한다. 버튼은 눌리는 즉시 그 단계로 직행하는 프리셋 방식으로
// 가정했다 — 실물 도착하면 꼭 확인할 것: 레벨0에서 레벨3 버튼을 바로 눌렀을 때 중간 단계를 거치지 않고
// 바로 레벨3로 가는지. (순환식이면 이 블록을 다시 손봐야 한다.)
//
// 릴레이 채널 핀 4개 필요 — 지금 BOM(hardware/bom.md)엔 1채널 모듈 1개뿐이라 3개 추가 발주 필요.
// 핀 번호는 배선에 맞게 수정 (hardware/wiring_low_voltage.md).
const uint8_t RELAY_PINS[NUM_LEVELS] = {4, 5, 6, 7};
const bool RELAY_ACTIVE_LOW = true;         // 모듈에 따라 다름 (확인 필요)
const unsigned long BUTTON_PULSE_MS = 150;  // 버튼을 누르고 있는 시간. 리모컨 PCB가 반응하는 최소 시간에 맞게 조정 (실측 필요)

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
  relayWrite(level, true);
  delay(BUTTON_PULSE_MS);
  relayWrite(level, false);
}
#endif

#ifdef ACTUATOR_PWM
const uint8_t PWM_PIN = 9;

inline void actuatorInit() { pinMode(PWM_PIN, OUTPUT); }
inline void applyLevel(int level) { analogWrite(PWM_PIN, LUT_PWM[level]); }
#endif

#ifdef ACTUATOR_RELAY_TAPS
// 릴레이 채널 핀. 채널 수 >= LUT_TAP 의 최댓값 + 1 이어야 한다. (핀 번호는 배선에 맞게 수정)
const uint8_t RELAY_PINS[NUM_LEVELS] = {4, 5, 6, 7};
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
