"""LightQ 설정값 모음.

모든 숫자 설정은 이 파일 한 곳에서만 관리한다.
다른 모듈은 값을 직접 쓰지 말고 `from pi import config` 후 `config.이름`으로 가져다 쓴다.
"""
import os


# ---------------------------------------------------------------------------
# 하드웨어 연결
# ---------------------------------------------------------------------------

# 릴레이 이름별 GPIO 번호 (BCM 번호 기준, 핀 번호 아님)
#   SA: 필름 A 전압 선택 (릴레이 SA1·SA2 두 개가 같은 핀에 연결됨)
#   PA: 필름 A 전원
#   SB: 필름 B 전압 선택 (릴레이 SB1·SB2 두 개가 같은 핀에 연결됨)
#   PB: 필름 B 전원
# 3단계 모드(기본, 45V만)에서는 SA·SB 릴레이를 연결하지 않는다.
#   대신 PA 핀에 PA·PA2, PB 핀에 PB·PB2 두 개씩 연결해 필름 두 선을 모두 끊는다.
GPIO_PINS = {"SA": 17, "PA": 27, "SB": 22, "PB": 23}

# 릴레이별로 LOW 신호에서 켜지는 타입(저레벨 트리거)이면 True, HIGH에서 켜지면(고레벨 트리거) False.
# 10/29 3단계 재배선 후 재시험: PA·PA2·PB·PB2 모두 고레벨 트리거 (HIGH = 켜짐). #14의 'PA·PB 저레벨' 판단은 더 이상 맞지 않음.
# 3단계 모드의 PA2·PB2는 PA·PB와 같은 핀을 쓰므로 PA·PB와 같은 타입이어야 한다 (H/L 점퍼가 있으면 맞춘다).
# 값을 바꾸면 deploy/setup_pi.sh를 다시 실행하고 재부팅한다 (부팅 중 꺼짐 레벨도 이 값을 따름).
RELAY_ACTIVE_LOW = {"SA": False, "PA": False, "SB": False, "PB": False}


def boot_gpio_lines() -> list:
    """부팅 직후부터 릴레이를 '꺼짐'으로 두는 /boot/firmware/config.txt 줄 (deploy/setup_pi.sh가 씀).

    저레벨 트리거는 HIGH(dh), 고레벨 트리거는 LOW(dl)가 꺼짐이라 릴레이별로 나눠 적는다.
    """
    lines = []
    for low, level in ((True, "dh"), (False, "dl")):
        pins = [str(p) for name, p in GPIO_PINS.items() if RELAY_ACTIVE_LOW[name] == low]
        if pins:
            lines.append(f"gpio={','.join(pins)}=op,{level}")
    return lines

# BH1750 조도센서 (I2C)
BH1750_BUS = 1        # Pi의 I2C 버스 번호
BH1750_ADDR = 0x23    # ADDR 핀이 GND면 0x23, VCC면 0x5C
BH1750_MODE_CONTINUOUS_HIGH_RES = 0x10  # 연속 고해상도 모드 명령 (1 lx 분해능)
BH1750_MAX_RETRY = 3                   # 읽기 실패 시 최대 재시도 횟수
BH1750_CONVERSION_FACTOR = 1.2         # raw 데이터 -> lux 환산 계수 (raw / 1.2)
BH1750_READ_BYTES = 2                  # 센서 측정 데이터 바이트 수

# ---------------------------------------------------------------------------
# 제어 주기와 깜빡임 방지
# ---------------------------------------------------------------------------

SAMPLE_PERIOD_S = 1.0          # 센서를 읽고 판단하는 주기(초)
STABLE_COUNT = 3               # 같은 판단이 3회 연속이어야 전환
MIN_SWITCH_INTERVAL_S = 5.0    # 마지막 전환 후 최소 간격(초)
RELAY_SETTLE_S = 0.1           # 릴레이를 바꾼 뒤 다음 동작까지 기다리는 시간(초)
STABILIZER_INITIAL_LAST_SWITCH = -1e9  # 시작 직후 즉시 전환 가능하도록 과거 시각으로 초기화

