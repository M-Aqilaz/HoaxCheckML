import os
import re
import json
import time
import pickle
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_from_directory, jsonify, session
)
from werkzeug.utils import secure_filename
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import BernoulliNB
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

app = Flask(__name__)
app.secret_key = "hoaxcheck-secret-key-pbl5"

# Kredensial Login Admin
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MODEL_DIR = os.path.join(BASE_DIR, "models")
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MODEL_DIR"] = MODEL_DIR
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

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


# -------------------------------------------------------------
# AUTHENTICATION DECORATOR
# -------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Silakan masuk terlebih dahulu untuk mengakses sistem.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r'\[(HOAKS|DISINFORMASI|MISINFORMASI|KLARIFIKASI|SALAH|FALSE)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\((HOAKS|DISINFORMASI|MISINFORMASI|KLARIFIKASI|SALAH|FALSE)\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?:\/\/\S+|www\.\S+', '', text)
    text = re.sub(r'<.*?>', '', text)
    text = re.sub(r'[^a-zA-Z\s]', ' ', text)
    return re.sub(r'\s+', ' ', text.lower()).strip()


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


def get_file_list():
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for f in sorted(os.listdir(UPLOAD_FOLDER)):
            path = os.path.join(UPLOAD_FOLDER, f)
            if os.path.isfile(path) and not f.startswith("."):
                files.append(get_file_info(path))
    return files


