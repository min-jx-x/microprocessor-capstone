// model.h 가 파이썬 모델과 같은 결과를 내는지 PC에서 확인한다.
//
// 사용법 (저장소 루트에서, train.py 실행 후):
//   g++ -I firmware/sketches/capstone_main server/ai/check_model.cpp -o /tmp/check_model && /tmp/check_model server/ai/data/test_vectors.csv
#include <cstdio>
#include "model.h"

int main(int argc, char** argv) {
  if (argc < 2) { std::printf("usage: %s test_vectors.csv\n", argv[0]); return 1; }
  FILE* f = std::fopen(argv[1], "r");
  if (!f) { std::printf("cannot open %s\n", argv[1]); return 1; }
  char line[256];
  std::fgets(line, sizeof line, f);  // header: lux,hour,cur,expected
  int total = 0, bad = 0;
  while (std::fgets(line, sizeof line, f)) {
    float lux; int hour, cur, expected;
    if (std::sscanf(line, "%f,%d,%d,%d", &lux, &hour, &cur, &expected) != 4) continue;
    total++;
    if (ml_predict(lux, hour, cur) != expected) {
      bad++;
      if (bad <= 5) std::printf("MISMATCH lux=%.4f hour=%d cur=%d expected=%d\n", lux, hour, cur, expected);
    }
  }
  std::fclose(f);
  std::printf("%d vectors, %d mismatches\n", total, bad);
  return bad ? 2 : 0;
}
