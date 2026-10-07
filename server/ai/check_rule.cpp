// decision.h 의 decide_rule() 이 파이썬 규칙(generate_synthetic.py)과 같은 결과를 내는지 확인한다.
//
// 사용법 (저장소 루트에서):
//   g++ -I firmware/sketches/capstone_main server/ai/check_rule.cpp -o /tmp/check_rule && /tmp/check_rule server/ai/data/synthetic.csv
#include <cstdio>
#include "decision.h"

int main(int argc, char** argv) {
  if (argc < 2) { std::printf("usage: %s synthetic.csv\n", argv[0]); return 1; }
  FILE* f = std::fopen(argv[1], "r");
  if (!f) { std::printf("cannot open %s\n", argv[1]); return 1; }
  char line[256];
  std::fgets(line, sizeof line, f);  // header: hour,lux,cur,level
  int total = 0, bad = 0;
  while (std::fgets(line, sizeof line, f)) {
    int hour, cur, level; float lux;
    if (std::sscanf(line, "%d,%f,%d,%d", &hour, &lux, &cur, &level) != 4) continue;
    total++;
    if (decide_rule(lux, hour, cur) != level) {
      bad++;
      if (bad <= 5) std::printf("MISMATCH hour=%d lux=%.1f cur=%d expected=%d got=%d\n", hour, lux, cur, level, decide_rule(lux, hour, cur));
    }
  }
  std::fclose(f);
  std::printf("%d rows, %d mismatches\n", total, bad);
  return bad ? 2 : 0;
}
