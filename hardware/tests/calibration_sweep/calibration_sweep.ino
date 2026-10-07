// 캘리브레이션 측정: PWM 구동값을 0~255로 단계적으로 바꾸며 BH1750 lux를 평균내어 "drive,lux" 로 출력한다.
// 결과를 tools/make_lut.py 에 넣으면 단계별 룩업테이블이 나온다.
//
// 측정 조건(매번 동일하게 유지): 광원과 센서 위치 고정, 필름은 센서와 광원 사이, 주변 조명 변화 없음.
// PWM_PIN 에는 개발 중에는 LED, 실제 측정 때는 0-10V 변환 모듈 입력을 연결한다 (대안 A 기준).
// 탭+릴레이 방식(대안 B)이면 analogWrite 부분을 릴레이 채널 전환으로 바꿔서 같은 방식으로 측정한다.
//
// 필요 라이브러리: "BH1750" by Christopher Laws
#include <Wire.h>
#include <BH1750.h>

const uint8_t PWM_PIN = 9;
const unsigned long SETTLE_MS = 3000;  // 구동값을 바꾼 뒤 필름이 안정될 때까지 기다리는 시간 (필름에 맞게 조정)
const int SAMPLES = 20;

BH1750 lightMeter;

void setup() {
  Serial.begin(115200);
  Wire.begin();
  pinMode(PWM_PIN, OUTPUT);
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println(F("# BH1750 init failed - check wiring"));
    while (true) {}
  }
  Serial.println(F("# drive,lux"));
  for (int i = 0; i <= 16; i++) {
    int drive = i * 16;
    if (drive > 255) drive = 255;
    analogWrite(PWM_PIN, drive);
    delay(SETTLE_MS);
    float sum = 0;
    int n = 0;
    for (int k = 0; k < SAMPLES; k++) {
      float l = lightMeter.readLightLevel();
      if (l >= 0) { sum += l; n++; }
      delay(100);
    }
    Serial.print(drive);
    Serial.print(',');
    Serial.println(n ? sum / n : -1.0f, 1);
  }
  Serial.println(F("# done"));
}

void loop() {}
