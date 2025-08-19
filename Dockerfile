# Gunakan Python 3.9 slim sebagai base image. Slim lebih kecil dan cepat.
FROM python:3.9-slim

# Tetapkan direktori kerja di dalam container
WORKDIR /app

# Salin file requirements.txt ke direktori kerja
# Ini dilakukan terlebih dahulu untuk memanfaatkan caching Docker jika requirements tidak berubah
COPY requirements.txt .

# Install semua dependensi Python yang dibutuhkan
# `--no-cache-dir` untuk menghemat ruang, `-r` untuk menginstal dari requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh isi direktori lokal Anda (kecuali yang diabaikan oleh .dockerignore, jika ada)
# ke direktori kerja di dalam container.
# Ini termasuk main.py dan file-file kode lainnya.
COPY . .

# Karena kita menggunakan variabel lingkungan dari .env, kita tidak akan menyalin .env
# ke dalam container Docker. Sebagai gantinya, variabel lingkungan akan disuntikkan
# saat deployment di Cloud Run.

# Exposed port untuk aplikasi Anda. Cloud Run akan mengarahkan traffic ke port ini.
# Pastikan ini sesuai dengan port yang didengarkan oleh aplikasi Python Anda.
EXPOSE 8080

# Command untuk menjalankan aplikasi Anda saat container dimulai.
# Cloud Run akan menjalankan perintah ini.
# Pastikan ini sesuai dengan cara Anda menjalankan bot Anda.
# Perhatikan bahwa kami tidak menyertakan `python main.py` di CMD, karena dalam konteks bot,
# biasanya ada framework atau skrip yang akan memulai polling atau webhook.
# Jika bot Anda menggunakan webhook dan Anda menjalankan Flask/FastAPI, CMD akan terlihat beda.
# Asumsi: Bot Anda akan diinisialisasi dan mulai berfungsi saat `main.py` dijalankan.
CMD ["python", "main.py"]