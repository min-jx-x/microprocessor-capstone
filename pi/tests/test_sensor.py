"""BH1750Sensor 드라이버 단위 테스트."""
from unittest.mock import MagicMock
import pytest

from pi import config
from pi.devices.sensor import BH1750Sensor
from pi.devices.bh1750 import BH1750Sensor as BH1750SensorAlias


def test_bh1750_alias_compatibility():
    assert BH1750Sensor is BH1750SensorAlias


def test_bh1750_init_sends_continuous_high_res_mode():
    mock_bus = MagicMock()
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)
    mock_bus.write_byte.assert_called_once_with(0x23, config.BH1750_MODE_CONTINUOUS_HIGH_RES)


def test_bh1750_read_lux_success():
    mock_bus = MagicMock()
    # raw = 300 (0x012c) -> lux = 300 / 1.2 = 250.0
    mock_bus.read_i2c_block_data.return_value = [0x01, 0x2C]
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)

    lux = sensor.read_lux()
    assert lux == pytest.approx(250.0)
    mock_bus.read_i2c_block_data.assert_called_once_with(
        0x23,
        config.BH1750_MODE_CONTINUOUS_HIGH_RES,
        config.BH1750_READ_BYTES
    )


def test_bh1750_read_lux_retry_on_oserror():
    mock_bus = MagicMock()
    # 2번 실패 후 3번째 성공
    mock_bus.read_i2c_block_data.side_effect = [
        OSError("I2C read failed"),
        OSError("I2C read failed"),
        [0x01, 0x2C],
    ]
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)

    lux = sensor.read_lux()
    assert lux == pytest.approx(250.0)
    assert mock_bus.read_i2c_block_data.call_count == 3


def test_bh1750_read_lux_returns_none_after_max_retries():
    mock_bus = MagicMock()
    # 모든 시도에서 OSError 발생
    mock_bus.read_i2c_block_data.side_effect = OSError("Bus error")
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)

    lux = sensor.read_lux()
    assert lux is None
    assert mock_bus.read_i2c_block_data.call_count == config.BH1750_MAX_RETRY


def test_bh1750_close():
    mock_bus = MagicMock()
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)
    sensor.close()
    mock_bus.close.assert_called_once()


def test_bh1750_recovers_when_init_failed():
    """부팅 때 센서가 응답하지 않아도 다음 측정에서 다시 연결되어야 한다."""
    mock_bus = MagicMock()
    mock_bus.write_byte.side_effect = [OSError("no ack"), None]
    mock_bus.read_i2c_block_data.return_value = [0x01, 0x2C]
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)
    assert sensor.bus is None
    assert sensor.read_lux() == pytest.approx(250.0)
    assert mock_bus.write_byte.call_count == 2


def test_bh1750_reinits_after_read_failures():
    """재시도까지 모두 실패하면 다음 측정 때 측정 모드 명령을 다시 보낸다 (센서 전원이 잠깐 끊긴 경우)."""
    mock_bus = MagicMock()
    sensor = BH1750Sensor(bus=1, addr=0x23, _bus_obj=mock_bus)
    mock_bus.read_i2c_block_data.side_effect = OSError("Bus error")
    assert sensor.read_lux() is None
    mock_bus.read_i2c_block_data.side_effect = None
    mock_bus.read_i2c_block_data.return_value = [0x01, 0x2C]
    assert sensor.read_lux() == pytest.approx(250.0)
    assert mock_bus.write_byte.call_count == 2
