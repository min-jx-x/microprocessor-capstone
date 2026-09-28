/*
  단계조광 스마트 블라인드 - 초기 스켈레톤 (v3: 현재 보유 하드웨어 기준)

  지금 손에 있는 게 "아두이노 우노 R3 + 브레드보드 + 점퍼선"뿐이라
  (BH1750 조도센서, 릴레이 모듈, PDLC 필름, 파워서플라이 전부 미도착),
  추가 부품 없이 우노 보드 하나만으로 돌아가게 만든 버전.

  - 조도센서 대신: 시리얼모니터에 숫자를 입력하면 그걸 "현재 조도(lux)"로 취급
  - 릴레이 대신: 보드 내장 LED(13번 핀, LED_BUILTIN)로 액추에이터 동작 여부를 표시
  - 그 외 판단 로직(시간대별 목표조도 비교, controlActuator 호출 흐름)은
    나중에 진짜 센서/릴레이로 바꿔도 구조가 그대로 유지되도록 짜둠.

  사용법:
    1) 업로드 후 시리얼모니터 열기 (9600bps, 줄바꿈 "새 줄" 설정)
    2) 조도값(숫자) 입력하고 엔터 -> "현재 조도"로 반영됨
    3) 목표조도보다 낮으면 "더 밝게 필요", 높으면 "더 어둡게 필요" 로그가 찍히고
       controlLevel > 0 이면 보드 내장 LED가 켜짐(지금은 항상 0이라 항상 꺼져있음 -
       이건 정상. lookupControlLevel이 아직 캘리브레이션 데이터가 없어서 임시로 0만
       반환하기 때문. 아래 TODO 참고)

  부품 도착하면 교체할 부분 (TODO에 위치 표시해둠):
    - BH1750 도착 -> readCurrentLux()를 실제 센서 읽기로 교체 (Wire.h + BH1750.h 필요)
    - 릴레이 모듈 도착 -> ACTUATOR_INDICATOR_PIN을 릴레이 핀(예: 7번)으로 교체
    - 필름/파워서플라이 도착 + 제어방식 확정 -> controlActuator() 실제 구현
      (docs/actuator-control-notes.md 참고)
    - 필름 실측 -> calibrationTable 채우고 lookupControlLevel 구현
      (docs/quantitative-metrics.md 참고)
*/

// 릴레이 도착 전까지는 보드 내장 LED로 "액추에이터가 지금 켜져있다/꺼져있다"를 대신 표시.
// 릴레이 도착하면 이 값을 실제 릴레이가 연결된 디지털 핀 번호로 바꾸면 됨(예: 7).
const int ACTUATOR_INDICATOR_PIN = LED_BUILTIN;

// ---- 시간대별 목표 조도 (lux) - 임시값, 실측/문헌 기반으로 조정 예정 ----
struct TargetProfile {
  const char* label;
  int targetLux;
};

TargetProfile profiles[] = {
  {"sleep",   10},   // 취침: 저조도
  {"wake",    200},  // 기상: 점진적 증가 목표
  {"daytime", 500},  // 주간: 일반 실내조도
};

// ---- 캘리브레이션 룩업테이블 자리표시자 ----
// 실측 후 {제어값(전압 또는 릴레이 조합 코드), 실측 lux} 쌍으로 채운다.
struct CalibrationPoint {
  int controlLevel; // 0~N (방식 확정 전 임시 정수 레벨)
  int measuredLux;
};

CalibrationPoint calibrationTable[] = {
  // { 0, 0 },   // 예시: 완전 차단 상태 실측값
  // { 1, 0 },   // TODO: 실측 후 채우기
};

// 센서 없을 때 쓸 기본값. 시리얼로 값을 입력하면 이 값이 갱신됨.
int lastKnownLux = 300;

void setup() {
  Serial.begin(9600);
  pinMode(ACTUATOR_INDICATOR_PIN, OUTPUT);
  digitalWrite(ACTUATOR_INDICATOR_PIN, LOW);

  Serial.println("=== 단계조광 스켈레톤 (센서/릴레이 없이 시뮬레이션 모드) ===");
  Serial.println("시리얼모니터에 조도값(숫자) 입력 후 엔터 -> 현재 조도로 반영됩니다.");
}

int readCurrentLux() {
  // TODO: BH1750 센서 도착하면 아래 코드로 교체 (Wire.h, BH1750.h 필요)
  //   float lux = lightMeter.readLightLevel();
  //   if (lux < 0) return lastKnownLux; // 읽기 실패 시 마지막 값 유지
  //   return (int)lux;

  // 지금은 센서가 없어서, 시리얼 입력을 받으면 그 숫자를 현재 조도로 취급.
  if (Serial.available() > 0) {
    int input = Serial.parseInt();
    while (Serial.available() > 0) Serial.read(); // 남은 개행문자 등 버퍼 비우기
    if (input > 0) {
      lastKnownLux = input;
      Serial.print(">> 입력받은 조도값으로 갱신: ");
      Serial.println(lastKnownLux);
    }
  }
  return lastKnownLux;
}

int decideTargetLux(const char* timeLabel) {
  for (auto &p : profiles) {
    if (strcmp(p.label, timeLabel) == 0) return p.targetLux;
  }
  return profiles[2].targetLux; // 기본값: daytime
}

int lookupControlLevel(int targetLux) {
  // TODO: calibrationTable을 순회하며 targetLux에 가장 가까운 controlLevel 반환
  // 캘리브레이션 데이터(필름 실측값)가 채워지기 전까지는 임시로 0 반환
  return 0;
}

void controlActuator(int controlLevel) {
  // TODO: 필름/파워서플라이 도착 및 제어방식 확정 후 실제 구현으로 교체
  // - 방식 2-A(0-10V): PWM-to-0-10V 모듈에 아날로그 출력
  // - 방식 2-B(RS485): MAX485 모듈로 시리얼 통신
  // - 방식 4(DIY 다단변압기): controlLevel을 릴레이 ON/OFF 조합으로 변환해 출력
  Serial.print("controlActuator called with level=");
  Serial.println(controlLevel);

  // 지금은 실제 액추에이터가 없어서, controlLevel > 0이면 내장 LED만 켜서
  // "여기서 액추에이터가 동작했을 것"을 표시 (실제 밝기 제어 아님, 배선/로직 검증용)
  digitalWrite(ACTUATOR_INDICATOR_PIN, controlLevel > 0 ? HIGH : LOW);
}

void loop() {
  int currentLux = readCurrentLux();
  const char* currentTimeLabel = "daytime"; // TODO: 시간대 판단 로직(NTP/RTC 결정 후)으로 대체

  int targetLux = decideTargetLux(currentTimeLabel);
  int controlLevel = lookupControlLevel(targetLux);
  controlActuator(controlLevel);

  Serial.print("현재 조도: ");
  Serial.print(currentLux);
  Serial.print(" lux | 시간대: ");
  Serial.print(currentTimeLabel);
  Serial.print(" | 목표 조도: ");
  Serial.print(targetLux);
  Serial.print(" lux | 판단: ");
  if (currentLux < targetLux) {
    Serial.println("더 밝게 필요 (목표보다 어두움)");
  } else if (currentLux > targetLux) {
    Serial.println("더 어둡게 필요 (목표보다 밝음)");
  } else {
    Serial.println("목표 도달");
  }

  delay(1000);
}
