// I2C 스캐너 (Arduino Uno): BH1750이 잡히는지 확인한다.
// ADDR 핀 미연결이면 보통 0x23, VCC 연결이면 0x5C. SDA = A4, SCL = A5
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();
  delay(500);
  Serial.println(F("# I2C scan start"));
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print(F("device at 0x"));
      Serial.println(addr, HEX);
      found++;
    }
  }
  if (!found) Serial.println(F("no device found - check wiring (SDA/SCL/VCC/GND)"));
}

void loop() {}