# ---------------------------------------------------------------------------
# 단계 정의
# ---------------------------------------------------------------------------

# 단계 번호 = 리스트 인덱스. 0이 가장 어둡다(실측 후 순서 확정).
# 각 항목은 (필름 A 상태, 필름 B 상태)
#   "off"  = 전원 꺼짐 (불투명)
#   "low"  = 약 45V (변압기 T2)
#   "high" = 100V (변압기 T1) - 6단계 모드에서만 사용
# 단계 구성은 환경변수 LIGHTQ_LEVELS로 고른다 (목록은 pi/calib.py).
#   3 (기본): 꺼짐/꺼짐, 45V/꺼짐, 45V/45V  → 필름 정격(60~70V) 안
#   6       : 위 3개 + 100V/꺼짐, 100V/45V, 100V/100V
from pi import calib as _calib  # noqa: E402

LEVEL_MODE = _calib.LEVEL_MODE
LEVELS = list(_calib.DEFAULT_LEVELS)
NUM_LEVELS = len(LEVELS)

# AI 모델 파일도 단계 구성마다 따로 둔다. 6단계 때 학습한 모델(ai_tree_6level.json)을 지우지 않고 보관해
# LIGHTQ_LEVELS=6으로 바꾸면 재학습 없이 그 모델을 바로 쓴다. 기록은 docs/troubleshooting-6-to-3-levels.md
AI_MODEL_PATH = os.environ.get(
    "LIGHTQ_AI_MODEL",
    "pi/data/ai_tree.json" if LEVEL_MODE == 3 else "pi/data/ai_tree_6level.json")
# 모델 선택 근거 실험 결과 (python -m pi.ai.compare_models). 웹 'AI 설명' 페이지가 읽는다.
AI_REPORT_PATH = os.environ.get(
    "LIGHTQ_AI_REPORT",
    "pi/data/ai_report.json" if LEVEL_MODE == 3 else "pi/data/ai_report_6level.json")

# ---------------------------------------------------------------------------
# 시간대와 목표 조도 (Uno 시절 params.h 값을 이어받음, 팀 합의 후 조정)
# ---------------------------------------------------------------------------
#   취침  SLEEP_START_HOUR ~ (기상 시각 - WAKE_RAMP_MIN) : 0단계 고정 (어둡게)
#   기상  (기상 시각 - WAKE_RAMP_MIN) ~ 기상 시각        : 목표 조도를 서서히 올림
#   아침  기상 시각 ~ WAKE_END_HOUR                       : TARGET_WAKE_LUX
#   주간  WAKE_END_HOUR ~ SUNSET_HOUR                     : TARGET_DAY_LUX
#   저녁  SUNSET_HOUR ~ SLEEP_START_HOUR                  : 0단계 고정 (사생활 보호)

DEFAULT_WAKE_TIME = "07:30"    # 웹에서 바꿀 수 있는 기상 시각 기본값
WAKE_RAMP_MIN = 20             # 기상 몇 분 전부터 밝아지기 시작할지
WAKE_END_HOUR = 9.0
SUNSET_HOUR = 18.0
SLEEP_START_HOUR = 22.0

TARGET_WAKE_START_LUX = 20.0   # 기상 램프 시작 시 목표
TARGET_WAKE_LUX = 200.0        # 기상 시각 이후 아침 목표
TARGET_DAY_LUX = 500.0         # 주간 목표

