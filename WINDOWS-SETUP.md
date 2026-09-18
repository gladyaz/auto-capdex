# Setup Windows 11 (Developer Mode)

Panduan ini untuk PC kantor Windows 11 yang meng-*clone* repository privat
`auto-capdex` dari GitHub, lalu menjalankan pipeline subtitle secara bulk.

Kalau kamu cuma menerima folder project dalam bentuk zip (tanpa Git), lompat
langsung ke **Langkah 6**.

---

## Langkah 1 — Install Python 3.12 (x64)

1. Buka https://www.python.org/downloads/windows/
2. Download **Windows installer (64-bit)** untuk **Python 3.12**
3. **PENTING:** saat installer jalan, centang **"Add python.exe to PATH"**
   sebelum klik Install

> Python 3.12 adalah versi yang dipakai dan sudah diuji untuk pipeline ini.

## Langkah 2 — Verifikasi Python

Buka **Command Prompt** (tekan Start, ketik `cmd`, Enter), lalu jalankan:

```bat
python --version
py --version
```

Keduanya harus menampilkan `Python 3.12.x`. Kalau `python` tidak dikenali,
Python belum masuk PATH — ulangi Langkah 1 dan pastikan checkbox-nya dicentang.

## Langkah 3 — Install Git

1. Download dari https://git-scm.com/download/win
2. Install dengan opsi default
3. Verifikasi:

```bat
git --version
```

## Langkah 4 — Install FFmpeg dan FFprobe

Buka **PowerShell**, lalu jalankan:

```powershell
winget install ffmpeg
```

Tutup PowerShell setelah selesai, lalu **buka Command Prompt baru** supaya PATH
yang baru terbaca.

## Langkah 5 — Verifikasi FFmpeg dan FFprobe

```bat
ffmpeg -version
ffprobe -version
```

**Dua-duanya wajib ada.** `ffprobe` dipakai untuk memvalidasi setiap video
input dan setiap video output. Kalau `ffprobe` tidak ada di PATH, semua video
akan di-skip dan hasilnya kosong.

## Langkah 6 — Clone Repository

`auto-capdex` adalah repository **privat**, jadi Git akan meminta login GitHub
(pakai browser atau Personal Access Token).

```bat
cd %USERPROFILE%\Documents
git clone https://github.com/gladyaz/auto-capdex.git
```

## Langkah 7 — Masuk ke Folder Project

```bat
cd auto-capdex
```

Semua langkah berikutnya dijalankan dari folder ini (root repository).

## Langkah 8 — Jalankan setup.bat

Double-click **`setup.bat`** di File Explorer, atau dari Command Prompt:

```bat
setup.bat
```

Script ini otomatis:

- mengecek Python ada di PATH dan menampilkan versinya
- mengecek `ffmpeg` dan `ffprobe` ada di PATH
- membuat virtual environment di `.venv`
- meng-install semua dependency dari `requirements.txt`

> **Tidak perlu bikin virtualenv manual.** `setup.bat` sudah menanganinya.
> Tunggu sampai muncul `Setup complete!`.

## Langkah 9 — Taruh Folder Drama di input/

Buat satu subfolder per drama di dalam `input\`, isi dengan file `.mp4` dan
poster/cover-nya:

```text
input\
  143-老公突然有了读心术\
    001.mp4
    002.mp4
    poster.jpg
```

Format gambar yang ikut disalin: `.jpg`, `.jpeg`, `.png`, `.webp`.

> Isi folder `input\` tidak pernah di-commit ke Git, dan file sumber tidak
> pernah diubah atau di-rename oleh pipeline.

## Langkah 10 — Jalankan run.bat

Double-click **`run.bat`**, lalu tekan sembarang tombol untuk mulai.

Proses per episode: ekstrak audio → transkrip Mandarin → terjemah ke Indonesia
→ buat `.srt` → burn subtitle ke video.

## Langkah 11 — Kalau Batch Terputus, Pakai resume.bat

Kalau ada video yang gagal (biasanya internet putus sesaat saat translate),
double-click **`resume.bat`**. Script ini membaca `output\job_state.json` dan
**hanya mengulang video yang gagal** — tidak memproses ulang semua dari awal.

## Langkah 12 — Hasilnya Ada di output/

Folder `output\` dibuat otomatis oleh pipeline saat pertama jalan, jadi wajar
kalau folder itu belum ada setelah clone.

Nama folder drama di `output\` diterjemahkan ke judul Indonesia, sementara
folder sumbernya tetap dalam bahasa Mandarin:

```text
input\                                output\
  143-老公突然有了读心术\        ->     143-Suamiku Tiba-Tiba Bisa Membaca Pikiran\
    001.mp4                              001.srt
    002.mp4                              001_subtitled.mp4
    poster.jpg                           002.srt
                                         002_subtitled.mp4
                                         poster.jpg
```

Prefix nomor (`4-`, `143-`) dipertahankan, jumlah episode seperti `（85集）`
menjadi `(85 Episode)`, dan poster disalin apa adanya tanpa diubah.

Selain folder drama, `output\` juga berisi:

- `processing.log` — log per job
- `failed_jobs.txt` — ringkasan video yang gagal
- `job_state.json` — state untuk `resume.bat`
- `batch_report.json` — ringkasan batch + mapping nama folder

## Langkah 13 — Run Pertama Akan Download Model

Saat pertama kali jalan, `faster-whisper` otomatis **men-download model
transkripsi** (ukuran `small`, beberapa ratus MB) ke cache user:

```text
%USERPROFILE%\.cache\huggingface\hub
```

Jadi run pertama terasa lama dan **butuh internet**. Run berikutnya memakai
model dari cache. Model ini tidak pernah masuk ke Git.

## Langkah 14 — Ubah Setting (Opsional)

Buka `config.yaml` pakai Notepad untuk mengubah font subtitle, ukuran model
transkripsi, jumlah proses paralel, dll. Setelah disimpan, jalankan `run.bat`
lagi.

---

## Troubleshooting

| Gejala | Penyebab & Solusi |
|---|---|
| `python tidak dikenali` | Python belum di PATH. Install ulang, centang "Add python.exe to PATH". |
| Semua video di-skip | `ffprobe` tidak ada di PATH. Jalankan `winget install ffmpeg`, buka Command Prompt baru. |
| `FFmpeg executable not found` | Sama seperti di atas. |
| Banyak video gagal saat translate | Koneksi internet putus-putus. Jalankan `resume.bat`. |
| Run pertama lama sekali | Normal — sedang download model faster-whisper (Langkah 13). |
| Judul Mandarin tampil rusak di Command Prompt | Kosmetik saja, tidak mempengaruhi hasil. Jalankan `chcp 65001` sebelum `run.bat` kalau mau rapi. |
