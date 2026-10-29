"""Logika deteksi jatuh. Murni Python, tanpa MQTT, sehingga mudah diuji.

Dipakai untuk:
  * extract_features()  -> fitur window 4 detik untuk model ML (Data Processing #2)
  * RuleDetector        -> state machine free-fall -> impact -> diam (sama dengan
                           edge1-phone/detector.js yang berjalan di HP)
  * confirm()           -> keputusan akhir di laptop: ML bila model ada, kalau tidak
                           pakai RuleDetector sebagai "pendapat kedua"

Sampel berupa dict: {"t": ms, "ax", "ay", "az", "mag" (m/s^2), "gyro" (rad/s)}.
"""
from __future__ import annotations

import math
from collections import deque
from statistics import mean, pstdev

WINDOW_BEFORE_MS = 2000   # data sebelum impact yang dipakai untuk fitur
WINDOW_AFTER_MS = 2000    # data sesudah impact (waktu event dikirim = impact + 2 detik)

FEATURE_NAMES = [
    "mag_max", "mag_min", "mag_mean", "mag_std", "mag_rms",
    "gyro_max", "gyro_mean", "post_std", "tilt_change_deg",
]


def _std(values):
    return pstdev(values) if len(values) > 1 else 0.0


def _mean_vec(samples):
    n = len(samples)
    return (
        sum(s["ax"] for s in samples) / n,
        sum(s["ay"] for s in samples) / n,
        sum(s["az"] for s in samples) / n,
    )


def _angle_deg(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    c = sum(x * y for x, y in zip(a, b)) / (na * nb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def extract_features(samples):
    """Hitung 9 fitur dari satu window sampel (urut waktu). Urutan = FEATURE_NAMES."""
    if len(samples) < 5:
        raise ValueError("Window minimal 5 sampel")
    samples = sorted(samples, key=lambda s: s["t"])
    t0, t1 = samples[0]["t"], samples[-1]["t"]
    mag = [s["mag"] for s in samples]
    gyro = [s["gyro"] for s in samples]
    post = [s["mag"] for s in samples if s["t"] >= t1 - 1500]   # 1,5 detik terakhir
    head = [s for s in samples if s["t"] <= t0 + 500] or samples[:1]
    tail = [s for s in samples if s["t"] >= t1 - 500] or samples[-1:]
    return [
        max(mag),
        min(mag),
        mean(mag),
        _std(mag),
        math.sqrt(mean(m * m for m in mag)),
        max(gyro),
        mean(gyro),
        _std(post),                                      # ~0 kalau diam setelah jatuh
        _angle_deg(_mean_vec(head), _mean_vec(tail)),    # perubahan orientasi HP
    ]


class RuleDetector:
    """State machine: (free-fall) -> impact -> diam selama still_after_ms -> POSSIBLE_FALL.

    Jatuh dinyatakan bila setelah impact HP diam (std magnitude kecil) DAN
    (sebelumnya ada free-fall ATAU ada rotasi kuat saat impact).
    Semua ambang perlu dikalibrasi dengan data nyata.
    """

    def __init__(self, freefall_mag=4.0, impact_mag=18.0, freefall_window_ms=1000,
                 still_after_ms=2000, still_std=1.2, gyro_min=2.0, cooldown_ms=10000):
        self.freefall_mag = freefall_mag
        self.impact_mag = impact_mag
        self.freefall_window_ms = freefall_window_ms
        self.still_after_ms = still_after_ms
        self.still_std = still_std
        self.gyro_min = gyro_min
        self.cooldown_ms = cooldown_ms
        self.reset()

    def reset(self):
        self.buf = deque()
        self.state = "IDLE"
        self.t_impact = None
        self.t_freefall = None
        self.had_freefall = False
        self.gyro_peak = 0.0
        self.t_last_event = None

    def update(self, t, mag, gyro=0.0):
        """Masukkan satu sampel. Mengembalikan dict event bila jatuh terdeteksi, else None."""
        self.buf.append((t, mag, gyro))
        while self.buf and t - self.buf[0][0] > 5000:
            self.buf.popleft()
        if mag < self.freefall_mag:
            self.t_freefall = t

        if self.state == "IDLE":
            if self.t_last_event is not None and t - self.t_last_event < self.cooldown_ms:
                return None
            if mag > self.impact_mag:
                self.state = "IMPACT"
                self.t_impact = t
                self.had_freefall = (
                    self.t_freefall is not None and t - self.t_freefall <= self.freefall_window_ms
                )
                self.gyro_peak = max(g for tt, _, g in self.buf if tt >= t - 1000)
            return None

        # state == IMPACT
        if t - self.t_impact <= 300:
            self.gyro_peak = max(self.gyro_peak, gyro)
        if t - self.t_impact < self.still_after_ms:
            return None
        after = [m for tt, m, _ in self.buf if tt >= self.t_impact + 500]
        self.state = "IDLE"
        if len(after) >= 5:
            sd = pstdev(after)
            if sd < self.still_std and (self.had_freefall or self.gyro_peak >= self.gyro_min):
                self.t_last_event = t
                return {
                    "type": "POSSIBLE_FALL",
                    "t": t,
                    "t_impact": self.t_impact,
                    "had_freefall": self.had_freefall,
                    "gyro_peak": round(self.gyro_peak, 2),
                    "still_std": round(sd, 3),
                }
        return None


def replay(samples, **rule_kwargs):
    """Jalankan RuleDetector pada daftar sampel; kembalikan list event."""
    det = RuleDetector(**rule_kwargs)
    events = []
    for s in sorted(samples, key=lambda x: x["t"]):
        ev = det.update(s["t"], s["mag"], s.get("gyro", 0.0))
        if ev:
            events.append(ev)
    return events


def confirm(window, model=None, threshold=0.6, **rule_kwargs):
    """Keputusan akhir. Return (is_fall, confidence|None, source)."""
    if model is not None:
        proba = model.predict_proba([extract_features(window)])[0]
        p = float(proba[list(model.classes_).index(1)])
        return p >= threshold, round(p, 2), "ml"
    return bool(replay(window, **rule_kwargs)), None, "rule"