# ---------------------------------------------------------------------------
# 단계별 상대 투과율 (가장 밝은 단계 = 1.0 기준)
# ---------------------------------------------------------------------------
# 판단 규칙이 쓰는 값. pi/data/lut.json(재우 calibrate.py 결과)이 있으면 그 값을 우선 쓴다.
# 아래 기본값은 시뮬레이터 가정(꺼짐 0.30, 45V 0.45, 100V 0.80)의 곱을 가장 밝은 단계로 나눈 값.
_LUT_T_DEFAULTS = {
    3: [0.44, 0.67, 1.00],                       # 0.09, 0.135, 0.2025 / 0.2025
    6: [0.14, 0.21, 0.32, 0.38, 0.56, 1.00],     # 0.09 ~ 0.64 / 0.64
}
LUT_T_DEFAULT = _LUT_T_DEFAULTS[LEVEL_MODE]
DEADBAND_T = 0.05              # 현재 단계를 유지하는 허용 오차. 클수록 덜 바뀐다

# ---------------------------------------------------------------------------
# 실측값 반영 (pi/data/lut.json, 형식은 pi/calib.py 참고)
# ---------------------------------------------------------------------------
# 파일이 있으면 단계 순서(LEVELS)를 실측 밝기 순으로 바꾸고, 상대 투과율(LUT_T)도 실측값을 쓴다.
# 파일이 없으면 위 기본값 그대로. 어느 쪽인지는 LUT_SOURCE로 확인 ("measured" / "default").
# 단계 수가 다른 lut.json(예: 6단계 때 잰 값)은 무시하고 기본값을 쓴다.

CALIBRATION = _calib.load()
if CALIBRATION is not None and len(CALIBRATION.ratio) == NUM_LEVELS:
    if CALIBRATION.lux:                       # 조합 정보가 있을 때만 순서를 바꾼다
        LEVELS = [tuple(x) for x in CALIBRATION.levels]
    LUT_T = list(CALIBRATION.ratio)
    LUT_SOURCE = "measured"
else:
    CALIBRATION = None
    LUT_T = list(LUT_T_DEFAULT)
    LUT_SOURCE = "default"

# ---------------------------------------------------------------------------
# 웹 / 로그
# ---------------------------------------------------------------------------
WEB_HOST = "0.0.0.0"           # 같은 Wi-Fi(핫스팟)의 휴대폰에서 접속 가능하게
WEB_PORT = 5000
WEB_HTTPS_PORT = 5443          # 인증서(deploy/make_cert.sh)가 있으면 이 포트로 HTTPS도 연다 (휴대폰 마이크용)
TLS_CERT = "pi/data/certs/cert.pem"
TLS_KEY = "pi/data/certs/key.pem"
HISTORY_POINTS = 300           # 화면 그래프에 보여줄 최근 기록 개수
# 핫스팟은 인터넷이 없어 Pi가 시각을 못 맞춘다(RTC 배터리 없으면 부팅 때 틀림).
# 대시보드를 열면 휴대폰 시각을 보내고, 차이가 이 값(초)보다 크면 그 시각으로 맞춘다.
TIME_SYNC_MIN_DIFF_S = 30
DB_PATH = os.environ.get("LIGHTQ_DB", "pi/data/lightq.db")   # 환경변수로 바꿀 수 있음
# SD카드 쓰기 줄이기: 기록을 모아 두었다가 이 간격(초)마다 한 번에 저장한다.
# 단계 전환 같은 이벤트는 바로 저장한다. 전원이 갑자기 꺼지면 최대 이 시간만큼 기록을 잃는다.
LOG_COMMIT_S = 10.0
LOG_KEEP_DAYS = 30             # 이보다 오래된 기록은 하루 한 번 지운다 (0이면 지우지 않음)

# ---------------------------------------------------------------------------
# 안전
# ---------------------------------------------------------------------------
SENSOR_FAIL_LIMIT = 10         # 센서가 연속 이 횟수만큼 실패하면 0단계(모든 릴레이 꺼짐)로 두고 경고
SAFE_LEVEL = 0                 # 0단계 = 필름 전원이 모두 꺼진 상태라 전기적으로 가장 안전

