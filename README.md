# HoaxCheckML

HoaxCheckML adalah proyek Product Based Learning untuk mendeteksi dan mengklasifikasikan potensi berita hoaks dalam bahasa Indonesia. Proyek ini menggabungkan eksperimen Machine Learning di Jupyter Notebook, engine analisis teks berbasis NLP, scraper RSS berita valid, serta dashboard web berbasis Flask.

> Hasil dari aplikasi ini merupakan alat bantu awal. Keputusan final tetap perlu diverifikasi melalui kanal resmi dan pengecekan fakta dari sumber kredibel.

## Fitur

- **Deteksi teks**: menganalisis judul atau isi klaim dan menghasilkan label `HOAKS` atau `VALID`.
- **Skor confidence**: menampilkan tingkat keyakinan hasil prediksi.
- **Bukti model**: menampilkan kata-kata yang mendukung klasifikasi hoaks maupun valid.
- **Pola linguistik**: mendeteksi ajakan menyebarkan pesan, urgensi palsu, tautan tidak resmi, atribusi lembaga formal, dan tanda baca emosional berlebih.
- **Simulasi pipeline**: memperlihatkan tahapan cleaning, tokenisasi, pencocokan kosakata, bobot kata, dan kalibrasi skor.
- **Benchmark model**: menampilkan perbandingan akurasi, precision, recall, F1-score, latensi, penggunaan memori, dan confusion matrix.
- **Scraper RSS**: mengambil berita terkini dari Antara, CNN Indonesia, dan CNBC Indonesia.
- **Manajemen dataset**: mengunggah, mempratinjau, mengunduh, dan menghapus file `.csv`, `.xls`, atau `.xlsx`.

## Cara Kerja

Dataset hoaks dimuat dari `data/komdigi_hoaks.csv`, sedangkan berita valid berasal dari file terbaru di `web/uploads/`. Sistem kemudian:

1. Membersihkan teks dari URL, HTML, tanda baca, dan label kebocoran data.
2. Mengubah teks menjadi lowercase dan melakukan tokenisasi.
3. Menghitung bobot log-likelihood kata berdasarkan frekuensi pada kedua kelas.
4. Menambahkan bobot dari pola linguistik manipulatif.
5. Mengonversi skor agregat menjadi probabilitas melalui sigmoid.
6. Menentukan label berdasarkan probabilitas akhir.

Engine aktif saat ini berada di [web/ml_detector.py](web/ml_detector.py).

## Struktur Proyek

```text
HoaxCheckML/
├── data/                                 # Dataset utama
│   └── komdigi_hoaks.csv                 # Dataset judul berita hoaks Komdigi
├── dokumentasi/                          # Dokumentasi visual dan figur evaluasi model
│   ├── gambar_f1_contoh_sampel.png       # Visualisasi contoh sampel data
│   └── gambar_f2_confusion_matrix.png    # Matriks konfusi hasil pengujian model
├── notebooks/                            # Seluruh eksperimen Jupyter Notebook
│   ├── 01_klasifikasi/                   # Eksperimen awal (KNN, Naive Bayes, SVM)
│   ├── 02_pengujian_supervised/          # Pengujian komprehensif model supervised (KNN, LR, NB, RF, SVM)
│   ├── 03_clustering_study_case/         # Eksperimen clustering kasus nyata (K-Means, DBSCAN, HDBSCAN)
│   ├── 04_clustering_uts/                # Eksperimen clustering UTS (Hierarchical, HDBSCAN)
│   └── 05_transformer/                   # IndoBERT transfer learning & fine-tuning
├── scripts/                              # Skrip utilitas dan otomasi dokumen
│   └── generate_dokumen_perencanaan.py   # Generator workbook perencanaan PBL
├── web/                                  # Aplikasi web Flask & RESTful API
│   ├── app.py                            # Entrypoint Flask dan route modular
│   ├── ml_detector.py                    # Inference engine ML & analisis linguistik
│   ├── cms_service.py                    # Layanan CMS dan sinkronisasi konten
│   ├── supabase_service.py               # Integrasi database cloud Supabase
│   ├── requirements.txt                  # Dependensi aplikasi web
│   ├── models/                           # Bobot model terlatih (.pkl & .json)
│   ├── static/                           # Aset statis frontend (CSS, JS, logo, favicon)
│   ├── templates/                        # Template antarmuka web (Jinja2)
│   └── uploads/                          # Dataset validasi scraping RSS & riwayat unggah
├── .gitignore
└── README.md
```

## Persyaratan

- Python 3.10 atau lebih baru
- Internet aktif untuk scraper RSS
- Browser modern

