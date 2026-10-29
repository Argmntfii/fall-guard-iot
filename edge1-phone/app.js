/* Edge 1: HP membaca accelerometer + gyroscope (DeviceMotion), memproses di HP,
 * lalu publish ke MQTT lewat WebSocket. Tidak ada data simulasi: bila sensor tidak ada,
 * halaman hanya memberi peringatan. */
(() => {
  const { RuleDetector } = window.FallGuard;
  const $ = id => document.getElementById(id);
  const G = 9.81;
  const SEND_MS = 50; // 20 Hz
  const FIELDS = ['project', 'broker', 'impact', 'freefall', 'stillStd', 'gyroMin'];

  let client = null, detector = null, wakeLock = null, running = false;
  let counters = { motion: 0, valid: 0, sent: 0, events: 0 };
  let cand = null, lastTick = 0, watchdog = null;

  const log = msg => {
    const el = $('log');
    el.textContent = `${new Date().toLocaleTimeString()}  ${msg}\n` + el.textContent.slice(0, 3000);
  };

  function loadConfig() {
    try {
      const q = new URLSearchParams(location.search);
      FIELDS.forEach(k => {
        const v = q.get(k) || localStorage.getItem('fg_' + k);
        if (v) $(k).value = v;
      });
    } catch (e) { /* storage bisa diblokir; abaikan */ }
  }
  function saveConfig() {
    try { FIELDS.forEach(k => localStorage.setItem('fg_' + k, $(k).value)); } catch (e) { /* abaikan */ }
  }

  const topic = s => `fallguard/${$('project').value.trim()}/${s}`;

  function connect() {
    client = mqtt.connect($('broker').value.trim(), {
      clientId: 'fg-edge1-' + Math.random().toString(16).slice(2, 8),
      reconnectPeriod: 2000,
      will: { topic: topic('edge1/status'), payload: 'offline', retain: true },
    });
    client.on('connect', () => {
      $('conn').textContent = 'MQTT: terhubung';
      client.publish(topic('edge1/status'), 'online', { retain: true });
      log('MQTT terhubung');
    });
    client.on('reconnect', () => { $('conn').textContent = 'MQTT: menyambung ulang...'; });
    client.on('error', e => log('MQTT error: ' + e.message));
    client.on('offline', () => { $('conn').textContent = 'MQTT: offline'; });
  }

  async function start() {
    if (running) return;
    if (!$('project').value.trim() || $('project').value.trim() === 'ganti-dengan-id-unik') {
      log('Isi PROJECT_ID dulu (harus sama dengan processor & dashboard).');
      return;
    }
    saveConfig();
    // iOS: izin sensor harus diminta dari gesture (klik tombol).
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
      try {
        if (await DeviceMotionEvent.requestPermission() !== 'granted') { log('Izin sensor ditolak.'); return; }
      } catch (e) { log('Gagal meminta izin sensor: ' + e.message); return; }
    }
    detector = new RuleDetector({
      impactMag: +$('impact').value, freefallMag: +$('freefall').value,
      stillStd: +$('stillStd').value, gyroMin: +$('gyroMin').value,
    });
    counters = { motion: 0, valid: 0, sent: 0, events: 0 };
    cand = null; lastTick = 0;
    connect();
    try { wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { log('Wake Lock tidak tersedia; jaga layar tetap menyala.'); }
    window.addEventListener('devicemotion', onMotion);
    running = true;
    $('start').disabled = true; $('stop').disabled = false;
    log('Mulai membaca sensor');
    watchdog = setTimeout(() => {
      if (counters.valid === 0) log('PERINGATAN: tidak ada data accelerometer/gyroscope. Pakai HP, HTTPS, dan izinkan sensor gerak.');
    }, 3000);
  }

  function stop() {
    window.removeEventListener('devicemotion', onMotion);
    clearTimeout(watchdog);
    if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
    if (client) {
      client.publish(topic('edge1/status'), 'offline', { retain: true });
      client.end();
      client = null;
    }
    running = false;
    $('start').disabled = false; $('stop').disabled = true;
    $('conn').textContent = 'MQTT: berhenti';
    log('Berhenti');
  }

  function onMotion(e) {
    counters.motion++;
    const a = e.accelerationIncludingGravity, r = e.rotationRate;
    if (!a || a.x == null || a.y == null || a.z == null || !r || r.alpha == null) return;
    counters.valid++;
    const mag = Math.hypot(a.x, a.y, a.z);                              // m/s^2
    const gyro = Math.hypot(r.alpha, r.beta, r.gamma) * Math.PI / 180;  // rad/s
    const now = Date.now();

    // Decimation 20 Hz: pilih sampel dengan simpangan terbesar dari 1 g
    // supaya lonjakan impact dan dip free-fall tidak hilang.
    if (!cand || Math.abs(mag - G) > Math.abs(cand.mag - G)) {
      cand = { t: now, ax: a.x, ay: a.y, az: a.z, mag, gyro };
    }
    if (now - lastTick < SEND_MS) return;
    lastTick = now;
    const smp = cand; cand = null;

    const ev = detector.update(smp.t, smp.mag, smp.gyro);
    const win = detector.buf;
    const rms = Math.sqrt(win.reduce((s, x) => s + x[1] * x[1], 0) / win.length);
    if (client && client.connected) {
      client.publish(topic('edge1/sensor'), JSON.stringify({
        device: 'edge1', t: smp.t,
        ax: +smp.ax.toFixed(3), ay: +smp.ay.toFixed(3), az: +smp.az.toFixed(3),
        mag: +smp.mag.toFixed(3), gyro: +smp.gyro.toFixed(3), rms: +rms.toFixed(3),
        state: detector.state,
      }));
      counters.sent++;
      if (ev) {
        client.publish(topic('edge1/event'), JSON.stringify({ device: 'edge1', ...ev }));
        counters.events++;
        log('POSSIBLE_FALL dikirim ke processor');
      }
    }
    render(smp, rms);
  }

  function render(smp, rms) {
    $('mag').textContent = smp.mag.toFixed(2);
    $('gyro').textContent = smp.gyro.toFixed(2);
    $('rms').textContent = rms.toFixed(2);
    $('state').textContent = detector.state;
    $('cMotion').textContent = counters.motion;
    $('cValid').textContent = counters.valid;
    $('cSent').textContent = counters.sent;
    $('cEvents').textContent = counters.events;
  }

  loadConfig();
  $('start').addEventListener('click', start);
  $('stop').addEventListener('click', stop);
})();
