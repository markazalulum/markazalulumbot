import logging
from dotenv import load_dotenv
load_dotenv() # Memuat variabel dari .env
from datetime import datetime, timedelta
import pytz
import re
import json
import os
import config
from config import db, firebase_admin # Pastikan Anda mengimpor 'db' dari config.py
from config import TOKEN, CHANNEL_ID, ADMIN_USER_ID, UNIVERSAL_ZOOM_LINK, DRIVE_LINK, MESSAGE_TEXT, FIREBASE_SERVICE_ACCOUNT_KEY_PATH, APP_ID
from firebase_admin import credentials, initialize_app
from firebase_admin import firestore # <-- Ini yang Anda butuhkan
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, constants, BotCommand, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
# Setup logging untuk melihat setiap aksi bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Mute httpx warnings
logger = logging.getLogger(__name__) # Definisi logger di sini

# --- Konfigurasi Bot (Membaca dari file config.py) ---
TOKEN = config.TOKEN
ADMIN_USER_ID = config.ADMIN_USER_ID
UNIVERSAL_ZOOM_LINK = config.UNIVERSAL_ZOOM_LINK
DRIVE_LINK = config.DRIVE_LINK

# Kamus untuk menerjemahkan nama hari dari bahasa Inggris ke Indonesia
hari_mapping = {
    "monday": "Senin",
    "tuesday": "Selasa",
    "wednesday": "Rabu",
    "thursday": "Kamis",
    "friday": "Jumat",
    "saturday": "Sabtu",
    "sunday": "Ahad"
}

# Jadwal pelajaran untuk setiap hari.
jadwal_path = 'jadwal.json'

try:
    with open(jadwal_path, 'r', encoding='utf-8') as f:
        jadwal_pelajaran = json.load(f)
except FileNotFoundError:
    logging.error(
        f"File '{jadwal_path}' tidak ditemukan. Pastikan file tersebut ada di direktori yang benar."
    )
    jadwal_pelajaran = {}
except json.JSONDecodeError:
    logging.error(
        f"Terjadi kesalahan saat membaca file '{jadwal_path}'. Pastikan formatnya benar."
    )
    jadwal_pelajaran = {}