# ---------------------------------------------------------------------------
# 개인 선호 보정 (pi/control/preference.py)
# ---------------------------------------------------------------------------
PREF_PATH = os.environ.get("LIGHTQ_PREF", "pi/data/preferences.json")
PREF_ALPHA = 0.3               # 수동 조작 한 번에 목표를 차이의 30%만큼 옮김
PREF_MAX = 0.3                 # 목표 보정은 기본값의 ±30% 안
PREF_SETTLE = 3                # 수동으로 바꾼 뒤 몇 회(초) 측정해서 선호 조도로 볼지

# ---------------------------------------------------------------------------
# 음성(문장) 명령 (pi/voice/)
# ---------------------------------------------------------------------------
VOICE_DATA_PATH = "pi/data/voice_intents.csv"      # 예문 (split, intent, text)
VOICE_MODEL_PATH = "pi/data/intent_model.json"     # 노트북에서 python -m pi.voice.train 으로 만든 의도 분류기
VOICE_REPORT_PATH = "pi/data/voice_report.json"    # 시험 예문 정확도 등
VOICE_MIN_CONF = 0.6           # 분류기 확신도가 이보다 낮으면 LLM에 묻는다 (voice_report.json의 thresholds 참고)
VOICE_MIN_CONF_OFFLINE = 0.35  # LLM을 못 쓸 때(키·인터넷 없음, 실패)는 이 확신도 이상이면 분류기 답을 그대로 쓴다
VOICE_COOLDOWN_S = 2.0         # 단계를 바꾸는 음성 명령 사이 최소 간격 (여러 기기가 동시에 보낼 때 깜빡임 방지)
VOICE_MAX_CHARS = 60           # 문장 길이 제한
VOICE_LOG_SIZE = 20            # 화면에 보여 줄 최근 명령 수
VOICE_LEARN = os.environ.get("LIGHTQ_VOICE_LEARN", "0") == "1"   # 음성 명령을 선호 학습에 쓸지 (시연 기본: 끔)
# LLM(Gemini) 보조 판단. 키는 환경변수 LIGHTQ_LLM_KEY 로만 넣는다 (레포에 넣지 않음)
VOICE_LLM_MODEL = "gemini-3.1-flash-lite"   # 환경변수 LIGHTQ_LLM_MODEL 로 바꿀 수 있음
VOICE_LLM_TIMEOUT_S = 5.0      # 이 안에 답이 없으면 포기하고 분류기 답으로 (3초일 때 15번 중 2번 시간 초과)
VOICE_LLM_MAX_PER_MIN = 10     # 분당 최대 호출 (무료 등급 한도 보호)
# 오프라인 음성 인식 (whisper.cpp 서버, deploy/setup_whisper.sh로 설치)
VOICE_STT_URL = "http://127.0.0.1:8178/inference"   # 환경변수 LIGHTQ_STT_URL 로 바꿀 수 있음
VOICE_STT_TIMEOUT_S = 15.0     # 글자로 바꾸는 데 이보다 오래 걸리면 포기
VOICE_STT_CHECK_S = 10.0       # 서버가 켜져 있는지 다시 확인하는 간격
VOICE_STT_LANG = "ko"
# 자주 나올 단어를 미리 알려 주면 인식이 나아진다 (빈 문자열이면 끔)
VOICE_STT_PROMPT = "라이트큐 창문 밝기 명령. 너무 밝아, 어둡게, 밝게, 0단계, 1단계, 2단계, 자동으로, 다 가려 줘."
VOICE_AUDIO_MAX_BYTES = 1_000_000    # 녹음 파일 최대 크기 (16kHz 모노 약 30초)
VOICE_AUDIO_DIR = "pi/data/voice_audio"
VOICE_AUDIO_KEEP = int(os.environ.get("LIGHTQ_VOICE_KEEP", "0"))   # 최근 녹음을 몇 개 남길지 (정확도 확인용, 기본 0 = 저장 안 함)
