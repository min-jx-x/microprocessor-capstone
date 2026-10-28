"""BH1750 I2C 조도센서 드라이버.

smbus2를 사용하여 Raspberry Pi I2C 버스에서 BH1750 센서와 통신한다.
모든 설정값은 config.py에서 가져오며, 코드에 숫자를 직접 쓰지 않는다.
"""
import time
from typing import Optional

try:
    import smbus2
except (ImportError, ModuleNotFoundError):
    smbus2 = None

from pi import config


class BH1750Sensor:
    """초기화나 읽기가 실패해도 다음 read_lux()에서 다시 연결을 시도한다.
    (부팅 때 선이 헐거웠거나 센서 전원이 잠깐 끊겨도 재시작 없이 복구)"""

    def __init__(self, bus: int = config.BH1750_BUS, addr: int = config.BH1750_ADDR,
                 _bus_obj: Optional[object] = None) -> None:
        self.bus_num = bus
        self.addr = addr
        self._bus_obj = _bus_obj       # 테스트용 가짜 버스
        self.bus = None
        self._state = None             # "ok" / "fail". 바뀔 때만 로그를 남긴다 (매초 같은 로그 방지)
        self._open()

    def _open(self) -> bool:
        """버스를 열고 측정 모드 명령을 보낸다. 실패하면 False."""
        try:
            if self.bus is None:
                if self._bus_obj is not None:
                    self.bus = self._bus_obj
                elif smbus2 is not None:
                    self.bus = smbus2.SMBus(self.bus_num)
                else:
                    self._report(False, "smbus2 없음")
                    return False
            self.bus.write_byte(self.addr, config.BH1750_MODE_CONTINUOUS_HIGH_RES)
            self._report(True)
            return True
        except Exception as e:
            self._drop()
            self._report(False, e)
            return False

    def _drop(self) -> None:
        """버스를 닫아서 다음 읽기 때 새로 열게 한다."""
        if self.bus is not None and self.bus is not self._bus_obj:
            try:
                self.bus.close()
            except Exception:
                pass
        self.bus = None

    def _report(self, ok: bool, err: object = None) -> None:
        state = "ok" if ok else "fail"
        if state == self._state:
            return
        self._state = state
        if ok:
            print(f"[bh1750] 연결됨 (bus {self.bus_num}, 0x{self.addr:02x})")
        else:
            print(f"[bh1750] 연결 실패 (bus {self.bus_num}, 0x{self.addr:02x}): {err} → 다음 측정 때 다시 시도")

    def read_lux(self) -> Optional[float]:
        """2바이트를 읽어 raw / config.BH1750_CONVERSION_FACTOR로 lux를 계산한다.

        읽기 실패(OSError)면 최대 config.BH1750_MAX_RETRY번 재시도하고,
        그래도 안 되면 None을 반환한다 (예외를 밖으로 던지지 않음).
        연결이 끊긴 상태면 먼저 다시 연결하고, 재시도까지 모두 실패하면 다음 번에 새로 연결한다.
        """
        if self.bus is None and not self._open():
            return None

        for _ in range(config.BH1750_MAX_RETRY):
            try:
                data = self.bus.read_i2c_block_data(
                    self.addr,
                    config.BH1750_MODE_CONTINUOUS_HIGH_RES,
                    config.BH1750_READ_BYTES
                )
                raw = (data[0] << 8) | data[1]
                self._report(True)
                return round(raw / config.BH1750_CONVERSION_FACTOR, 1)
            except Exception:
                time.sleep(0.05)
        self._drop()
        self._report(False, f"{config.BH1750_MAX_RETRY}회 연속 읽기 실패")
        return None

    def close(self) -> None:
        """연결된 I2C 버스를 닫는다."""
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                pass
            finally:
                self.bus = None