## Instalasi

### 1. Masuk ke folder proyek

```powershell
cd "D:\Kuliah\Kelas\Semester 5\Product Based Learning\HoaxCheckML"
```

### 2. Buat dan aktifkan virtual environment

```powershell
py -m venv web\.venv
.\web\.venv\Scripts\Activate.ps1
```

Jika PowerShell menolak eksekusi script, aktifkan policy untuk sesi terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\web\.venv\Scripts\Activate.ps1
```

### 3. Instal dependensi

```powershell
python -m pip install --upgrade pip
pip install -r web\requirements.txt
```

Untuk menjalankan notebook eksperimen, instal dependensi tambahan sesuai kebutuhan notebook:

```powershell
pip install jupyter notebook scikit-learn hdbscan scipy matplotlib seaborn
```

## Menjalankan Aplikasi

Jalankan Flask dari root proyek:

```powershell
python web\app.py
```

Buka:

```text
http://127.0.0.1:5000
```

Server juga dapat dijalankan agar dapat diakses pada jaringan lokal:

```text
http://<alamat-ip-komputer>:5000
```

## Halaman Dashboard

- `/` - Data Hub, pengelolaan dataset, dan scraper RSS.
- `/detector` - Deteksi teks berita atau klaim.
- `/pipeline` - Visualisasi dan simulasi pipeline pemrosesan.
- `/benchmark` - Ringkasan perbandingan model.
- `/admin` - Dashboard Admin Manajemen Data Cloud Supabase (Tips Literasi, Panduan & Checklist, Tentang HoaxCheck, Laporan Masalah/Bug, dan Broadcast Notifikasi).

## Endpoint API

### Prediksi teks

```http
POST /api/predict
Content-Type: application/json
```

Contoh body:

```json
{
  "text": "Segera viralkan dan bagikan sebelum tautan ini dihapus!",
  "model": "bernoulli"
}
```

### Simulasi pipeline

```http
POST /api/pipeline/simulate
Content-Type: application/json
```

Contoh body:

```json
{
  "text": "Kementerian resmi mengumumkan kebijakan baru.",
  "model": "bernoulli"
}
```

### Daftar metadata model

```http
GET /api/pipeline/models
```

Semua endpoint prediksi juga dapat menerima parameter form melalui `application/x-www-form-urlencoded`.

## Dataset

### Dataset hoaks

Lokasi: [data/komdigi_hoaks.csv](data/komdigi_hoaks.csv)

Dataset berisi 4.176 baris dan menggunakan kolom `title` sebagai sumber teks hoaks. Kolom data lain mencakup URL, slug, tanggal publikasi, kategori, tag, topik, dan cuplikan berita.

### Dataset valid

Lokasi: [web/uploads](web/uploads)

Dataset valid dihasilkan oleh scraper RSS dengan kolom:

```text
id, source, title, excerpt, url, published_at, label
```

Saat proses scraping berhasil, hasil disimpan sebagai `berita_valid_<timestamp>.csv` dan diperbarui menjadi `berita_valid_terbaru.csv`.

## Eksperimen Machine Learning

Folder notebook menyediakan eksperimen untuk:

- Supervised: KNN, Naive Bayes Bernoulli/Gaussian/Multinomial, dan SVM.
- Metrik jarak: Euclidean, Cosine, dan Manhattan.
- Clustering: K-Means, DBSCAN, HDBSCAN, dan Hierarchical.
- Perbandingan performa model dan visualisasi hasil eksperimen.

Hasil benchmark pada halaman `/benchmark` merupakan metadata evaluasi riset yang disimpan di [web/app.py](web/app.py). Tidak semua model pada notebook direplikasi sebagai engine inference aktif di halaman deteksi.

## Skrip Dokumen Perencanaan

Untuk menghasilkan workbook perencanaan dan fitur:

```powershell
python scripts\generate_dokumen_perencanaan.py
```

Output `Dokumen Perencanaan - HoaxCheck.xlsx` disebabkan oleh `.gitignore` tidak akan dilacak oleh Git.

## Pengembangan

Saat mengubah engine deteksi, perhatikan file berikut:

- [web/ml_detector.py](web/ml_detector.py): preprocessing, bobot kata, dan prediksi.
- [web/app.py](web/app.py): route, API, scraping, unggah file, dan metadata benchmark.
- [web/templates](web/templates): tampilan dashboard, detector, pipeline, dan benchmark.

Usahakan setiap perubahan memperbarui README jika tersedia endpoint, dependensi, data, atau alur penggunaan yang berubah.