# --- Fungsi kustom untuk meng-escape MarkdownV2 ---
def escape_markdown_v2(text: str) -> str:
    """Fungsi untuk meng-escape semua karakter khusus MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', str(text))


# --- FUNGSI PEMBANTU (Refactoring) ---
async def send_or_edit_message(update: Update,
                               text: str,
                               reply_markup: InlineKeyboardMarkup = None):
    """
    Fungsi pembantu untuk mengirim pesan baru atau mengedit pesan yang sudah ada
    berdasarkan jenis pembaruan (pesan teks atau klik tombol).
    """
    try:
        # Menangani kasus ketika update adalah CallbackQuery
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.edit_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
        # Menangani kasus ketika update adalah Message (misal dari command langsung)
        elif update.message:
            await update.message.reply_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
        else:
            logging.warning(
                "send_or_edit_message called without valid update.message or update.callback_query.message."
            )
    except Exception as e:
        logging.error(f"Gagal mengirim atau mengedit pesan: {e}")
        # Fallback: jika edit gagal (misal pesan terlalu lama atau sudah diedit), coba kirim pesan baru
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(
                "Maaf, terjadi kesalahan saat memproses permintaan Anda, mungkin pesan terlalu lama untuk diedit. Berikut hasilnya sebagai pesan baru:",
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=None # Tanpa markup untuk fallback ini
            )
            # Kirim pesan asli yang gagal diedit sebagai pesan baru
            await update.callback_query.message.reply_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
        elif update.message:
            await update.message.reply_text(
                "Maaf, terjadi kesalahan saat memproses permintaan Anda.")
        logging.error(f"Error dalam send_or_edit_message: {e}", exc_info=True)


async def send_message_to_channel(message_text: str,
                                   reply_markup: InlineKeyboardMarkup = None):
    """
    Fungsi ini menginisialisasi bot dan mengirimkan pesan ke channel
    yang sudah ditentukan dalam config.CHANNEL_ID.
    """
    try:
        bot = Bot(token=config.TOKEN) # Buat instance bot menggunakan token dari config.TOKEN
        await bot.send_message(
            chat_id=config.CHANNEL_ID, # Menggunakan CHANNEL_ID dari config.py
            text=message_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
            disable_web_page_preview=True # Mematikan preview link agar tampilan pesan lebih rapi
        )
        logging.info("Pesan berhasil dikirim ke channel.")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan ke channel: {e}", exc_info=True)

# --- FUNGSI BARU UNTUK MENERIMA UMPAN BALIK ---
async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Meminta pengguna untuk mengirim umpan balik setelah perintah /feedback."""
    user = update.effective_user
    logger.info(f"Perintah /feedback diterima dari {user.id} ({user.full_name})")
        
    await update.message.reply_text(
        "Silakan ketik umpan balik atau pertanyaan Anda setelah pesan ini. Saya akan meneruskannya kepada pengembang. Terima kasih!"
        "\n\nUntuk membatalkan, kirim /cancel."
    )
    # Menyetel status pengguna agar pesan berikutnya ditangani sebagai umpan balik
    context.user_data['state'] = 'awaiting_feedback'

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menerima dan menyimpan umpan balik dari pengguna ke Firestore."""
    user = update.effective_user
    user_id = str(user.id)
        
    # Periksa apakah pengguna sedang dalam status menunggu umpan balik
    if context.user_data.get('state') == 'awaiting_feedback':
        feedback_text = update.message.text
        logger.info(f"Umpan balik diterima dari {user.id} ({user.full_name}): {feedback_text[:50]}...") # Log 50 karakter pertama

        try:
            # Dapatkan APP_ID dari config.py juga jika Anda ingin menggunakannya
            # from config import APP_ID # Tambahkan ini jika APP_ID tidak diakses secara global di sini
            # Contoh penggunaan APP_ID (pastikan APP_ID diatur di config.py)
            app_id_from_config = firebase_admin._apps['[DEFAULT]'].name if firebase_admin._apps else 'default-app-id' # Menggunakan nama aplikasi default atau fallback# DEBUGGING: Cetak APP_ID yang digunakan
            logger.debug(f"Menggunakan APP_ID: {app_id_from_config}")# Path ke koleksi umpan balik: artifacts/{APP_ID}/public/data/feedback
            # Ini akan membuat dokumen baru untuk setiap umpan balik
            feedback_collection_ref = db.collection(f'artifacts/{app_id_from_config}/public/data/feedback')
                
            feedback_data = {
                'user_id': user_id,
                'username': user.full_name or user.username,
                'feedback_text': feedback_text,
                'received_at': firestore.SERVER_TIMESTAMP,
                'status': 'new' # Status awal umpan balik
            }
                
            feedback_collection_ref.add(feedback_data) # Gunakan add() untuk membuat dokumen baru secara otomatis
                
            await update.message.reply_text(
                "Terima kasih atas umpan balik Anda! Pesan Anda telah berhasil diterima dan akan kami tinjau."
            )
            logger.info(f"Umpan balik dari {user.id} berhasil disimpan ke Firestore.")

            # Opsional: Kirim notifikasi ke admin
            if ADMIN_USER_ID and ADMIN_USER_ID != 0:
                try:
                    admin_message = (
                        f"**Umpan Balik Baru Diterima!**\n\n"
                        f"**Dari:** {user.full_name or user.username} (`{user_id}`)\n"
                        f"**Umpan Balik:** {feedback_text}"
                    )
                    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='Markdown')
                    logger.info(f"Notifikasi umpan balik dikirim ke admin {ADMIN_USER_ID}.")
                except Exception as admin_e:
                    logger.error(f"Gagal mengirim notifikasi umpan balik ke admin {ADMIN_USER_ID}: {admin_e}", exc_info=True)

        except Exception as e:
            logger.error(f"Gagal menyimpan umpan balik dari {user.id}: {e}", exc_info=True)
            await update.message.reply_text(
                "Maaf, terjadi kesalahan saat menyimpan umpan balik Anda. Mohon coba lagi nanti."
            )
            
        # Reset status pengguna setelah umpan balik diterima
        del context.user_data['state']
    # Jika bukan dalam status awaiting_feedback, biarkan MessageHandler lain menanganinya
    # atau lewati (pass) jika ini adalah satu-satunya MessageHandler
    else:
        return

async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Membatalkan proses pengiriman umpan balik."""
    if context.user_data.get('state') == 'awaiting_feedback':
        del context.user_data['state']
        await update.message.reply_text("Pengiriman umpan balik dibatalkan.")
        logger.info(f"Pengiriman umpan balik dibatalkan oleh {update.effective_user.id}.")
    else:
        await update.message.reply_text("Anda tidak sedang dalam mode pengiriman umpan balik.")

