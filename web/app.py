import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename

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
    app.run(debug=True)