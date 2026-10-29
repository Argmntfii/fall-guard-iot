"""Uji logika deteksi. Urutan sampel di sini dibuat manual HANYA untuk unit test
(bukan data yang dikirim sistem). Jalankan: cd processor && pytest"""
import math

import pytest

from detector import FEATURE_NAMES, RuleDetector, confirm, extract_features, replay

DT = 50  # ms, 20 Hz


def s(t, mag, gyro=0.5, ax=0.0, ay=0.0, az=None):
    return {"t": t, "ax": ax, "ay": ay, "az": mag if az is None else az, "mag": mag, "gyro": gyro}


def walking(t0, secs):
    n = int(secs * 1000 / DT)
    return [s(t0 + i * DT, 9.8 + 3 * math.sin(2 * math.pi * 2 * i * DT / 1000)) for i in range(n)]


def still(t0, secs, gyro=0.1):
    n = int(secs * 1000 / DT)
    return [s(t0 + i * DT, 9.8 + (0.1 if i % 2 else 0), gyro) for i in range(n)]


def fall(t0, still_secs=4.0, freefall=True, impact_gyro=4.0, impact_mag=30.0):
    out, t = [], t0
    if freefall:
        for _ in range(6):
            out.append(s(t, 1.5, gyro=2.5)); t += DT
    out.append(s(t, impact_mag, gyro=impact_gyro)); t += DT
    out += still(t, still_secs)
    return out


def test_fall_detected():
    seq = walking(0, 2) + fall(2000)
    events = replay(seq)
    assert len(events) == 1
    assert events[0]["had_freefall"] is True
    assert events[0]["still_std"] < 1.2


def test_walking_is_not_fall():
    assert replay(walking(0, 15)) == []


def test_jump_then_walk_is_not_fall():
    # free-fall + impact, tapi lanjut berjalan (tidak diam)
    seq = walking(0, 2) + fall(2000, still_secs=0) + walking(2400, 6)
    assert replay(seq) == []


def test_bump_without_freefall_or_rotation_is_not_fall():
    seq = walking(0, 2) + fall(2000, freefall=False, impact_gyro=0.2)
    assert replay(seq) == []


def test_rotation_alone_can_trigger():
    seq = walking(0, 2) + fall(2000, freefall=False, impact_gyro=4.0)
    assert len(replay(seq)) == 1


def test_cooldown_suppresses_second_event():
    seq = walking(0, 2) + fall(2000, still_secs=2.5)
    t_next = seq[-1]["t"] + DT
    seq += fall(t_next, still_secs=3)
    assert len(replay(seq)) == 1


def test_cooldown_can_be_disabled():
    seq = walking(0, 2) + fall(2000, still_secs=2.5)
    seq += fall(seq[-1]["t"] + DT, still_secs=3)
    assert len(replay(seq, cooldown_ms=0)) == 2


def test_features_shape_and_tilt():
    w = [s(i * DT, 9.8, ax=0.0, ay=0.0, az=9.8) for i in range(20)]
    w += [s(1000 + i * DT, 9.8, ax=9.8, ay=0.0, az=0.0) for i in range(20)]
    f = extract_features(w)
    assert len(f) == len(FEATURE_NAMES) == 9
    assert f[FEATURE_NAMES.index("tilt_change_deg")] == pytest.approx(90.0, abs=1.0)
    assert f[FEATURE_NAMES.index("mag_max")] == pytest.approx(9.8)


def test_features_need_enough_samples():
    with pytest.raises(ValueError):
        extract_features([s(0, 9.8)] * 3)


class DummyModel:
    classes_ = [0, 1]

    def __init__(self, p_fall):
        self.p = p_fall

    def predict_proba(self, X):
        return [[1 - self.p, self.p] for _ in X]


def _window():
    seq = walking(0, 2) + fall(2000)
    t_imp = 2000 + 6 * DT
    return [x for x in seq if t_imp - 2000 <= x["t"] <= t_imp + 2200]


def test_confirm_with_model():
    ok, conf, src = confirm(_window(), DummyModel(0.9), threshold=0.6)
    assert (ok, conf, src) == (True, 0.9, "ml")
    ok, conf, src = confirm(_window(), DummyModel(0.2), threshold=0.6)
    assert ok is False and src == "ml"


def test_confirm_rule_fallback():
    ok, conf, src = confirm(_window())
    assert ok is True and conf is None and src == "rule"
    ok, _, _ = confirm(walking(0, 4))
    assert ok is False
