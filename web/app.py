import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from werkzeug.utils import secure_filename

try:
    from web.ml_detector import detector_engine
except ImportError:
    from ml_detector import detector_engine

app = Flask(__name__)
app.secret_key = "hoaxcheck-secret-key-pbl5"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Sumber Berita Valid Terpercaya (RSS Resmi)
RSS_SOURCES = {
    "antara": {
        "name": "Antara News (Kantor Berita Negara)",
        "feeds": [
            "https://www.antaranews.com/rss/terkini.xml",
            "https://www.antaranews.com/rss/politik.xml",
            "https://www.antaranews.com/rss/hukum.xml",
            "https://www.antaranews.com/rss/ekonomi.xml",
            "https://www.antaranews.com/rss/tekno.xml",
            "https://www.antaranews.com/rss/humaniora.xml"
        ]
    },
    "cnn": {
        "name": "CNN Indonesia",
        "feeds": [
            "https://www.cnnindonesia.com/nasional/rss",
            "https://www.cnnindonesia.com/teknologi/rss",
            "https://www.cnnindonesia.com/ekonomi/rss"
        ]
    },
    "cnbc": {
        "name": "CNBC Indonesia",
        "feeds": [
            "https://www.cnbcindonesia.com/news/rss",
            "https://www.cnbcindonesia.com/market/rss",
            "https://www.cnbcindonesia.com/tech/rss"
        ]
    }
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_info(filepath):
    size_kb = round(os.path.getsize(filepath) / 1024, 2)
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%d-%m-%Y %H:%M")
    row_count = "-"

    filename = os.path.basename(filepath)
    if filename.endswith(".csv"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                row_count = sum(1 for _ in f) - 1
                row_count = max(0, row_count)
        except Exception:
            row_count = "-"
    elif filename.endswith((".xlsx", ".xls")):
        row_count = "Excel"

    return {
        "name": filename,
        "size": size_kb,
        "modified": mtime,
        "rows": row_count
    }


def scrape_valid_news(source_choice="all", limit=200):
    articles = []
    seen_titles = set()

    sources_to_scrape = {}
    if source_choice == "all":
        sources_to_scrape = RSS_SOURCES
    elif source_choice in RSS_SOURCES:
        sources_to_scrape = {source_choice: RSS_SOURCES[source_choice]}

    for src_key, src_data in sources_to_scrape.items():
        src_name = src_data["name"]
        for feed_url in src_data["feeds"]:
            if limit != "all" and len(articles) >= int(limit):
                break
            try:
                req = urllib.request.Request(
                    feed_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, timeout=7) as resp:
                    root = ET.fromstring(resp.read())
                    for item in root.findall(".//item"):
                        if limit != "all" and len(articles) >= int(limit):
                            break

                        title_el = item.find("title")
                        link_el = item.find("link")
                        desc_el = item.find("description")
                        date_el = item.find("pubDate")

                        title = title_el.text.strip() if title_el is not None and title_el.text else ""
                        link = link_el.text.strip() if link_el is not None and link_el.text else ""
                        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                        pub_date = date_el.text.strip() if date_el is not None and date_el.text else ""

                        clean_desc = re.sub(r"<[^>]+>", "", desc).strip()

                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            articles.append({
                                "id": len(articles) + 1,
                                "source": src_name,
                                "title": title,
                                "excerpt": clean_desc,
                                "url": link,
                                "published_at": pub_date,
                                "label": "valid"
                            })
            except Exception as e:
                pass

    return articles


# -------------------------------------------------------------
# WEB ROUTES
# -------------------------------------------------------------

@app.route("/")
def index():
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for f in sorted(os.listdir(UPLOAD_FOLDER)):
            path = os.path.join(UPLOAD_FOLDER, f)
            if os.path.isfile(path) and not f.startswith("."):
                files.append(get_file_info(path))

    active_tab = request.args.get("tab", "dataset")

    return render_template(
        "index.html",
        files=files,
        active_tab=active_tab
    )


@app.route("/detector")
def detector():
    return render_template("detector.html")


@app.route("/benchmark")
def benchmark():
    return render_template("benchmark.html")


# Master metadata evaluasi riset ML (9 Model Supervised)
PIPELINE_MODELS_DATA = {
    "NB_Bernoulli": {
        "name": "Bernoulli Naive Bayes",
        "category": "Probabilistic (Binarized Occurrence)",
        "accuracy": 92.33,
        "precision_macro": 0.9264,
        "recall_macro": 0.9233,
        "f1_macro": 0.9232,
        "f1_weighted": 0.9232,
        "latency_sec": 0.0075,
        "latency_ms": 7.5,
        "memory_mb": 0.39,
        "cm": {"tn": 155, "fp": 21, "fn": 6, "tp": 170, "total": 352},
        "description": "Model klasifikasi terbaik dengan akurasi 92.33%. Sangat unggul karena hanya memeriksa kemunculan biner kata provokatif (ada/tidak ada) tanpa terdistorsi panjang berita.",
        "badge": "Champion PBL",
        "rank": 1
    },
    "NB_Multinomial": {
        "name": "Multinomial Naive Bayes",
        "category": "Probabilistic (Word Frequency / TF-IDF)",
        "accuracy": 89.20,
        "precision_macro": 0.8921,
        "recall_macro": 0.8920,
        "f1_macro": 0.8920,
        "f1_weighted": 0.8920,
        "latency_sec": 0.0118,
        "latency_ms": 11.8,
        "memory_mb": 0.15,
        "cm": {"tn": 158, "fp": 18, "fn": 20, "tp": 156, "total": 352},
        "description": "Menggunakan frekuensi kemunculan kata atau bobot TF-IDF. Sangat hemat memori (0.15 MB), cocok untuk server berspesifikasi minimalis.",
        "badge": "Paling Hemat RAM",
        "rank": 2
    },
    "SVM_Cosine": {
        "name": "SVM Kernel Linear (Cosine Similarity)",
        "category": "Geometric Margin (Linear)",
        "accuracy": 89.00,
        "precision_macro": 0.8902,
        "recall_macro": 0.8900,
        "f1_macro": 0.8900,
        "f1_weighted": 0.8900,
        "latency_sec": 0.8499,
        "latency_ms": 849.9,
        "memory_mb": 0.88,
        "cm": {"tn": 135, "fp": 15, "fn": 18, "tp": 132, "total": 300},
        "description": "Menemukan hyperplane pemisah optimal dengan sudut kosinus antar-vektor TF-IDF. Margin generalisasi sangat stabil.",
        "badge": "Optimal Linear",
        "rank": 3
    },
    "SVM_Euclidean": {
        "name": "SVM Kernel RBF (Euclidean Distance)",
        "category": "Geometric Margin (Non-Linear RBF)",
        "accuracy": 89.00,
        "precision_macro": 0.8909,
        "recall_macro": 0.8900,
        "f1_macro": 0.8899,
        "f1_weighted": 0.8899,
        "latency_sec": 1.4132,
        "latency_ms": 1413.2,
        "memory_mb": 0.88,
        "cm": {"tn": 137, "fp": 13, "fn": 20, "tp": 130, "total": 300},
        "description": "Memetakan fitur teks ke dimensi tak terhingga menggunakan fungsi Radial Basis Function (RBF). Akurasi setara Cosine namun waktu latih lebih lama.",
        "badge": "Kernel RBF",
        "rank": 4
    },
    "NB_Gaussian": {
        "name": "Gaussian Naive Bayes",
        "category": "Probabilistic (Normal Continuous)",
        "accuracy": 86.65,
        "precision_macro": 0.8685,
        "recall_macro": 0.8665,
        "f1_macro": 0.8663,
        "f1_weighted": 0.8663,
        "latency_sec": 0.0452,
        "latency_ms": 45.2,
        "memory_mb": 36.32,
        "cm": {"tn": 146, "fp": 30, "fn": 17, "tp": 159, "total": 352},
        "description": "Mengasumsikan distribusi fitur kontinu kontinyu gaussian. Menghabiskan RAM lebih banyak (36.3 MB) karena matriks kovarian padat.",
        "badge": "Distribusi Gaussian",
        "rank": 5
    },
    "KNN_Euclidean": {
        "name": "KNN Euclidean Distance (k=5)",
        "category": "Instance-Based Distance",
        "accuracy": 83.00,
        "precision_macro": 0.8333,
        "recall_macro": 0.8300,
        "f1_macro": 0.8296,
        "f1_weighted": 0.8296,
        "latency_sec": 0.0213,
        "latency_ms": 21.3,
        "memory_mb": 5.73,
        "cm": {"tn": 117, "fp": 33, "fn": 18, "tp": 132, "total": 300},
        "description": "Mengkalkulasi jarak lurus Euclidean antar titik data teks. Mengalami penurunan efektivitas pada ruang berdimensi tinggi (sparse vector).",
        "badge": "Jarak Euclidean",
        "rank": 6
    },
    "KNN_Cosine": {
        "name": "KNN Cosine Distance (k=5)",
        "category": "Instance-Based Angle",
        "accuracy": 82.39,
        "precision_macro": 0.8300,
        "recall_macro": 0.8239,
        "f1_macro": 0.8230,
        "f1_weighted": 0.8230,
        "latency_sec": 0.0346,
        "latency_ms": 34.6,
        "memory_mb": 9.68,
        "cm": {"tn": 134, "fp": 42, "fn": 20, "tp": 156, "total": 352},
        "description": "Menghitung sudut orientasi kemiripan teks. Cukup tangguh namun memerlukan pencarian tetangga ke seluruh dataset saat prediksi.",
        "badge": "Sudut Cosine",
        "rank": 7
    },
    "SVM_Manhattan": {
        "name": "SVM Kernel Laplacian (Manhattan Distance)",
        "category": "Geometric Margin (Laplacian)",
        "accuracy": 80.00,
        "precision_macro": 0.8571,
        "recall_macro": 0.8000,
        "f1_macro": 0.7917,
        "f1_weighted": 0.7917,
        "latency_sec": 1.8937,
        "latency_ms": 1893.7,
        "memory_mb": 21.98,
        "cm": {"tn": 150, "fp": 0, "fn": 60, "tp": 90, "total": 300},
        "description": "Menggunakan metrik Cityblock L1 distance. Cenderung bias ke kelas mayoritas dan lambat saat komputasi kernel matriks.",
        "badge": "Jarak L1",
        "rank": 8
    },
    "KNN_Manhattan": {
        "name": "KNN Manhattan Distance (k=5)",
        "category": "Instance-Based L1",
        "accuracy": 50.00,
        "precision_macro": 0.2500,
        "recall_macro": 0.5000,
        "f1_macro": 0.3333,
        "f1_weighted": 0.3333,
        "latency_sec": 0.0504,
        "latency_ms": 50.4,
        "memory_mb": 0.27,
        "cm": {"tn": 0, "fp": 150, "fn": 0, "tp": 150, "total": 300},
        "description": "Gagal total dalam menggeneralisasi data teks berdimensi 1,500 (Akurasi 50% = tebakan acak), akibat fenomena 'Curse of Dimensionality'.",
        "badge": "Terkendala Dimensi",
        "rank": 9
    }
}


@app.route("/pipeline")
def pipeline():
    # Statistik Preprocessing & Top Discriminative Words
    sorted_hoax = [
        {"word": k, "weight": round(v, 2)}
        for k, v in sorted(detector_engine.log_weights.items(), key=lambda x: x[1], reverse=True)[:15]
    ]
    sorted_valid = [
        {"word": k, "weight": round(abs(v), 2), "raw_weight": round(v, 2)}
        for k, v in sorted(detector_engine.log_weights.items(), key=lambda x: x[1])[:15]
    ]

    stats = {
        "total_hoax_raw": detector_engine.total_hoax_samples or 4176,
        "total_valid_raw": detector_engine.total_valid_samples or 878,
        "balanced_total": (detector_engine.total_valid_samples or 878) * 2,
        "train_samples": int((detector_engine.total_valid_samples or 878) * 2 * 0.8),
        "test_samples": int((detector_engine.total_valid_samples or 878) * 2 * 0.2),
        "vocab_size": detector_engine.vocab_size or 3006,
        "avg_raw_len": 65.6,
        "avg_clean_len": 56.2,
        "noise_reduction_pct": 14.3
    }

    return render_template(
        "pipeline.html",
        models_data=PIPELINE_MODELS_DATA,
        stats=stats,
        sorted_hoax=sorted_hoax,
        sorted_valid=sorted_valid
    )


@app.route("/api/pipeline/simulate", methods=["POST", "OPTIONS"])
def api_pipeline_simulate():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "POST,OPTIONS")
        return response, 200

    data = request.get_json(silent=True) or {}
    text = data.get("text") or request.form.get("text", "")
    model_name = data.get("model") or request.form.get("model", "bernoulli")

    result = detector_engine.simulate_pipeline(text, model_name=model_name)
    response = jsonify(result)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@app.route("/api/pipeline/models", methods=["GET"])
def api_pipeline_models():
    return jsonify(PIPELINE_MODELS_DATA)


@app.route("/api/predict", methods=["POST", "OPTIONS"])
def api_predict():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "POST,OPTIONS")
        return response, 200

    data = request.get_json(silent=True) or {}
    text = data.get("text") or request.form.get("text", "")
    model_name = data.get("model") or request.form.get("model", "bernoulli")
    
    result = detector_engine.predict(text, model_name=model_name)
    response = jsonify(result)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("Tidak ada file yang dipilih.", "danger")
        return redirect(url_for("index", tab="dataset"))

    file = request.files["file"]
    if file.filename == "":
        flash("Nama file kosong.", "danger")
        return redirect(url_for("index", tab="dataset"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        flash(f"File '{filename}' berhasil diunggah.", "success")
    else:
        flash("Format file tidak didukung. Gunakan .xlsx, .xls, atau .csv.", "danger")

    return redirect(url_for("index", tab="dataset"))


@app.route("/scrape", methods=["POST"])
def scrape():
    source_choice = request.form.get("source", "all")
    limit = request.form.get("limit", "200")

    articles = scrape_valid_news(source_choice=source_choice, limit=limit)
    if not articles:
        flash("Gagal mengambil berita dari portal yang dipilih.", "danger")
        return redirect(url_for("index", tab="scraper"))

    df = pd.DataFrame(articles)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"berita_valid_{timestamp}.csv"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    df.to_csv(filepath, index=False, encoding="utf-8")

    latest_path = os.path.join(app.config["UPLOAD_FOLDER"], "berita_valid_terbaru.csv")
    df.to_csv(latest_path, index=False, encoding="utf-8")

    flash(
        f"Berhasil men-scrape {len(df)} berita valid! Tersimpan di '{filename}' & 'berita_valid_terbaru.csv'.",
        "success"
    )
    return redirect(url_for("index", tab="scraper"))


@app.route("/preview/<filename>")
def preview_file(filename):
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
    if not os.path.exists(filepath):
        flash("File tidak ditemukan.", "danger")
        return redirect(url_for("index", tab="dataset"))

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(filepath, nrows=10)
        else:
            df = pd.read_excel(filepath, nrows=10)

        columns = list(df.columns)
        records = df.to_dict(orient="records")
        return render_template("preview.html", filename=filename, columns=columns, rows=records, total_preview=len(df))
    except Exception as e:
        flash(f"Gagal membaca file untuk preview: {e}", "danger")
        return redirect(url_for("index", tab="dataset"))


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], secure_filename(filename), as_attachment=True)


@app.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
    if os.path.exists(path):
        os.remove(path)
        flash(f"File '{filename}' berhasil dihapus.", "success")
    else:
        flash("File tidak ditemukan.", "danger")
    return redirect(url_for("index", tab="dataset"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)