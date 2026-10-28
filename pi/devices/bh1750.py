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
    def __init__(self, bus: int = config.BH1750_BUS, addr: int = config.BH1750_ADDR,
                 _bus_obj: Optional[object] = None) -> None:
        self.bus_num = bus
        self.addr = addr
        self.bus = None

        try:
            if _bus_obj is not None:
                self.bus = _bus_obj
            elif smbus2 is not None:
                self.bus = smbus2.SMBus(self.bus_num)
            
            if self.bus is not None:
                self.bus.write_byte(self.addr, config.BH1750_MODE_CONTINUOUS_HIGH_RES)
        except Exception:
            self.bus = None

    def read_lux(self) -> Optional[float]:
        """2바이트를 읽어 raw / config.BH1750_CONVERSION_FACTOR로 lux를 계산한다.

        읽기 실패(OSError)면 최대 config.BH1750_MAX_RETRY번 재시도하고,
        그래도 안 되면 None을 반환한다 (예외를 밖으로 던지지 않음).
        """
        if self.bus is None:
            return None

        for _ in range(config.BH1750_MAX_RETRY):
            try:
                data = self.bus.read_i2c_block_data(
                    self.addr,
                    config.BH1750_MODE_CONTINUOUS_HIGH_RES,
                    config.BH1750_READ_BYTES
                )
                raw = (data[0] << 8) | data[1]
                return round(raw / config.BH1750_CONVERSION_FACTOR, 1)
            except OSError:
                time.sleep(0.05)
                continue
            except Exception:
                time.sleep(0.05)
                continue
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