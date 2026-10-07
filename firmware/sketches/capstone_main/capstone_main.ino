// 캡스톤 메인 펌웨어 (Arduino Uno R3)
// 담당: 김대현 (펌웨어)
//
// 필요 라이브러리: "BH1750" by Christopher Laws (라이브러리 매니저에서 설치)
// 배선: BH1750 SDA -> A4, SCL -> A5 (hardware/wiring_low_voltage.md 참고)
//
// 주의: 실제 보드에서 컴파일/동작을 검증하지 않은 초안이다. 첫 업로드 때 확인할 것.

#include <Wire.h>
#include <BH1750.h>
#include "params.h"
#include "decision.h"
#include "actuator.h"

// ---- 동작 파라미터 ----
const unsigned long SAMPLE_MS = 1000;      // 측정 주기
const unsigned long MIN_SWITCH_MS = 5000;  // 최소 전환 간격 (시연용 값)
const int STABLE_COUNT = 3;                // 같은 판단이 연속 N회 나와야 전환

BH1750 lightMeter;

int hourNow = 14;                // TODO: RTC 또는 NTP로 교체. 지금은 시리얼에 "H14" 처럼 입력해서 변경
int level = NUM_LEVELS - 1;      // 시작은 가장 투명한 단계
int pendingLevel = -1;
int pendingCount = 0;
unsigned long lastSwitchMs = 0;
unsigned long lastSampleMs = 0;

char inBuf[8];
uint8_t inLen = 0;

void handleSerialInput() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inLen >= 2 && (inBuf[0] == 'H' || inBuf[0] == 'h')) {
        inBuf[inLen] = 0;
        int h = atoi(inBuf + 1);
        if (h >= 0 && h <= 23) {
          hourNow = h;
          Serial.print(F("# hour set to "));
          Serial.println(hourNow);
        }
      }
      inLen = 0;
    } else if (inLen < sizeof(inBuf) - 1) {
      inBuf[inLen++] = c;
    }
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  actuatorInit();
  applyLevel(level);
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println(F("# BH1750 init failed - check wiring"));
  }
  Serial.println(F("# ms,hour,lux,level"));  // 로거는 '#'로 시작하는 줄을 파일에 저장하지 않는다
}

void loop() {
  handleSerialInput();

  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_MS) return;
  lastSampleMs = now;

  float lux = lightMeter.readLightLevel();
  if (lux < 0) {
    Serial.println(F("# BH1750 read error"));
    return;
  }

  int desired = decide(lux, hourNow, level);
  if (desired != level) {
    if (desired == pendingLevel) {
      pendingCount++;
    } else {
      pendingLevel = desired;
      pendingCount = 1;
    }
    if (pendingCount >= STABLE_COUNT && (now - lastSwitchMs) >= MIN_SWITCH_MS) {
      applyLevel(desired);
      level = desired;
      lastSwitchMs = now;
      pendingLevel = -1;
      pendingCount = 0;
    }
  } else {
    pendingLevel = -1;
    pendingCount = 0;
  }

  // CSV: ms,hour,lux,level
  Serial.print(now);
  Serial.print(',');
  Serial.print(hourNow);
  Serial.print(',');
  Serial.print(lux, 1);
  Serial.print(',');
  Serial.println(level);
}
