// BH1750 값 출력 (Arduino Uno): 센서를 손으로 가렸다 열었을 때 lux가 변하는지 확인한다.
// 필요 라이브러리: "BH1750" by Christopher Laws
#include <Wire.h>
#include <BH1750.h>

BH1750 lightMeter;

void setup() {
  Serial.begin(115200);
  Wire.begin();
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println(F("BH1750 init failed - check wiring"));
  }
}

void loop() {
  float lux = lightMeter.readLightLevel();
  Serial.print(F("lux: "));
  Serial.println(lux);
  delay(500);
}
