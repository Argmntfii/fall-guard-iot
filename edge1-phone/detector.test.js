// Uji state machine JS (cermin dari processor/tests/test_detector.py).
// Jalankan: node edge1-phone/detector.test.js
const assert = require('node:assert');
const { RuleDetector } = require('./detector.js');

const DT = 50;
const s = (t, mag, gyro = 0.5) => ({ t, mag, gyro });
const walking = (t0, secs) =>
  Array.from({ length: Math.floor(secs * 1000 / DT) }, (_, i) =>
    s(t0 + i * DT, 9.8 + 3 * Math.sin(2 * Math.PI * 2 * i * DT / 1000)));
const still = (t0, secs) =>
  Array.from({ length: Math.floor(secs * 1000 / DT) }, (_, i) => s(t0 + i * DT, 9.8 + (i % 2 ? 0.1 : 0), 0.1));
function fall(t0, { stillSecs = 4, freefall = true, impactGyro = 4 } = {}) {
  const out = []; let t = t0;
  if (freefall) for (let i = 0; i < 6; i++) { out.push(s(t, 1.5, 2.5)); t += DT; }
  out.push(s(t, 30, impactGyro)); t += DT;
  return out.concat(still(t, stillSecs));
}
function replay(seq, opts) {
  const d = new RuleDetector(opts);
  return seq.map(x => d.update(x.t, x.mag, x.gyro)).filter(Boolean);
}

let ev = replay(walking(0, 2).concat(fall(2000)));
assert.strictEqual(ev.length, 1, 'jatuh harus terdeteksi');
assert.strictEqual(ev[0].had_freefall, true);

assert.strictEqual(replay(walking(0, 15)).length, 0, 'jalan bukan jatuh');
assert.strictEqual(replay(walking(0, 2).concat(fall(2000, { stillSecs: 0 }), walking(2400, 6))).length, 0, 'lompat lalu jalan');
assert.strictEqual(replay(walking(0, 2).concat(fall(2000, { freefall: false, impactGyro: 0.2 }))).length, 0, 'benturan tanpa free-fall/rotasi');
assert.strictEqual(replay(walking(0, 2).concat(fall(2000, { freefall: false, impactGyro: 4 }))).length, 1, 'rotasi kuat saja cukup');

let seq = walking(0, 2).concat(fall(2000, { stillSecs: 2.5 }));
seq = seq.concat(fall(seq[seq.length - 1].t + DT, { stillSecs: 3 }));
assert.strictEqual(replay(seq).length, 1, 'cooldown');
assert.strictEqual(replay(seq, { cooldownMs: 0 }).length, 2, 'tanpa cooldown');

console.log('detector.js: semua uji lolos');
