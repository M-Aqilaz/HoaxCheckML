import os
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ganti-ini-bebas"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    files = []
    for f in os.listdir(UPLOAD_FOLDER):
        path = os.path.join(UPLOAD_FOLDER, f)
        files.append({
            "name": f,
            "size": round(os.path.getsize(path) / 1024, 2)
        })
    return render_template("index.html", files=files)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("Tidak ada file yang dipilih.", "danger")
        return redirect(url_for("index"))

    file = request.files["file"]

    if file.filename == "":
        flash("Nama file kosong.", "danger")
        return redirect(url_for("index"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        flash(f"File '{filename}' berhasil diupload.", "success")
    else:
        flash("Format file tidak didukung. Gunakan .xlsx, .xls, atau .csv.", "danger")

    return redirect(url_for("index"))


@app.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        os.remove(path)
        flash(f"File '{filename}' berhasil dihapus.", "success")
    else:
        flash("File tidak ditemukan.", "danger")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)