def get_model_info():
    meta_path = os.path.join(MODEL_DIR, "model_metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def extract_text_series(df):
    cols = [c.lower() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}
    
    if "title" in cols and "excerpt" in cols:
        return (df[col_map["title"]].fillna("") + " " + df[col_map["excerpt"]].fillna("")).apply(clean_text)
    elif "title" in cols and "content" in cols:
        return (df[col_map["title"]].fillna("") + " " + df[col_map["content"]].fillna("")).apply(clean_text)
    elif "title" in cols:
        return df[col_map["title"]].fillna("").apply(clean_text)
    elif "teks" in cols:
        return df[col_map["teks"]].fillna("").apply(clean_text)
    elif "text" in cols:
        return df[col_map["text"]].fillna("").apply(clean_text)
    elif "berita" in cols:
        return df[col_map["berita"]].fillna("").apply(clean_text)
    elif "narasi" in cols:
        return df[col_map["narasi"]].fillna("").apply(clean_text)
    else:
        str_cols = df.select_dtypes(include=["object"]).columns
        if len(str_cols) > 0:
            return df[str_cols[0]].fillna("").apply(clean_text)
        return pd.Series([""] * len(df))


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
            except Exception:
                pass

    return articles


# -------------------------------------------------------------
# AUTH ROUTES (LOGIN & LOGOUT)
# -------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dataset_view"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            flash("Selamat datang kembali, Admin!", "success")
            return redirect(url_for("dataset_view"))
        else:
            flash("Username atau password salah. Silakan coba lagi.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda telah berhasil keluar (logout).", "info")
    return redirect(url_for("login"))


# -------------------------------------------------------------
# MODULAR FEATURE ROUTES (DATASET, SCRAPER, TRAIN)
# -------------------------------------------------------------

@app.route("/")
def index():
    tab = request.args.get("tab")
    if tab == "scraper":
        return redirect(url_for("scraper_view"))
    elif tab == "train":
        return redirect(url_for("train_view"))
    return redirect(url_for("dataset_view"))


@app.route("/dataset")
@login_required
def dataset_view():
    files = get_file_list()
    model_info = get_model_info()
    return render_template("dataset.html", files=files, model_info=model_info, active_page="dataset")


@app.route("/scraper")
@login_required
def scraper_view():
    files = get_file_list()
    model_info = get_model_info()
    return render_template("scraper.html", files=files, model_info=model_info, active_page="scraper")


@app.route("/train", methods=["GET", "POST"])
@login_required
def train_view():
    if request.method == "POST":
        hoax_file = request.form.get("hoax_file")
        valid_file = request.form.get("valid_file")

        if not hoax_file or not valid_file:
            flash("Silakan pilih file Hoaks dan file Valid terlebih dahulu.", "danger")
            return redirect(url_for("train_view"))

        hoax_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(hoax_file))
        valid_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(valid_file))

        if not os.path.exists(hoax_path) or not os.path.exists(valid_path):
            flash("Salah satu file dataset tidak ditemukan di sistem.", "danger")
            return redirect(url_for("train_view"))

        try:
            # 1. Pemuatan Data
            df_hoax = pd.read_csv(hoax_path, on_bad_lines="skip") if hoax_file.endswith(".csv") else pd.read_excel(hoax_path)
            df_valid = pd.read_csv(valid_path, on_bad_lines="skip") if valid_file.endswith(".csv") else pd.read_excel(valid_path)

            df_hoax["teks_bersih"] = extract_text_series(df_hoax)
            df_valid["teks_bersih"] = extract_text_series(df_valid)

            df_hoax["label"] = 1
            df_valid["label"] = 0

            df_hoax = df_hoax[df_hoax["teks_bersih"].str.len() > 10].reset_index(drop=True)
            df_valid = df_valid[df_valid["teks_bersih"].str.len() > 10].reset_index(drop=True)

            if len(df_hoax) == 0 or len(df_valid) == 0:
                flash("Dataset tidak memiliki teks valid yang mencukupi untuk dilatih.", "danger")
                return redirect(url_for("train_view"))

            # 2. Penyeimbangan Kelas 1:1
            min_samples = min(len(df_hoax), len(df_valid))
            df_hoax_sampled = df_hoax.sample(n=min_samples, random_state=42)
            df_valid_sampled = df_valid.sample(n=min_samples, random_state=42)
            df_all = pd.concat([df_hoax_sampled, df_valid_sampled], ignore_index=True)

            # 3. Split 80:20 Terstratifikasi
            X_train, X_test, y_train, y_test = train_test_split(
                df_all["teks_bersih"], df_all["label"],
                test_size=0.2, random_state=42, stratify=df_all["label"]
            )

            # 4. TF-IDF
            tfidf = TfidfVectorizer(max_features=1500, ngram_range=(1, 2))
            X_train_vec = tfidf.fit_transform(X_train)
            X_test_vec = tfidf.transform(X_test)

            # 5. Model Bernoulli Naive Bayes
            start_time = time.time()
            model = BernoulliNB(alpha=1.0, binarize=0.0)
            model.fit(X_train_vec, y_train)
            y_pred = model.predict(X_test_vec)
            duration = round(time.time() - start_time, 4)

            # 6. Evaluasi Metrik
            acc = round(accuracy_score(y_test, y_pred) * 100, 2)
            prec = round(precision_score(y_test, y_pred, average="macro", zero_division=0) * 100, 2)
            rec = round(recall_score(y_test, y_pred, average="macro", zero_division=0) * 100, 2)
            f1 = round(f1_score(y_test, y_pred, average="macro", zero_division=0) * 100, 2)

            # 7. Simpan Model & Metadata
            with open(os.path.join(MODEL_DIR, "model_bernoulli.pkl"), "wb") as f:
                pickle.dump(model, f)

            with open(os.path.join(MODEL_DIR, "tfidf_vectorizer.pkl"), "wb") as f:
                pickle.dump(tfidf, f)

            metadata = {
                "algorithm": "Bernoulli Naive Bayes",
                "accuracy": acc,
                "precision": prec,
                "recall": rec,
                "f1_score": f1,
                "duration_seconds": duration,
                "total_samples": len(df_all),
                "hoax_samples": min_samples,
                "valid_samples": min_samples,
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "hoax_file": hoax_file,
                "valid_file": valid_file,
                "trained_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            }

            with open(os.path.join(MODEL_DIR, "model_metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)

            flash(
                f"🎉 Model Bernoulli Naive Bayes berhasil dilatih! Akurasi: {acc}%, F1-Score: {f1}% (dari {len(df_all)} data seimbang). Siap dipakai di Web & Mobile API!",
                "success"
            )
        except Exception as e:
            flash(f"Gagal melatih model: {str(e)}", "danger")

        return redirect(url_for("train_view"))

    # GET request
    files = get_file_list()
    model_info = get_model_info()
    return render_template("train.html", files=files, model_info=model_info, active_page="train")


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "file" not in request.files:
        flash("Tidak ada file yang dipilih.", "danger")
        return redirect(url_for("dataset_view"))

    file = request.files["file"]
    if file.filename == "":
        flash("Nama file kosong.", "danger")
        return redirect(url_for("dataset_view"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        flash(f"File '{filename}' berhasil diunggah.", "success")
    else:
        flash("Format file tidak didukung. Gunakan .xlsx, .xls, atau .csv.", "danger")

    return redirect(url_for("dataset_view"))


@app.route("/scrape", methods=["POST"])
@login_required
def scrape():
    source_choice = request.form.get("source", "all")
    limit = request.form.get("limit", "200")

    articles = scrape_valid_news(source_choice=source_choice, limit=limit)
    if not articles:
        flash("Gagal mengambil berita dari portal yang dipilih.", "danger")
        return redirect(url_for("scraper_view"))

    df = pd.DataFrame(articles)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"berita_valid_{timestamp}.csv"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    df.to_csv(filepath, index=False, encoding="utf-8")

    latest_path = os.path.join(app.config["UPLOAD_FOLDER"], "berita_valid_terbaru.csv")
    if os.path.exists(latest_path):
        try:
            df_old = pd.read_csv(latest_path)
            df_combined = pd.concat([df_old, df], ignore_index=True)
            if "url" in df_combined.columns:
                df_combined = df_combined.drop_duplicates(subset=["url"], keep="last")
            elif "title" in df_combined.columns:
                df_combined = df_combined.drop_duplicates(subset=["title"], keep="last")
            df_combined["id"] = range(1, len(df_combined) + 1)
            df_combined.to_csv(latest_path, index=False, encoding="utf-8")
            total_latest = len(df_combined)
        except Exception:
            df.to_csv(latest_path, index=False, encoding="utf-8")
            total_latest = len(df)
    else:
        df.to_csv(latest_path, index=False, encoding="utf-8")
        total_latest = len(df)

    flash(
        f"Berhasil men-scrape {len(df)} berita! Tersimpan di '{filename}' dan digabungkan ke 'berita_valid_terbaru.csv' (Total sekarang: {total_latest} berita).",
        "success"
    )
    return redirect(url_for("scraper_view"))


@app.route("/predict", methods=["POST"])
@login_required
def predict():
    input_text = request.form.get("text", "").strip()
    if not input_text:
        flash("Teks berita tidak boleh kosong.", "warning")
        return redirect(url_for("train_view"))

    model_path = os.path.join(MODEL_DIR, "model_bernoulli.pkl")
    tfidf_path = os.path.join(MODEL_DIR, "tfidf_vectorizer.pkl")

    if not os.path.exists(model_path) or not os.path.exists(tfidf_path):
        flash("Model belum dilatih. Silakan klik tombol 'Mulai Training Sekarang' terlebih dahulu.", "danger")
        return redirect(url_for("train_view"))

    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        with open(tfidf_path, "rb") as f:
            tfidf = pickle.load(f)

        t_clean = clean_text(input_text)
        t_vec = tfidf.transform([t_clean])
        pred = model.predict(t_vec)[0]
        prob = model.predict_proba(t_vec)[0]

        status = "HOAKS" if pred == 1 else "VALID"
        confidence = round(prob[pred] * 100, 1)

        result_msg = f"Hasil Deteksi: [{status}] dengan Tingkat Keyakinan {confidence}%"
        flash(result_msg, "info")
    except Exception as e:
        flash(f"Gagal melakukan inferensi: {e}", "danger")

    return redirect(url_for("train_view"))


@app.route("/preview/<filename>")
@login_required
def preview_file(filename):
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
    if not os.path.exists(filepath):
        flash("File tidak ditemukan.", "danger")
        return redirect(url_for("dataset_view"))

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(filepath, nrows=10, on_bad_lines="skip")
        else:
            df = pd.read_excel(filepath, nrows=10)

        columns = list(df.columns)
        records = df.to_dict(orient="records")
        return render_template("preview.html", filename=filename, columns=columns, rows=records, total_preview=len(df))
    except Exception as e:
        flash(f"Gagal membaca file untuk preview: {e}", "danger")
        return redirect(url_for("dataset_view"))


@app.route("/download/<filename>")
@login_required
def download_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], secure_filename(filename), as_attachment=True)


@app.route("/delete/<filename>", methods=["POST"])
@login_required
def delete(filename):
    path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
    if os.path.exists(path):
        os.remove(path)
        flash(f"File '{filename}' berhasil dihapus.", "success")
    else:
        flash("File tidak ditemukan.", "danger")
    return redirect(url_for("dataset_view"))


# -------------------------------------------------------------
# REST API ENDPOINT PUBLIK UNTUK FLUTTER MOBILE (NO COOKIE REQUIRED)
# -------------------------------------------------------------

@app.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json(silent=True) or request.form
    text = data.get("text", "").strip() if data else ""

    if not text:
        return jsonify({
            "status": "error",
            "message": "Field 'text' tidak boleh kosong."
        }), 400

    model_path = os.path.join(MODEL_DIR, "model_bernoulli.pkl")
    tfidf_path = os.path.join(MODEL_DIR, "tfidf_vectorizer.pkl")

    if not os.path.exists(model_path) or not os.path.exists(tfidf_path):
        return jsonify({
            "status": "error",
            "message": "Model belum dilatih di server."
        }), 503

    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        with open(tfidf_path, "rb") as f:
            tfidf = pickle.load(f)

        t_clean = clean_text(text)
        t_vec = tfidf.transform([t_clean])
        pred = int(model.predict(t_vec)[0])
        prob = model.predict_proba(t_vec)[0]

        prediction_label = "HOAKS" if pred == 1 else "VALID"
        confidence = round(float(prob[pred]) * 100, 2)

        return jsonify({
            "status": "success",
            "prediction": prediction_label,
            "label": pred,
            "confidence": confidence,
            "model": "Bernoulli Naive Bayes"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)
