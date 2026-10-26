"""BH1750 조도센서 호환성 모듈.

pi/devices/sensor.py의 BH1750Sensor를 re-export하여
기존 코드(app.py, tools/check_sensor.py 등)와 신규 명세 모두 지원한다.
"""
from pi.devices.sensor import BH1750Sensor

__all__ = ["BH1750Sensor"]
