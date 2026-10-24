"""pytest 공통 설정: 레포 최상위를 기준으로 실행되게 한다.

실행 (레포 최상위): python -m pytest pi/tests -q
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
