"""실측값(lut.json) 처리 테스트."""
import json

from pi import calib


def test_sorts_by_brightness_and_normalizes():
    # 45V/45V(480)가 100V/꺼짐(410)보다 밝은 경우 → 순서가 바뀌어야 함
    cal = calib.build(calib.LEVELS_6, [182, 279, 480, 410, 715, 1273], ambient=5)
    assert cal.levels[2] == ("high", "off") and cal.levels[3] == ("low", "low")
    assert cal.ratio[-1] == 1.0
    assert cal.ratio == sorted(cal.ratio)


def test_save_and_load(tmp_path):
    p = tmp_path / "lut.json"
    calib.save(str(p), [100, 150, 220, 260, 400, 700], ambient=10, levels=calib.LEVELS_6)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["ambient_lux"] == 10
    cal = calib.load(str(p))
    assert cal is not None and len(cal.ratio) == 6


def test_three_level_mode_is_default_and_45v_only():
    from pi import config
    assert calib.level_mode(None) == 3 and calib.level_mode("") == 3 and calib.level_mode("x") == 3
    assert calib.level_mode("6") == 6
    assert calib.LEVELS_3 == calib.LEVELS_6[:3]
    assert all("high" not in combo for combo in calib.LEVELS_3)   # 3단계는 100V를 쓰지 않음
    if calib.LEVEL_MODE == 3:
        assert config.NUM_LEVELS == 3 and len(config.LUT_T_DEFAULT) == 3


def test_save_and_load_three_levels(tmp_path):
    p = tmp_path / "lut3.json"
    calib.save(str(p), [120, 260, 410], ambient=5, levels=calib.LEVELS_3)
    cal = calib.load(str(p))
    assert cal is not None and len(cal.ratio) == 3 and cal.ratio[-1] == 1.0
    assert cal.levels == calib.LEVELS_3


def test_missing_or_broken_file_returns_none(tmp_path):
    assert calib.load(str(tmp_path / "none.json")) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert calib.load(str(bad)) is None
