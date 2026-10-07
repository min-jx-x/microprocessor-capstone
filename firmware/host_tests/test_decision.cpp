// decision.h 의 기본 동작을 PC에서 확인한다. (Arduino 불필요)
//
// 사용법 (저장소 루트에서):
//   g++ -I firmware/sketches/capstone_main firmware/host_tests/test_decision.cpp -o /tmp/test_decision && /tmp/test_decision
#include <cstdio>
#include "decision.h"

static int failures = 0;
#define CHECK(cond, msg)                                  \
  do {                                                    \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); failures++; } \
  } while (0)

int main() {
  // 밤에 어두우면 가장 투명한 단계로
  CHECK(decide(0.0f, 23, 0) == NUM_LEVELS - 1, "dark night -> most transparent");
  // 낮에 매우 밝으면 현재보다 더 불투명한 단계로 내려간다
  int bright = decide(1000.0f, 12, NUM_LEVELS - 1);
  CHECK(bright < NUM_LEVELS - 1, "bright day -> darker level");
  // 목표에 거의 맞으면 단계 유지
  float incident = 1000.0f;  // 가정한 입사광
  int cur = 2;
  float lux_at_cur = incident * LUT_T[cur];
  int next = decide(lux_at_cur, 12, cur);
  std::printf("cur=%d lux=%.1f -> next=%d (target %.0f lux)\n", cur, lux_at_cur, next, target_lux(12));
  // 범위 밖 입력이 들어와도 유효한 단계를 돌려준다
  int a = decide(300.0f, 12, -3);
  int b = decide(300.0f, 12, 99);
  CHECK(a >= 0 && a < NUM_LEVELS, "clamp low cur");
  CHECK(b >= 0 && b < NUM_LEVELS, "clamp high cur");

  if (failures == 0) std::printf("OK\n");
  return failures ? 1 : 0;
}
