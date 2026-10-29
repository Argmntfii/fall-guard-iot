"""Latih Random Forest dari CSV di ml/data/ dan simpan ke ml/model.pkl.

  python train.py                 # pakai ml/data
  python train.py --data folder   # folder lain

Kelas ditentukan dari awalan nama file: fall* = jatuh (1), adl* = bukan jatuh (0).
  * File "adl": window 4 detik digeser tiap 1 detik.
  * File "fall": window 4 detik yang berpusat di puncak magnitude (2 detik sebelum +
    2 detik sesudah impact), plus 4 geseran kecil (+-150/300 ms) sebagai augmentasi.
    Rekam minimal ~3 detik sebelum dan ~3 detik sesudah jatuh.
Evaluasi memisahkan data uji per FILE (~25% file tiap kelas) agar window yang tumpang
tindih tidak bocor antara data latih dan uji.
"""
import argparse
import csv
import glob
import json
import os
import sys

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "processor"))
from detector import FEATURE_NAMES, WINDOW_AFTER_MS, WINDOW_BEFORE_MS, extract_features  # noqa: E402

SIZE = WINDOW_BEFORE_MS + WINDOW_AFTER_MS
MIN_SAMPLES = 20


def load_csv(path):
    with open(path) as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


def cut(samples, start, end):
    return [s for s in samples if start <= s["t"] < end]


def windows_adl(samples, step=1000):
    out, t0, t1 = [], samples[0]["t"], samples[-1]["t"]
    s = t0
    while s + SIZE <= t1:
        w = cut(samples, s, s + SIZE)
        if len(w) >= MIN_SAMPLES:
            out.append(w)
        s += step
    return out


def windows_fall(samples):
    peak = max(samples, key=lambda x: x["mag"])
    out = []
    for off in (-300, -150, 0, 150, 300):
        end = peak["t"] + WINDOW_AFTER_MS + off
        start = end - SIZE
        if start < samples[0]["t"] or end > samples[-1]["t"] + 1:
            continue
        w = cut(samples, start, end + 1)
        if len(w) >= MIN_SAMPLES:
            out.append(w)
    return out


def build(data_dir):
    X, y, groups, names = [], [], [], []
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    for gi, path in enumerate(files):
        base = os.path.basename(path)
        label = 1 if base.startswith("fall") else 0 if base.startswith("adl") else None
        if label is None:
            print(f"  lewati {base} (nama harus diawali fall/adl)")
            continue
        samples = load_csv(path)
        if len(samples) < MIN_SAMPLES:
            print(f"  lewati {base} (sampel terlalu sedikit)")
            continue
        wins = windows_fall(samples) if label else windows_adl(samples)
        if not wins:
            print(f"  lewati {base} (tidak ada window valid; rekaman terlalu pendek?)")
            continue
        for w in wins:
            X.append(extract_features(w)); y.append(label); groups.append(gi)
        names.append(base)
    return np.array(X), np.array(y), np.array(groups), names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "model.pkl"))
    ap.add_argument("--plot", default=os.path.join(HERE, "..", "docs", "confusion_matrix.png"))
    args = ap.parse_args()

    X, y, groups, names = build(args.data)
    if len(y) == 0 or len(set(y)) < 2:
        sys.exit("Butuh data kedua kelas (fall* dan adl*). Rekam dulu dengan record.py.")
    n_fall_files = len({g for g, l in zip(groups, y) if l == 1})
    n_adl_files = len({g for g, l in zip(groups, y) if l == 0})
    print(f"{len(y)} window dari {len(names)} file  (file fall={n_fall_files}, adl={n_adl_files}, "
          f"window fall={int(y.sum())}, adl={int((y == 0).sum())})")

    def new_model():
        return RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42)

    report = None
    if n_fall_files >= 4 and n_adl_files >= 4:
        # Pisahkan per FILE, ~25% file tiap kelas jadi data uji (kedua kelas pasti ada di uji).
        rng = np.random.RandomState(42)
        test_groups = set()
        for cls in (0, 1):
            gs = sorted({g for g, l in zip(groups, y) if l == cls})
            rng.shuffle(gs)
            test_groups |= set(gs[:max(1, round(0.25 * len(gs)))])
        te = np.where(np.isin(groups, list(test_groups)))[0]
        tr = np.where(~np.isin(groups, list(test_groups)))[0]
        if len(set(y[tr])) == 2 and len(set(y[te])) == 2:
            m = new_model().fit(X[tr], y[tr])
            pred = m.predict(X[te])
            cm = confusion_matrix(y[te], pred, labels=[0, 1])
            print("\nConfusion matrix (baris=aktual, kolom=prediksi; 0=bukan jatuh, 1=jatuh)\n", cm)
            print(classification_report(y[te], pred, target_names=["bukan jatuh", "jatuh"], zero_division=0))
            report = classification_report(y[te], pred, target_names=["bukan jatuh", "jatuh"],
                                           zero_division=0, output_dict=True)
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(4, 3.4))
                ax.imshow(cm, cmap="Blues")
                for (i, j), v in np.ndenumerate(cm):
                    ax.text(j, i, int(v), ha="center", va="center")
                ax.set_xticks([0, 1], ["bukan jatuh", "jatuh"]); ax.set_yticks([0, 1], ["bukan jatuh", "jatuh"])
                ax.set_xlabel("prediksi"); ax.set_ylabel("aktual"); ax.set_title("Confusion matrix (data uji)")
                fig.tight_layout()
                os.makedirs(os.path.dirname(args.plot), exist_ok=True)
                fig.savefig(args.plot, dpi=150)
                print(f"Gambar confusion matrix: {os.path.abspath(args.plot)}")
            except ImportError:
                print("matplotlib tidak ada; gambar dilewati.")
        else:
            print("Split uji tidak memuat kedua kelas; evaluasi dilewati. Tambah rekaman.")
    else:
        print("PERINGATAN: data terlalu sedikit untuk evaluasi (perlu >= 4 file fall dan >= 4 file adl).")

    model = new_model().fit(X, y)   # model akhir memakai semua data
    joblib.dump(model, args.out)
    imp = sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda x: -x[1])
    print("\nPentingnya fitur:", ", ".join(f"{n}={v:.2f}" for n, v in imp))
    with open(os.path.join(os.path.dirname(args.out), "model_info.json"), "w") as f:
        json.dump({"features": FEATURE_NAMES, "windows": int(len(y)), "files": names,
                   "report": report}, f, indent=2)
    print(f"Model tersimpan: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