# --- FUNGSI SCHEDULER (untuk pengingat otomatis) ---
# --- FUNGSI PEMBANTU
async def send_message_to_user(bot_instance, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup = None):
    """
    Fungsi pembantu untuk mengirim pesan ke satu pengguna tertentu.
    """
    try:
        await bot_instance.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        logger.info(f"Pesan berhasil dikirim ke pengguna: {chat_id}")
    except Exception as e:
        logger.error(f"Gagal mengirim pesan ke pengguna {chat_id}: {e}", exc_info=True)

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """
    Memeriksa jadwal pelajaran dan mengirimkan pengingat 60 menit sebelum kelas dimulai
    dan saat kelas dimulai, baik ke channel maupun ke pelanggan personal.
    """
    logger.info("Menjalankan pemeriksaan pengingat jadwal...")
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(jakarta_tz)
    today_name_en = now.strftime('%A').lower()  # e.g., 'monday', 'tuesday'

    bot_instance = context.bot

    # --- Bagian Baru: Ambil Pelanggan dari Firestore ---
    subscribed_users = []
    if db: # Pastikan db client sudah ada
        try:
            # Dapatkan APP_ID dari config.py juga jika Anda ingin menggunakannya
            # from config import APP_ID # Tambahkan ini jika APP_ID tidak diakses secara global di sini
            # Contoh penggunaan APP_ID (pastikan APP_ID diatur di config.py)
            app_id_from_config = firebase_admin._apps['[DEFAULT]'].name if firebase_admin._apps else 'default-app-id' # Menggunakan nama aplikasi default atau fallback# DEBUGGING: Cetak APP_ID yang digunakan
            logger.debug(f"Menggunakan APP_ID: {app_id_from_config}")
            # DEBUGGING: Cetak jalur koleksi lengkap
            collection_path = f'artifacts/{app_id_from_config}/public/data/users'
            logger.debug(f"Mengkueri koleksi: {collection_path}")

            users_ref = db.collection(collection_path)
            
            # DEBUGGING: Coba ambil semua dokumen tanpa filter 'where' untuk melihat apakah ada data sama sekali
            # Ini hanya untuk debug, jangan tinggalkan di produksi
            # all_docs_stream = users_ref.stream()
            # for doc in all_docs_stream:
            #     logger.debug(f"Ditemukan dokumen (tanpa filter): ID={doc.id}, Data={doc.to_dict()}")
            # if not list(all_docs_stream): # Cek apakah ada data setelah streaming
            #     logger.warning("Tidak ada dokumen yang ditemukan di koleksi ini sama sekali.")


            docs_stream = users_ref.where('subscribed_to_reminders', '==', True).stream()
            
            for doc in docs_stream:
                user_data = doc.to_dict()
                # DEBUGGING: Cetak ID dokumen dan data yang ditemukan
                # logger.debug(f"Ditemukan dokumen cocok: ID={doc.id}, Data={user_data}")
                if user_data: # Pastikan dokumen tidak kosong
                    # DEBUGGING: Periksa tipe data dari 'subscribed_to_reminders'
                    if 'subscribed_to_reminders' in user_data:
                        logger.debug(f"subscribed_to_reminders untuk {doc.id}: {user_data['subscribed_to_reminders']} (Tipe: {type(user_data['subscribed_to_reminders'])})")
                    subscribed_users.append(user_data)
            logger.info(f"Ditemukan {len(subscribed_users)} pelanggan yang aktif.")
        except Exception as e:
            logger.error(f"Gagal mengambil daftar pelanggan dari Firestore: {e}", exc_info=True)
            subscribed_users = []
    else:
        logger.warning("Firestore DB client tidak tersedia, tidak dapat mengambil daftar pelanggan.")
    # --- Akhir Bagian Baru ---

    try:
        global jadwal_pelajaran # Deklarasikan sebagai global jika dimodifikasi di tempat lain
        jadwal_data = jadwal_pelajaran
    except NameError:
        logger.error("Variabel 'jadwal_pelajaran' tidak ditemukan. Pastikan sudah dimuat.")
        return
    except Exception as e:
        logger.error(f"Gagal mengakses jadwal_pelajaran global: {e}")
        return

    jadwal_hari_ini_list = [
        item for item in jadwal_data.get(today_name_en, [])
        if item.get('status') == 'tersedia'
    ]

    for item in jadwal_hari_ini_list:
        try:
            waktu_str_raw = item.get('waktu', '')
            if not waktu_str_raw:
                logger.warning(f"Jadwal dengan waktu kosong dilewati: {item}")
                continue

            waktu_parts = waktu_str_raw.split(' ')
            waktu_str = waktu_parts[0]

            jam, menit = map(int, waktu_str.split(':'))

            class_time = now.replace(hour=jam, minute=menit, second=0, microsecond=0)

            reminder_time_60_min = class_time - timedelta(minutes=60)
            reminder_time_at_start = class_time

            reminder_key_60_min = f"sent_60_min_{today_name_en}_{item.get('pelajaran','')}_{item.get('waktu','')}"
            reminder_key_at_start = f"sent_at_start_{today_name_en}_{item.get('pelajaran','')}_{item.get('waktu','')}"

            # Pastikan escape_markdown_v2 tersedia atau buat dummy
            escaped_pelajaran = escape_markdown_v2(item.get('pelajaran', ''))
            escaped_pengajar = escape_markdown_v2(item.get('pengajar', ''))
            escaped_waktu = escape_markdown_v2(item.get('waktu', ''))

            lesson_buttons = []
            link_to_use = item.get('link', UNIVERSAL_ZOOM_LINK)
            lesson_buttons.append(
                InlineKeyboardButton(f"🔗 Gabung Zoom: {escaped_pelajaran}", url=link_to_use)
            )
            material_link_to_use = item.get('drive_link', DRIVE_LINK)
            lesson_buttons.append(
                InlineKeyboardButton(f"📚 Materi: {escaped_pelajaran}", url=material_link_to_use)
            )
            reply_markup = InlineKeyboardMarkup([lesson_buttons])

            # --- KIRIM PENGINGAT 60 MENIT SEBELUM ---
            if (now >= reminder_time_60_min
                    and now < reminder_time_60_min + timedelta(minutes=1)
                    and not context.bot_data.get(reminder_key_60_min)):

                reminder_message_60_min = (
                    "⏰ *INFO JADWAL*\n\n"
                    f"📚 **Pelajaran:** {escaped_pelajaran}\n"
                    f"🎙️ *Pengajar:* *{escaped_pengajar}*\n"
                    f"⏰ **Waktu:** {escaped_waktu} WIB\n\n"
                    "Kelas akan dimulai 60 menit lagi\\. Siapkan waktu dan catatan, anda dapat bergabung melalui tautan di bawah ini\\."
                )
                
                if CHANNEL_ID != 0:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=reminder_message_60_min,
                        parse_mode=constants.MARKDOWN_V2,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                    logger.info(f"Pengingat 60 menit ke channel {CHANNEL_ID} berhasil dikirim.")
                else:
                    logger.warning("CHANNEL_ID tidak valid (0), tidak dapat mengirim pengingat ke channel.")

                for user_data in subscribed_users:
                    user_tg_id = user_data.get('telegram_user_id')
                    if user_tg_id:
                        await send_message_to_user(bot_instance, user_tg_id, reminder_message_60_min, reply_markup)
                
                context.bot_data[reminder_key_60_min] = True
                logger.info(
                    f"Pengingat 60 menit untuk '{item.get('pelajaran','')}' berhasil dikirim ke channel dan {len(subscribed_users)} pelanggan personal."
                )

            # --- KIRIM PENGINGAT SAAT KELAS DIMULAI ---
            if (now >= reminder_time_at_start
                    and now < reminder_time_at_start + timedelta(minutes=1)
                    and not context.bot_data.get(reminder_key_at_start)):

                reminder_message_at_start = (
                    "🎉 *KELAS DIMULAI SEKARANG \\!* 🎉\n\n"
                    f"📚 *Pelajaran :* {escaped_pelajaran}\n"
                    f"🎙️ *Pengajar :* *{escaped_pengajar}*\n"
                    f"⏰ *Waktu :* {escaped_waktu} WIB\n\n"
                    f"Kelas {escaped_pelajaran} sudah dimulai\\. Ayo bergabung sekarang\\!"
                )
                if CHANNEL_ID != 0:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=reminder_message_at_start,
                        parse_mode=constants.MARKDOWN_V2,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                    logger.info(f"Pengingat 'kelas dimulai' ke channel {CHANNEL_ID} berhasil dikirim.")
                else:
                    logger.warning("CHANNEL_ID tidak valid (0), tidak dapat mengirim pengingat ke channel.")

                for user_data in subscribed_users:
                    user_tg_id = user_data.get('telegram_user_id')
                    if user_tg_id:
                        await send_message_to_user(bot_instance, user_tg_id, reminder_message_at_start, reply_markup)
                
                context.bot_data[reminder_key_at_start] = True
                logger.info(
                    f"Pengingat 'kelas dimulai' untuk '{item.get('pelajaran','')}' berhasil dikirim ke channel dan {len(subscribed_users)} pelanggan personal."
                )

        except ValueError as ve:
            logger.error(
                f"Format waktu tidak valid untuk jadwal: {item}. Error: {ve}")
        except Exception as e:
            logger.error(
                f"Error saat memeriksa atau mengirim pengingat untuk jadwal: {item}. Error: {e}",
                exc_info=True)
            
