# config.py
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore # <--- PASTIKAN BARIS INI ADA!

load_dotenv()

# Masukkan token bot Anda di sini
# PENTING: Untuk deployment, ini HARUS diatur sebagai variabel lingkungan (misalnya di Google Cloud Run)
# Untuk pengembangan lokal, gunakan file .env (dan pastikan .env ada di .gitignore!)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Tanpa nilai default yang sensitif

# Ganti dengan ID numerik channel/grup Anda
CHANNEL_ID = int(os.getenv("TELEGRAM_CHANNEL_ID", "0")) # Default ke 0 atau nilai non-fungsional jika tidak disetel

# ID numerik telegram user
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) # Default ke 0 atau nilai non-fungsional jika tidak disetel

# Jalur ke Firebase Service Account Key
    # Untuk lokal, pastikan file JSON ada di root folder proyek Anda.
FIREBASE_SERVICE_ACCOUNT_KEY_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH")

# ID numerik telegram user
APP_ID = os.getenv("APP_ID") # <--- Lebih baik tidak default ke "0" jika ini adalah string ID

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

# Konfigurasi Firebase
# Inisialisasi variabel app dan db di luar blok try agar selalu didefinisikan
app = None
db = None

# Konfigurasi Firebase
try:
    if not FIREBASE_SERVICE_ACCOUNT_KEY_PATH:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_KEY_PATH tidak ditemukan di .env")

    # Inisialisasi hanya jika belum diinisialisasi
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_KEY_PATH)
        app = firebase_admin.initialize_app(cred) # Assign the app instance
        print("Firebase berhasil diinisialisasi!")
    else:
        # If already initialized, get the default app instance
        app = firebase_admin.get_app()
        print("Firebase sudah diinisialisasi sebelumnya.")

    # Dapatkan klien Firestore
    db = firestore.client()
    print("Firestore client berhasil didapatkan.")

except Exception as e:
    print(f"ERROR: Gagal menginisialisasi Firebase atau Firestore: {e}")
    # Penting: re-raise error agar aplikasi berhenti jika inisialisasi gagal
    raise

# Tambahkan validasi dasar untuk APP_ID (opsional tapi disarankan)
if APP_ID is None:
    # Anda perlu menetapkan nilai default jika APP_ID tidak ada di .env
    # Atau, berikan peringatan keras/raise error jika ini kritis
    print("PERINGATAN: APP_ID tidak ditemukan. Harap setel variabel lingkungan 'APP_ID'.")
    # Contoh: APP_ID = "telegram-bot-markazalulum" # Jika Anda ingin hardcode untuk pengembangan
