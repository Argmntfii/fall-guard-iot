# Hasil Pengujian

Isi tabel ini dari pengujian nyata. Jatuh disimulasikan pada kasur/bantal, bukan pada orang.

## Kondisi uji
- HP Edge 1: *[tipe, posisi: saku celana / pinggang]*
- Broker: *[HiveMQ / EMQX]* · Jaringan: *[WiFi/hotspot]*
- Model: *[Random Forest, jumlah data latih: ... window dari ... file]*

## Skenario

| Skenario | Jumlah uji | Seharusnya | Terdeteksi (alert) | Ditolak processor | Catatan |
|---|---|---|---|---|---|
| Jatuh ke depan | 10 | alert | | | |
| Jatuh ke belakang | 10 | alert | | | |
| Jatuh ke samping | 10 | alert | | | |
| Jalan | 10 | tidak ada | | | |
| Duduk cepat | 10 | tidak ada | | | |
| Lompat | 10 | tidak ada | | | |
| Naik/turun tangga | 10 | tidak ada | | | |
| HP dijatuhkan ke meja | 10 | tidak ada | | | |

## Ringkasan

- Recall jatuh = terdeteksi / total jatuh = ...
- False positive per 100 aktivitas harian = ...
- Latensi (jatuh → alert di Edge 2/dashboard, diukur stopwatch/video) = ... detik
  (catatan: sistem menunggu ±2 detik setelah impact untuk memastikan HP diam)
- Confusion matrix data uji: `docs/confusion_matrix.png` (hasil `ml/train.py`)

## Temuan & perbaikan
- ...