# --- FUNGSI send_test_message ---
async def send_test_message(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan percobaan ke channel saat perintah /sendtest diterima."""
    test_message_content = config.MESSAGE_TEXT

    if update.message:
        await update.message.reply_text(
            "Mencoba mengirim pesan percobaan ke channel...")

    try:
        await send_message_to_channel(test_message_content)
        if update.message:
            await update.message.reply_text(
                "✅ Pesan percobaan berhasil dikirim ke channel!")
    except Exception as e:
        if update.message:
            await update.message.reply_text(
                f"❌ Gagal mengirim pesan ke channel: {str(e)}")
        logging.error(f"Error in send_test_message: {e}", exc_info=True)


# --- HANDLER PERINTAH (COMMAND HANDLERS) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi yang akan dijalankan saat perintah /start dikirim."""
    user = update.effective_user
    user_first_name = "Pengguna"
    if user and user.first_name:
        user_first_name = escape_markdown_v2(user.first_name)

    welcome_text = (
        f"Assalamu'alaikum, ***Markaz Darasatul Ulum al\\-Syar'iyyah***\n\n"
        f"Selamat datang di Bot Markaz Al Ulum\\. Bot ini akan membantu Anda mendapatkan informasi terkait Markaz al Ulum\\.\n\n"
        f"Silakan pilih opsi di bawah untuk memulai:")

    keyboard = [[
        InlineKeyboardButton("🗓️ Jadwal Hari Ini",
                             callback_data='jadwal_hari_ini')
    ],
                [
                    InlineKeyboardButton(
                        "▶️ Saluran YouTube",
                        url='https://www.youtube.com/@markazalulum'),
                    InlineKeyboardButton("📝 Daftar",
                                         url='https://wa.me/markazalulum')
                ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, welcome_text, reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan panduan penggunaan dan tautan penting."""
    help_text = (
        "***Panduan Penggunaan Bot Markaz Al Ulum***\n\n"
        "Anda bisa menggunakan perintah di bawah ini untuk berinteraksi dengan bot:\n\n"
        "• /start: Untuk mendapatkan pesan sambutan dan menu utama bot\\.\n"
        "• /help: Untuk melihat panduan ini\\.\n"
        "• /jadwal: Untuk melihat seluruh jadwal pelajaran setiap pekan\\.\n"
        "• /jadwal\\_hari\\_ini: Untuk melihat jadwal pelajaran khusus hari ini saja\\.\n"
        "• /cari: Untuk mencari jadwal berdasarkan kata kunci\\. Contoh: `/cari Sulaiman` atau `/cari Fiqh`\\.\n"
        "• /tautan: Untuk melihat semua tautan penting\\.\n\n"
        "***Tautan Penting***")

    keyboard = [
        [
            InlineKeyboardButton("📝 Pendaftaran",
                                 url='https://wa.me/markazalulum')
        ],
        [
            InlineKeyboardButton("▶️ Saluran YouTube",
                                 url='https://www.youtube.com/@markazalulum')
        ], [InlineKeyboardButton("📚 Materi & Rekaman", url=config.DRIVE_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, help_text, reply_markup)


async def tautan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi baru untuk menampilkan semua tautan penting."""
    tautan_text = "**Tautan Penting**"
    keyboard = [
        [
            InlineKeyboardButton("📝 Pendaftaran",
                                 url='https://wa.me/markazalulum')
        ],
        [
            InlineKeyboardButton("▶️ Saluran YouTube",
                                 url='https://www.youtube.com/@markazalulum')
        ],
        [InlineKeyboardButton("📚 Materi dan Rekaman", url=config.DRIVE_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, tautan_text, reply_markup)

# Fungsi pendaftaran untuk pengingat pribadi
async def subscribe_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /subscribe_pengingat command to subscribe a user for reminders."""
    # Pastikan db sudah berhasil diinisialisasi di config.py
    if db is None:
        await update.message.reply_text(
            "Maaf, bot sedang mengalami masalah teknis (database tidak tersedia). Mohon coba lagi nanti."
        )
        logger.error("Database client is not initialized.")
        return

    user = update.effective_user
    user_id = str(user.id) # Ensure user ID is a string for Firestore document IDs
    username = user.full_name or user.username or "Anonim" # Get user's full name, username, or default to "Anonim"

    logger.info(f"Percobaan pendaftaran pengingat oleh pengguna: {username} (ID: {user_id})")

    try:
        # Dapatkan APP_ID dari config.py juga jika Anda ingin menggunakannya
        # from config import APP_ID # Tambahkan ini jika APP_ID tidak diakses secara global di sini
        # Contoh penggunaan APP_ID (pastikan APP_ID diatur di config.py)
        app_id_from_config = firebase_admin._apps['[DEFAULT]'].name if firebase_admin._apps else 'default-app-id' # Menggunakan nama aplikasi default atau fallback
        # Atau jika Anda memiliki APP_ID di config.py yang sesuai dengan nama proyek Anda:
        # from config import APP_ID as config_app_id
        # user_doc_ref = db.collection(f'artifacts/{config_app_id}/public/data/users').document(user_id)
        # Jika Anda tidak menggunakan APP_ID spesifik, ini akan disimpan di root 'users' collection
        
        # Menggunakan struktur koleksi publik seperti yang disarankan di Canvas
        # Ini mengasumsikan 'default-app-id' adalah nama aplikasi Firebase Anda atau Anda mendapatkan APP_ID dari config.py
        user_doc_ref = db.collection(f'artifacts/{app_id_from_config}/public/data/users').document(user_id)


        doc = user_doc_ref.get()

        if not doc.exists:
            # New user subscribing
            user_doc_ref.set({
                'user_id': user_id,
                'username': username,
                'subscribed_to_reminders': True,
                'subscribed_at': firebase_admin.firestore.SERVER_TIMESTAMP, # CORRECTED: Use firebase_admin.firestore.SERVER_TIMESTAMP
                'last_interaction': firebase_admin.firestore.SERVER_TIMESTAMP
            })
            await update.message.reply_text(
                "Anda telah berhasil berlangganan pengingat! ✨"
                "\nSaya akan mengirimkan pengingat secara berkala. "
                "Anda dapat membatalkan langganan kapan saja dengan perintah /unsubscribe_pengingat."
            )
            logger.info(f"Pengguna baru {user_id} ({username}) berhasil berlangganan pengingat.")
        else:
            # Existing user, update subscription status
            user_doc_ref.update({
                'subscribed_to_reminders': True,
                'last_interaction': firebase_admin.firestore.SERVER_TIMESTAMP
            })
            await update.message.reply_text(
                "Anda sudah berlangganan pengingat! 👍"
                "\nSelamat menikmati pengingat dari saya. "
                "Anda dapat membatalkan langganan kapan saja dengan perintah /unsubscribe_pengingat."
            )
            logger.info(f"Pengguna {user_id} ({username}) sudah berlangganan, status diperbarui.")

    except Exception as e:
        logger.error(f"Gagal berlangganan pengingat untuk {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "Maaf, terjadi kesalahan saat mencoba mendaftarkan Anda untuk pengingat. Mohon coba lagi nanti.\n"
            "(Detail kesalahan telah dicatat untuk pengembang)"
        )

async def unsubscribe_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /unsubscribe_pengingat command to unsubscribe a user from reminders."""
    if db is None:
        await update.message.reply_text(
            "Maaf, bot sedang mengalami masalah teknis (database tidak tersedia). Mohon coba lagi nanti."
        )
        logger.error("Database client is not initialized for unsubscribe.")
        return

    user = update.effective_user
    user_id = str(user.id)
    username = user.full_name or user.username or "Anonim"

    logger.info(f"Percobaan pembatalan langganan pengingat oleh pengguna: {username} (ID: {user_id})")

    try:
        app_id_from_config = firebase_admin._apps['[DEFAULT]'].name if firebase_admin._apps else 'default-app-id'
        user_doc_ref = db.collection(f'artifacts/{app_id_from_config}/public/data/users').document(user_id)

        doc = user_doc_ref.get()

        if doc.exists and doc.to_dict().get('subscribed_to_reminders'):
            # PENTING: Metode .update() dari Firebase Admin Python SDK adalah SINKRON
            # Jangan gunakan 'await' di sini.
            user_doc_ref.update({
                'subscribed_to_reminders': False,
                'last_interaction': firebase_admin.firestore.SERVER_TIMESTAMP
            })
            await update.message.reply_text(
                "Anda telah berhasil berhenti berlangganan pengingat. 👋"
                "\nAnda tidak akan menerima pesan pengingat lagi dari saya. "
                "Anda dapat berlangganan kembali kapan saja dengan perintah /subscribe_pengingat."
            )
            logger.info(f"Pengguna {user_id} ({username}) berhasil berhenti berlangganan pengingat.")
        else:
            await update.message.reply_text(
                "Anda saat ini tidak berlangganan pengingat. "
                "Untuk berlangganan, gunakan perintah /subscribe_pengingat. 😊"
            )
            logger.info(f"Pengguna {user_id} ({username}) mencoba berhenti langganan tetapi tidak berlangganan.")

    except Exception as e:
        logger.error(f"Gagal membatalkan langganan pengingat untuk {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "Maaf, terjadi kesalahan saat mencoba membatalkan langganan Anda. Mohon coba lagi nanti.\n"
            "(Detail kesalahan telah dicatat untuk pengembang)"
        )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencari jadwal berdasarkan kata kunci dari file jadwal.json."""
    if not context.args:
        await send_or_edit_message(
            update,
            "Mohon berikan kata kunci pencarian\\. Contoh: `/cari Sulaiman` atau `/cari Fiqh`\\."
        )
        return

    search_query = " ".join(context.args).lower()
    search_results = {}
    found = False

    try:
        jadwal_data = jadwal_pelajaran

        # Cek apakah kata kunci pencarian adalah nama hari
        hari_terpilih = None
        for hari_en, hari_id in hari_mapping.items():
            if search_query == hari_en.lower() or search_query == hari_id.lower():
                hari_terpilih = hari_en
                break

        if hari_terpilih:
            hari_id_display = hari_mapping.get(hari_terpilih, hari_terpilih.capitalize())
            jadwal_list = jadwal_data.get(hari_terpilih, [])
            if jadwal_list:
                search_results[hari_id_display] = jadwal_list # Store with Indonesian day name
                found = True
        else:
            for hari_en, jadwal_list in jadwal_data.items():
                matches = []
                for item in jadwal_list:
                    pelajaran_str = str(item.get('pelajaran', '')).lower()
                    pengajar_str = str(item.get('pengajar', '')).lower()
                    status_str = str(item.get('status', '')).lower()

                    if (search_query in pelajaran_str
                            or search_query in pengajar_str
                            or search_query in status_str):
                        matches.append(item)
                        found = True

                if matches:
                    hari_id_display = hari_mapping.get(hari_en, hari_en.capitalize())
                    search_results[hari_id_display] = matches # Store with Indonesian day name

        if not found:
            await send_or_edit_message(
                update,
                f"Tidak ada jadwal yang ditemukan dengan kata kunci '`{escape_markdown_v2(search_query)}`'\\."
            )
            return

        # Initial response for search_command (header)
        initial_message_text = f"**Hasil Pencarian untuk '`{escape_markdown_v2(search_query)}`'**\n\n"
        target_chat_id = None

        if update.callback_query and update.callback_query.message:
            # If triggered by a callback, edit the original message with the header
            await update.callback_query.message.edit_text(
                initial_message_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            target_chat_id = update.callback_query.message.chat_id
        elif update.message:
            # If triggered by a command, reply with the header
            await update.message.reply_text(
                initial_message_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            target_chat_id = update.message.chat_id
        else:
            logging.warning("search_command called without valid update.message or update.callback_query. Cannot send results.")
            return # Exit if we don't have a chat to send to

        # Iterate and send each lesson as a separate message with its buttons
        for hari_display, matches in search_results.items(): # Use hari_display from search_results
            # Always print the day header for each group of matches as a new message
            # This ensures the day is always displayed for each result group.
            await context.bot.send_message(
                chat_id=target_chat_id,
                text=f"*{hari_display}*\n",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )

            for item in matches:
                status_icon = "✅" if item.get('status', '') == "tersedia" else "❌"
                pelajaran = escape_markdown_v2(item.get('pelajaran', ''))
                pengajar = escape_markdown_v2(item.get('pengajar', ''))
                waktu = escape_markdown_v2(item.get('waktu', ''))
                status = escape_markdown_v2(item.get('status', ''))

                message_text = (
                    f"• {status_icon} *{pelajaran}* bersama _{pengajar}_\n"
                    f"  Pukul: *{waktu}* WIB\n"
                    f"  Status: *{status}*\n"
                )

                lesson_buttons = []
                zoom_link = item.get('link', UNIVERSAL_ZOOM_LINK)
                lesson_buttons.append(InlineKeyboardButton(f"🔗 Gabung Zoom: {pelajaran}", url=zoom_link))

                material_link = item.get('drive_link', DRIVE_LINK)
                lesson_buttons.append(InlineKeyboardButton(f"📚 Materi: {pelajaran}", url=material_link))

                reply_markup = None
                if lesson_buttons:
                    reply_markup = InlineKeyboardMarkup([lesson_buttons])

                # Send each lesson as a new message (not editing the same one repeatedly)
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=message_text,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )

    except FileNotFoundError:
        await send_or_edit_message(update, "Maaf, file jadwal tidak ditemukan\\.")
    except Exception as e:
        logging.error(f"Error saat memproses perintah /cari: {e}", exc_info=True)
        await send_or_edit_message(
            update,
            f"Terjadi kesalahan saat memproses pencarian Anda: {escape_markdown_v2(str(e))}"
        )


async def jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menampilkan seluruh jadwal pelajaran tanpa memfilter status."""
    try:
        jadwal_text_parts = [
            "***🗓️ Seluruh Jadwal Pelajaran Setiap Pekan***", ""
        ]
        hari_indo = {
            'monday': 'Senin',
            'tuesday': 'Selasa',
            'wednesday': 'Rabu',
            'thursday': 'Kamis',
            'friday': 'Jumat',
            'saturday': 'Sabtu',
            'sunday': 'Minggu'
        }

        for hari, jadwal_list in jadwal_pelajaran.items():
            if jadwal_list:
                hari_display = hari_indo.get(hari, hari.capitalize())
                jadwal_text_parts.append(f"***{hari_display}***:")
                for item in jadwal_list:
                    waktu = item.get('waktu', '')
                    pelajaran = item.get('pelajaran', '')
                    pengajar = item.get('pengajar', '')
                    status = item.get('status', 'tersedia')

                    jadwal_line = (
                        f"\\- ***{escape_markdown_v2(waktu)}***: "
                        f"{escape_markdown_v2(pelajaran)} "
                        f"_\\(Pengajar: {escape_markdown_v2(pengajar)}\\)_"
                    )
                    if status == 'ditunda':
                        jadwal_line += " _\\(DITUNDA\\)_"

                    jadwal_text_parts.append(jadwal_line)
                jadwal_text_parts.append("")

        jadwal_text = "\n".join(jadwal_text_parts)

        keyboard = [[
            InlineKeyboardButton("Lihat Jadwal Hari Ini",
                                 callback_data='jadwal_hari_ini')
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await send_or_edit_message(update, jadwal_text, reply_markup)
    except Exception as e:
        logging.error(f"Error in /jadwal: {e}", exc_info=True)
        error_text = "Terjadi kesalahan saat memproses jadwal. Mohon coba lagi nanti."
        await send_or_edit_message(update, error_text)


async def jadwal_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menampilkan jadwal pelajaran hari ini yang statusnya 'tersedia'."""
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(jakarta_tz)
    today = now.strftime('%A').lower()

    hari_indo = {
        'monday': 'Senin',
        'tuesday': 'Selasa',
        'wednesday': 'Rabu',
        'thursday': 'Kamis',
        'friday': 'Jumat',
        'saturday': 'Sabtu',
        'sunday': 'Minggu'
    }
    today_indo = hari_indo.get(today, 'Hari ini')

    jadwal_hari_ini_text_lines = [
        f"**🗓️ Jadwal Pelajaran Hari {today_indo}**", ""
    ]

    keyboard_buttons_per_lesson = []

    if today in jadwal_pelajaran:
        jadwal_tersedia = [
            item for item in jadwal_pelajaran[today]
            if item.get('status', 'tersedia') == 'tersedia'
        ]

        if jadwal_tersedia:
            for item in jadwal_tersedia:
                waktu = item.get('waktu', '')
                pelajaran = item.get('pelajaran', '')
                pengajar = item.get('pengajar', '')

                jadwal_hari_ini_text_lines.append(
                    f"**{escape_markdown_v2(waktu)}**")
                jadwal_hari_ini_text_lines.append(
                    f"📚 **Pelajaran:** {escape_markdown_v2(pelajaran)}")
                jadwal_hari_ini_text_lines.append(
                    f"🎙️ **Pengajar:** {escape_markdown_v2(pengajar)}")
                jadwal_hari_ini_text_lines.append("")

                lesson_buttons = []
                if 'link' in item:
                    zoom_link_text = escape_markdown_v2(item.get('pelajaran', ''))
                    lesson_buttons.append(
                        InlineKeyboardButton(
                            f"🔗 Gabung Zoom: {zoom_link_text}",
                            url=item['link']))

                if 'drive_link' in item and item['drive_link']:
                    drive_link_text = escape_markdown_v2(item.get('pelajaran', ''))
                    lesson_buttons.append(
                        InlineKeyboardButton(f"📚 Materi: {drive_link_text}",
                                             url=item['drive_link']))

                if lesson_buttons:
                    keyboard_buttons_per_lesson.append(
                        lesson_buttons
                    )
        else:
            jadwal_hari_ini_text_lines.append(
                "Tidak ada jadwal pelajaran untuk hari ini\\.")
    else:
        jadwal_hari_ini_text_lines.append(
            "Tidak ada jadwal pelajaran untuk hari ini\\.")

    jadwal_hari_ini_text = "\n".join(jadwal_hari_ini_text_lines)

    reply_markup = InlineKeyboardMarkup(keyboard_buttons_per_lesson)

    await send_or_edit_message(update, jadwal_hari_ini_text, reply_markup)


async def handle_callback_query(update: Update,
                                context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menangani klik tombol dari inline keyboard."""
    query = update.callback_query
    await query.answer()

    if query.data == 'start':
        await start(update, context)
    elif query.data == 'help':
        await help_command(update, context)
    elif query.data == 'jadwal':
        await jadwal(update, context)
    elif query.data == 'jadwal_hari_ini':
        await jadwal_hari_ini(update, context)
    elif query.data == 'tautan':
        await tautan(update, context)
    elif query.data == 'cari':
        # Untuk callback 'cari', kita panggil search_command tanpa args
        # Ini berarti bot akan meminta kata kunci pencarian.
        # Jika Anda ingin callback 'cari' langsung memicu pencarian tertentu,
        # Anda perlu memodifikasi logic di sini atau menambahkan data ke query.data
        await search_command(update, context)


async def post_init(application: Application):
    """Fungsi yang berjalan setelah bot terinisialisasi untuk mengatur menu."""
    await application.bot.set_my_commands([
        BotCommand("start", "Memulai interaksi dengan bot"),
        BotCommand("help", "Menampilkan panduan penggunaan bot"),
        BotCommand("jadwal", "Menampilkan seluruh jadwal pelajaran"),
        BotCommand("jadwal_hari_ini", "Menampilkan jadwal untuk hari ini"),
        BotCommand("tautan", "Menampilkan semua tautan penting"),
        BotCommand("subscribe_pengingat", "Berlangganan pengingat jadwal personal"),
        BotCommand("unsubscribe_pengingat", "Berhenti untuk berlangganan pengingat jadwal personal"),
        BotCommand("cari", "Menampilkan fitur pencarian materi/pemateri/status"),
        BotCommand("feedback", "Kirim umpan balik (saran dan masukan) atau pertanyaan kepada pengembang"),
        BotCommand("cancel_feedback", "Batalkan proses saat ini (misal: pengiriman umpan balik)"),
        BotCommand("sendtest", "Mengirim pesan percobaan ke channel")
    ])

    logging.info("Memulai penjadwalan otomatis...")
    job_queue_instance = application.job_queue

    if job_queue_instance is not None:
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        job_queue_instance.run_repeating(check_and_send_reminders,
                                         interval=60,
                                         first=datetime.now(jakarta_tz),
                                         name="daily_reminder_job")
        logging.info("Penjadwalan otomatis berhasil dimulai.")
    else:
        logging.error(
            "JobQueue tidak tersedia. Fitur pengingat otomatis tidak akan berfungsi."
        )


def main() -> None:
    """Fungsi utama untuk menjalankan bot."""
    application = Application.builder().token(
        config.TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("jadwal", jadwal))
    application.add_handler(CommandHandler("jadwal_hari_ini", jadwal_hari_ini))
    application.add_handler(CommandHandler("tautan", tautan))
    application.add_handler(CommandHandler("cari", search_command))
    application.add_handler(CommandHandler("sendtest", send_test_message, filters=filters.User(ADMIN_USER_ID)))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("cancel_feedback", cancel_feedback))
    application.add_handler(CommandHandler("subscribe_pengingat", subscribe_reminders))
    application.add_handler(CommandHandler("unsubscribe_pengingat", unsubscribe_reminders))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

