/* State machine deteksi jatuh (Data Processing #1, berjalan di HP / edge).
 * Logikanya sama dengan processor/detector.py (RuleDetector) agar hasilnya konsisten.
 * Free-fall -> impact -> diam selama stillAfterMs -> POSSIBLE_FALL. Ambang perlu dikalibrasi. */
(function (root) {
  function std(a) {
    if (a.length < 2) return 0;
    const m = a.reduce((s, v) => s + v, 0) / a.length;
    return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length);
  }

  class RuleDetector {
    constructor(opts = {}) {
      this.o = Object.assign({
        freefallMag: 4, impactMag: 18, freefallWindowMs: 1000,
        stillAfterMs: 2000, stillStd: 1.2, gyroMin: 2, cooldownMs: 10000,
      }, opts);
      this.reset();
    }

    reset() {
      this.buf = [];
      this.state = 'IDLE';
      this.tImpact = null;
      this.tFreefall = null;
      this.hadFreefall = false;
      this.gyroPeak = 0;
      this.tLastEvent = null;
    }

    /** t (ms), mag (m/s^2), gyro (rad/s). Return event object atau null. */
    update(t, mag, gyro = 0) {
      const o = this.o;
      this.buf.push([t, mag, gyro]);
      while (this.buf.length && t - this.buf[0][0] > 5000) this.buf.shift();
      if (mag < o.freefallMag) this.tFreefall = t;

      if (this.state === 'IDLE') {
        if (this.tLastEvent !== null && t - this.tLastEvent < o.cooldownMs) return null;
        if (mag > o.impactMag) {
          this.state = 'IMPACT';
          this.tImpact = t;
          this.hadFreefall = this.tFreefall !== null && t - this.tFreefall <= o.freefallWindowMs;
          this.gyroPeak = Math.max(...this.buf.filter(x => x[0] >= t - 1000).map(x => x[2]));
        }
        return null;
      }

      // state === 'IMPACT'
      if (t - this.tImpact <= 300) this.gyroPeak = Math.max(this.gyroPeak, gyro);
      if (t - this.tImpact < o.stillAfterMs) return null;
      const after = this.buf.filter(x => x[0] >= this.tImpact + 500).map(x => x[1]);
      this.state = 'IDLE';
      if (after.length >= 5) {
        const sd = std(after);
        if (sd < o.stillStd && (this.hadFreefall || this.gyroPeak >= o.gyroMin)) {
          this.tLastEvent = t;
          return {
            type: 'POSSIBLE_FALL', t, t_impact: this.tImpact,
            had_freefall: this.hadFreefall,
            gyro_peak: Math.round(this.gyroPeak * 100) / 100,
            still_std: Math.round(sd * 1000) / 1000,
          };
        }
      }
      return null;
    }
  }

  const api = { RuleDetector, std };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FallGuard = api;
})(typeof window !== 'undefined' ? window : globalThis);
