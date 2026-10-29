"""Rekam data sensor berlabel dari HP (Edge 1) untuk training model.

Contoh:
  python record.py fall_depan --seconds 10      # lakukan SATU jatuh (simulasi di kasur) di tengah rekaman
  python record.py adl_jalan --seconds 20
  python record.py adl_duduk --seconds 10
  python record.py adl_lompat --seconds 15

Aturan nama: awalan "fall" = kelas jatuh, awalan "adl" = aktivitas harian (bukan jatuh).
Hasil: ml/data/<nama>_<timestamp>.csv
Sebelum merekam: HP harus sudah Mulai di halaman Edge 1 dengan PROJECT_ID yang sama.
"""
import argparse
import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "processor"))
import config  # noqa: E402

COLUMNS = ["t", "ax", "ay", "az", "mag", "gyro"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label", help="mis. fall_depan, adl_jalan")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--out", default=os.path.join(HERE, "data"))
    args = ap.parse_args()
    if not args.label.startswith(("fall", "adl")):
        sys.exit('Nama harus diawali "fall" atau "adl".')

    import paho.mqtt.client as mqtt

    rows = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION_2, client_id=f"fg-rec-{os.getpid()}")

    def on_connect(c, u, f, rc, p=None):
        c.subscribe(config.topic("edge1", "sensor"))

    def on_message(c, u, msg):
        try:
            d = json.loads(msg.payload)
            rows.append([d[k] for k in COLUMNS])
        except (ValueError, KeyError):
            pass

    client.on_connect, client.on_message = on_connect, on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT)
    client.loop_start()
    for i in (3, 2, 1):
        print(f"Mulai dalam {i}...", flush=True)
        time.sleep(1)
    print(f"MEREKAM '{args.label}' selama {args.seconds:.0f} detik", flush=True)
    rows.clear()
    time.sleep(args.seconds)
    client.loop_stop()
    client.disconnect()

    if len(rows) < 20:
        sys.exit("Data terlalu sedikit. Pastikan HP sudah Mulai dan PROJECT_ID sama.")
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{args.label}_{int(time.time())}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"Tersimpan: {path} ({len(rows)} sampel)")


if __name__ == "__main__":
    main()
