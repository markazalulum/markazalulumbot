# config.py
import os

# Masukkan token bot Anda di sini
# PENTING: Untuk deployment, ini HARUS diatur sebagai variabel lingkungan (misalnya di Google Cloud Run)
# Untuk pengembangan lokal, gunakan file .env (dan pastikan .env ada di .gitignore!)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Tanpa nilai default yang sensitif

# Ganti dengan ID numerik channel/grup Anda
CHANNEL_ID = int(os.getenv("TELEGRAM_CHANNEL_ID", "0")) # Default ke 0 atau nilai non-fungsional jika tidak disetel

# ID numerik telegram user
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) # Default ke 0 atau nilai non-fungsional jika tidak disetel

# Tautan Zoom universal untuk semua pelajaran
UNIVERSAL_ZOOM_LINK = os.getenv(
    "UNIVERSAL_ZOOM_LINK",
    "https://example.com/zoom_link_placeholder" # Placeholder link
)

# Tautan Google Drive untuk materi dan rekaman
DRIVE_LINK = os.getenv(
    "DRIVE_LINK",
    "https://example.com/drive_link_placeholder" # Placeholder link
)

# Pesan percobaan untuk perintah /sendtest
MESSAGE_TEXT = os.getenv(
    "TELEGRAM_TEST_MESSAGE_TEXT",
    "Assalamu'alaikum warrahmatullahi wabarakatuh, Ini adalah pesan percobaan yang dikirim bot menggunakan file konfigurasi. Kredensial berhasil diimpor!"
)

# Tambahkan validasi dasar untuk token (opsional tapi disarankan)
if TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan. Harap setel variabel lingkungan atau dalam file .env.")

# Tambahkan validasi dasar untuk CHANNEL_ID (opsional tapi disarankan)
if CHANNEL_ID == 0:
    print("PERINGATAN: CHANNEL_ID tidak diatur atau disetel ke 0. Harap setel variabel lingkungan.")

# Tambahkan validasi dasar untuk ADMIN_USER_ID (opsional tapi disarankan)
if ADMIN_USER_ID == 0:
    print("PERINGATAN: ADMIN_USER_ID tidak diatur atau disetel ke 0. Harap setel variabel lingkungan.")

