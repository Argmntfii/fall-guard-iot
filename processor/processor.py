"""Processor di laptop (Data Processing #2 + AI).

Alur:
  edge1/sensor  -> disimpan di buffer per device (8 detik)
  edge1/event   -> (HP mendeteksi POSSIBLE_FALL lewat state machine)
                   -> ambil window 4 detik di sekitar impact
                   -> ekstraksi fitur + Random Forest (ml/model.pkl)
                      atau, jika model belum ada, replay RuleDetector
                   -> publish `alert` bila dikonfirmasi, `processor/log` untuk keduanya

Jalankan:  python processor.py
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque

import config
from detector import WINDOW_AFTER_MS, WINDOW_BEFORE_MS, confirm

MODEL = None
buffers: dict[str, deque] = defaultdict(deque)


def load_model(path=config.MODEL_PATH):
    if os.path.exists(path):
        import joblib
        print(f"[processor] model ML dimuat: {os.path.abspath(path)}")
        return joblib.load(path)
    print("[processor] model.pkl belum ada -> memakai konfirmasi berbasis aturan (rule).")
    return None


def _publish(client, name, payload, retain=False):
    client.publish(config.topic(name), json.dumps(payload), qos=0, retain=retain)


def handle_sensor(device, data):
    buf = buffers[device]
    buf.append(data)
    while buf and data["t"] - buf[0]["t"] > config.BUFFER_SECONDS * 1000:
        buf.popleft()


def handle_event(client, device, ev, model=None):
    """Putuskan apakah POSSIBLE_FALL dari HP benar-benar jatuh. Return dict alert atau None."""
    if ev.get("type") != "POSSIBLE_FALL" or "t_impact" not in ev:
        return None
    t_imp = ev["t_impact"]
    window = [
        s for s in buffers[device]
        if t_imp - WINDOW_BEFORE_MS <= s["t"] <= t_imp + WINDOW_AFTER_MS + 200
    ]
    started = time.time()
    if model is None or len(window) < 20:
        is_fall, conf, source = True, None, "edge-only"
    else:
        is_fall, conf, source = confirm(window, model, config.CONFIRM_THRESHOLD)
    # if len(window) < 20:
    #     is_fall, conf, source = True, None, "edge-only"   # data kurang -> percaya HP
    # else:
    #     is_fall, conf, source = confirm(window, model, config.CONFIRM_THRESHOLD)
    ms = round((time.time() - started) * 1000, 1)

    log = {"device": device, "t_impact": t_imp, "samples": len(window), "source": source,
           "confidence": conf, "decision": "FALL" if is_fall else "REJECTED"}
    _publish(client, "processor/log", log)
    print(f"[processor] {device}: {log['decision']} (source={source}, conf={conf}, n={len(window)})")
    if not is_fall:
        return None

    alert = {"device": device, "type": "FALL", "t_impact": t_imp,
             "t_alert": int(time.time() * 1000), "confidence": conf,
             "source": source, "samples": len(window), "processing_ms": ms}
    _publish(client, "alert", alert)
    return alert


def main():
    import paho.mqtt.client as mqtt

    global MODEL
    MODEL = load_model()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION_2, client_id=f"fg-processor-{os.getpid()}")
    client.will_set(config.topic("processor", "status"), "offline", retain=True)

    def on_connect(c, userdata, flags, reason_code, properties=None):
        print(f"[processor] terhubung ke {config.BROKER_HOST}:{config.BROKER_PORT} ({reason_code})")
        c.subscribe(config.topic("+", "sensor"))
        c.subscribe(config.topic("+", "event"))
        c.publish(config.topic("processor", "status"), "online", retain=True)

    def on_message(c, userdata, msg):
        parts = msg.topic.split("/")          # fallguard / ID / device / kind
        if len(parts) != 4:
            return
        device, kind = parts[2], parts[3]
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        if kind == "sensor" and "mag" in data and "t" in data:
            handle_sensor(device, data)
        elif kind == "event":
            handle_event(c, device, data, MODEL)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT, keepalive=30)
    print(f"[processor] project={config.PROJECT_ID}  (Ctrl+C untuk berhenti)")
    client.loop_forever()


if __name__ == "__main__":
    main()
