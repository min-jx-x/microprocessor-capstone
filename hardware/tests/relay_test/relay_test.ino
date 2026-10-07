// 릴레이 채널 시험 (Arduino Uno): 채널을 하나씩 켰다 끈다. 딸깍 소리와 모듈 LED로 확인한다.
// 중요: 처음에는 릴레이 접점 쪽(고전압 쪽)에 아무것도 연결하지 말 것.
//       이후에도 저전압 전구/LED로 먼저 시험하고, 교류 전원 연결은 hardware/safety_checklist.md 점검을 통과한 뒤에만 한다.
const uint8_t RELAY_PINS[] = {4, 5, 6, 7, 8};  // 사용하는 채널 수에 맞게 수정
const int NUM_CH = sizeof(RELAY_PINS) / sizeof(RELAY_PINS[0]);
const bool RELAY_ACTIVE_LOW = true;  // 모듈에 맞게 수정 (확인 필요)

void setRelay(int ch, bool on) {
  bool level = RELAY_ACTIVE_LOW ? !on : on;
  digitalWrite(RELAY_PINS[ch], level ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < NUM_CH; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    setRelay(i, false);
  }
}

void loop() {
  for (int i = 0; i < NUM_CH; i++) {
    setRelay(i, true);
    Serial.print(F("ch "));
    Serial.print(i);
    Serial.println(F(" ON"));
    delay(1000);
    setRelay(i, false);
    delay(500);  // 채널 사이에 모두 꺼진 구간을 둔다 (탭 단락 방지 습관)
  }
}
