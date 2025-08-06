import logging
from datetime import datetime, timedelta
import pytz
import re
import json
import config
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, constants, BotCommand, Bot 
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
# Mengimpor escape_markdown untuk memperbaiki error parsing
from telegram.helpers import escape_markdown

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

# Teks pesan yang akan dikirim bot
MESSAGE_TEXT = "Assalamu'alaikum warrahmatullahi wabarakatuh, Ini adalah pesan percobaan yang dikirim bot menggunakan file konfigurasi. Kredensial berhasil diimpor!"

# Setup logging untuk melihat setiap aksi bot
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# Jadwal pelajaran untuk setiap hari.
try:
    with open('jadwal.json', 'r') as f:
        jadwal_pelajaran = json.load(f)
except FileNotFoundError:
    logging.error("File 'jadwal.json' tidak ditemukan. Pastikan file tersebut ada di direktori yang sama.")
    jadwal_pelajaran = {}
except json.JSONDecodeError:
    logging.error("Terjadi kesalahan saat membaca file 'jadwal.json'. Pastikan formatnya benar.")
    jadwal_pelajaran = {}

def escape_markdown_v2(text: str) -> str:
    """Fungsi untuk meng-escape semua karakter khusus MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', text)

# --- FUNGSI PEMBANTU BARU (Refactoring) ---
async def send_or_edit_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None):
    """
    Fungsi pembantu untuk mengirim pesan baru atau mengedit pesan yang sudah ada
    berdasarkan jenis pembaruan (pesan teks atau klik tombol).
    """
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )

async def send_message_to_channel(message_text: str, reply_markup: InlineKeyboardMarkup = None):
    """
    Fungsi ini menginisialisasi bot dan mengirimkan pesan ke channel.
    """
    try:
        # Buat instance bot menggunakan token dari config.py
        bot = Bot(token=config.TOKEN)
        
        # Kirim pesan ke channel
        await bot.send_message(chat_id=config.CHANNEL_ID, text=message_text, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=reply_markup, disable_web_page_preview=True)
        logging.info("Pesan berhasil dikirim ke channel.")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan ke channel: {e}", exc_info=True)

# --- FUNGSI SCHEDULER BARU ---
# --- FUNGSI SCHEDULER BARU ---
async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """
    Memeriksa jadwal pelajaran dan mengirimkan pengingat 60 menit sebelum kelas dimulai
    dan saat kelas dimulai.
    """
    logging.info("Menjalankan pemeriksaan pengingat jadwal...")
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(jakarta_tz)
    today_name_en = now.strftime('%A').lower() # e.g., 'monday', 'tuesday'

    jadwal_hari_ini_list = [item for item in jadwal_pelajaran.get(today_name_en, []) if item.get('status') == 'tersedia']

    for item in jadwal_hari_ini_list:
            try:
                waktu_str = item['waktu'].split(' ')[0] # Ambil hanya HH:MM jika ada " WIB"
                jam, menit = map(int, waktu_str.split(':'))

                # Buat objek datetime untuk waktu pelajaran hari ini
                class_time = now.replace(hour=jam, minute=menit, second=0, microsecond=0)

                # Hitung waktu pengingat (60 menit sebelum)
                reminder_time_60_min = class_time - timedelta(minutes=60)
                
                # Hitung waktu pengingat (saat kelas dimulai)
                reminder_time_at_start = class_time

                # Gunakan context.bot_data untuk melacak pengingat yang sudah dikirim
                # Ini akan reset setiap kali bot di-restart
                reminder_key_60_min = f"sent_60_min_{today_name_en}_{item['pelajaran']}_{item['waktu']}"
                reminder_key_at_start = f"sent_at_start_{today_name_en}_{item['pelajaran']}_{item['waktu']}"

                # >>>>>> PERUBAHAN DIMULAI DI SINI <<<<<<
                # Escape dynamic content once at the beginning of the loop,
                # so it's available for both 60-min and at-start reminders.
                escaped_pelajaran = escape_markdown_v2(item['pelajaran'])
                escaped_pengajar = escape_markdown_v2(item['pengajar'])
                escaped_waktu = escape_markdown_v2(item['waktu']) 
                # >>>>>> PERUBAHAN BERAKHIR DI SINI <<<<<<

                # Cek apakah pengingat 60 menit sebelum sudah waktunya
                # dan berada dalam jendela 1 menit dari waktu pengingat, dan belum dikirim
                if (now >= reminder_time_60_min and now < reminder_time_60_min + timedelta(minutes=1) and
                    not context.bot_data.get(reminder_key_60_min)):
                    
                    reminder_message = (
                        f"📣 *INFO JADWAL*\n\n"
                        f"📚 **Pelajaran:** {escaped_pelajaran}\n" # Menggunakan variabel yang sudah di-escape
                        f"👨‍🏫 *Pengajar:* *{escaped_pengajar}*\n"   # Menggunakan variabel yang sudah di-escape
                        f"⏰ **Waktu:** {escaped_waktu} WIB\n\n"    # Menggunakan variabel yang sudah di-escape
                        f"Kelas akan dimulai 60 menit lagi\\. Siapkan waktu dan catatan, anda dapat bergabung melalui tautan di bawah ini\\."
                    )
                    
                    # Menggunakan link dari jadwal.json atau UNIVERSAL_ZOOM_LINK
                    link_to_use = item.get('link', config.UNIVERSAL_ZOOM_LINK)
                    keyboard = [[InlineKeyboardButton(f"🔗 Gabung Zoom: {escape_markdown_v2(item['pelajaran'])}", url=link_to_use)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await send_message_to_channel(reminder_message, reply_markup)
                    context.bot_data[reminder_key_60_min] = True # Set flag
                    logging.info(f"Pengingat 60 menit untuk '{item['pelajaran']}' berhasil dikirim.")
                
                # Cek apakah pengingat saat kelas dimulai sudah waktunya
                # Kita bisa menambahkan sedikit toleransi waktu agar tidak terlewat, dan belum dikirim
                if (now >= reminder_time_at_start and now < reminder_time_at_start + timedelta(minutes=1) and
                    not context.bot_data.get(reminder_key_at_start)):

                    reminder_message = (
                        f"🎉 *KELAS DIMULAI SEKARANG \\!* 🎉\n\n" # Manually escape * and !
                        f"📚 *Pelajaran :* {escaped_pelajaran}\n"
                        f"👨‍🏫 *Pengajar :* *{escaped_pengajar}*\n"
                        f"⏰ *Waktu :* {escaped_waktu} WIB\n\n"
                        f"Kelas {escaped_pelajaran} sudah dimulai\\. Ayo bergabung sekarang\\!" # Manually escape . and !
                    )
                    
                    # Menggunakan link dari jadwal.json atau UNIVERSAL_ZOOM_LINK
                    link_to_use = item.get('link', config.UNIVERSAL_ZOOM_LINK)
                    keyboard = [[InlineKeyboardButton(f"🔗 Gabung Zoom: {escape_markdown_v2(item['pelajaran'])}", url=link_to_use)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await send_message_to_channel(reminder_message, reply_markup)
                    context.bot_data[reminder_key_at_start] = True # Set flag
                    logging.info(f"Pengingat 'kelas dimulai' untuk '{item['pelajaran']}' berhasil dikirim.")

            except ValueError as ve:
                logging.error(f"Format waktu tidak valid untuk jadwal: {item}. Error: {ve}")
            except Exception as e:
                logging.error(f"Error saat memeriksa atau mengirim pengingat untuk jadwal: {item}. Error: {e}", exc_info=True)

# --- FUNGSI BARU: send_test_message ---
async def send_test_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan percobaan ke channel saat perintah /sendtest diterima."""
    await update.message.reply_text("Mencoba mengirim pesan percobaan ke channel...")
    await send_message_to_channel()
    await update.message.reply_text("Perintah pengiriman pesan percobaan telah dieksekusi. Cek konsol atau channel Anda.")

# --- HANDLER PERINTAH (COMMAND HANDLERS) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi yang akan dijalankan saat perintah /start dikirim."""
    welcome_text = (
        "Assalamu'alaikum, ***Markaz Darasatul Ulum al\\-Syar'iyyah***\n\n"
        "Selamat datang di Bot Markaz Al Ulum\\. Bot ini akan membantu Anda mendapatkan informasi terkait Markaz al Ulum\\.\n\n"
        "Silakan pilih opsi di bawah untuk memulai:"
    )

    keyboard = [
        [
            InlineKeyboardButton("🗓️ Jadwal Hari Ini", callback_data='jadwal_hari_ini')
        ],
        [
            InlineKeyboardButton("▶️ Saluran YouTube", url='https://www.youtube.com/@markazalulum'),
            InlineKeyboardButton("📝 Daftar", url='https://wa.me/markazalulum')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_or_edit_message(update, welcome_text, reply_markup)

# --- Fungsi help_command yang Diperbarui ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan panduan penggunaan dan tautan penting."""
    help_text = (
        "***Panduan Penggunaan Bot Markaz Al Ulum***\n\n"
        "Anda bisa menggunakan perintah di bawah ini untuk berinteraksi dengan bot:\n\n"
        "• /start: Untuk mendapatkan pesan sambutan dan menu utama bot\\.\n"
        "• /help: Untuk melihat panduan ini\\.\n"
        "• /jadwal: Untuk melihat seluruh jadwal pelajaran setiap pekan\\.\n"
        "• /jadwal\_hari\_ini: Untuk melihat jadwal pelajaran khusus hari ini saja\\.\n"
        "• /cari: Untuk mencari jadwal berdasarkan kata kunci\\. Contoh: `/cari Sulaiman` atau `/cari Fiqh`\\.\n"
        "• /tautan: Untuk melihat semua tautan penting\\.\n\n"
        "***Tautan Penting***"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Pendaftaran", url='https://wa.me/markazalulum')
        ],
        [
            InlineKeyboardButton("▶️ Saluran YouTube", url='https://www.youtube.com/@markazalulum')
        ],
        [
            InlineKeyboardButton("📚 Materi & Rekaman", url=config.DRIVE_LINK)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_or_edit_message(update, help_text, reply_markup)

async def tautan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi baru untuk menampilkan semua tautan penting."""
    tautan_text = "**Tautan Penting**"
    keyboard = [
        [
            InlineKeyboardButton("📝 Pendaftaran", url='https://wa.me/markazalulum')
        ],
        [
            InlineKeyboardButton("▶️ Saluran YouTube", url='https://www.youtube.com/@markazalulum')
        ],
        [
            InlineKeyboardButton("📚 Materi dan Rekaman", url=config.DRIVE_LINK)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_or_edit_message(update, tautan_text, reply_markup)

# --- FUNGSI BARU: search_command ---
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencari jadwal berdasarkan kata kunci dari file jadwal.json."""
    if not context.args:
        await send_or_edit_message(update, "Mohon berikan kata kunci pencarian\\. Contoh: `/cari Sulaiman` atau `/cari Fiqh`\\.")
        return

    search_query = " ".join(context.args).lower()
    search_results = {}
    found = False

    try:
        with open('jadwal.json', 'r') as f:
            jadwal_data = json.load(f)

        # Cek apakah kata kunci pencarian adalah nama hari
        hari_terpilih = None
        for hari_en, hari_id in hari_mapping.items():
            if search_query == hari_en.lower() or search_query == hari_id.lower():
                hari_terpilih = hari_en
                break
        
        # Jika kata kunci adalah hari, tampilkan jadwal hari itu saja
        if hari_terpilih:
            hari_id = hari_mapping.get(hari_terpilih, hari_terpilih.capitalize())
            jadwal_list = jadwal_data.get(hari_terpilih, [])
            if jadwal_list:
                search_results[hari_id] = jadwal_list
                found = True

        # Jika bukan hari, lakukan pencarian biasa
        else:            
            for hari_en, jadwal_list in jadwal_data.items():
                matches = []
                for jadwal in jadwal_list:
                    if (search_query in jadwal['pelajaran'].lower() or
                        search_query in jadwal['pengajar'].lower() or
                        search_query in jadwal['status'].lower()):
                    
                        matches.append(jadwal)
                        found = True
            
                if matches:
                    hari_id = hari_mapping.get(hari_en, hari_en.capitalize())
                    search_results[hari_id] = matches

        if not found:
            await send_or_edit_message(update, f"Tidak ada jadwal yang ditemukan dengan kata kunci '`{search_query}`'\\.")
            return

        result_text = f"**Hasil Pencarian untuk '`{search_query}`'**\n\n"
        for hari_id, matches in search_results.items():
            result_text += f"*{hari_id}*\n"
            for jadwal in matches:
                status_icon = "✅" if jadwal['status'] == "tersedia" else "❌"
                jadwal_line = (
                    f"• {status_icon} {jadwal['pelajaran']} bersama {jadwal['pengajar']} "
                    f"pukul {jadwal['waktu']}"
                )
                result_text += escape_markdown(jadwal_line, version=2) + "\n"
            result_text += "\n"

        await send_or_edit_message(update, result_text)

    except FileNotFoundError:
        await send_or_edit_message(update, "Maaf, file jadwal tidak ditemukan\\.")
    except Exception as e:
        await send_or_edit_message(update, f"Terjadi kesalahan saat memuat jadwal: {escape_markdown(str(e), version=2)}")

async def jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menampilkan seluruh jadwal pelajaran tanpa memfilter status."""
    try:
        jadwal_text_parts = ["***🗓️ Seluruh Jadwal Pelajaran Setiap Pekan***", ""]
        hari_indo = {
            'monday': 'Senin', 'tuesday': 'Selasa', 'wednesday': 'Rabu',
            'thursday': 'Kamis', 'friday': 'Jumat', 'saturday': 'Sabtu',
            'sunday': 'Minggu'
        }

        for hari, jadwal_list in jadwal_pelajaran.items():
            if jadwal_list:
                hari_display = hari_indo.get(hari, hari.capitalize())
                jadwal_text_parts.append(f"***{hari_display}***:")
                for item in jadwal_list:
                    waktu = item['waktu']
                    pelajaran = item['pelajaran']
                    pengajar = item['pengajar']
                    status = item.get('status', 'tersedia')
                    
                    jadwal_line = f"\\- ***{escape_markdown_v2(waktu)}***: {escape_markdown_v2(pelajaran)} _\\(Pengajar: {escape_markdown_v2(pengajar)}\\)_"
                    if status == 'ditunda':
                        jadwal_line += " _\\(DITUNDA\\)_"
                    
                    jadwal_text_parts.append(jadwal_line)
                jadwal_text_parts.append("")
        
        jadwal_text = "\n".join(jadwal_text_parts)
        
        keyboard = [[InlineKeyboardButton("Lihat Jadwal Hari Ini", callback_data='jadwal_hari_ini')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_or_edit_message(update, jadwal_text, reply_markup)
    except Exception as e:
        logging.error(f"Error in /jadwal: {e}", exc_info=True)
        error_text = "Terjadi kesalahan saat memproses jadwal. Mohon coba lagi nanti."
        await send_or_edit_message(update, error_text)

async def jadwal_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menampilkan jadwal pelajaran hari ini yang statusnya 'tersedia'."""
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    today = datetime.now(jakarta_tz).strftime('%A').lower()

    hari_indo = {
        'monday': 'Senin', 'tuesday': 'Selasa', 'wednesday': 'Rabu',
        'thursday': 'Kamis', 'friday': 'Jumat', 'saturday': 'Sabtu',
        'sunday': 'Minggu'
    }
    today_indo = hari_indo.get(today, 'Hari ini')
    
    jadwal_hari_ini_text_lines = [f"**🗓️ Jadwal Pelajaran Hari {today_indo}**", ""]
    
    keyboard = []
    
    if today in jadwal_pelajaran:
        jadwal_tersedia = [item for item in jadwal_pelajaran[today] if item.get('status', 'tersedia') == 'tersedia']

        if jadwal_tersedia:
            for item in jadwal_tersedia:
                waktu = item['waktu']
                pelajaran = item['pelajaran']
                pengajar = item['pengajar']

                jadwal_hari_ini_text_lines.append(f"**{escape_markdown_v2(waktu)}**")
                jadwal_hari_ini_text_lines.append(f"📚 **Pelajaran:** {escape_markdown_v2(pelajaran)}")
                jadwal_hari_ini_text_lines.append(f"👨‍🏫 **Pengajar:** {escape_markdown_v2(pengajar)}")
                jadwal_hari_ini_text_lines.append("")
                
                if 'link' in item:
                    link_text = escape_markdown_v2(item['pelajaran'])
                    keyboard.append([InlineKeyboardButton(f"🔗 Gabung Zoom: {link_text}", url=item['link'])])
        else:
            jadwal_hari_ini_text_lines.append("Tidak ada jadwal pelajaran untuk hari ini\\.")
    else:
        jadwal_hari_ini_text_lines.append("Tidak ada jadwal pelajaran untuk hari ini\\.")

    jadwal_hari_ini_text = "\n".join(jadwal_hari_ini_text_lines)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_or_edit_message(update, jadwal_hari_ini_text, reply_markup)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fungsi untuk menangani klik tombol dari inline keyboard."""
    query = update.callback_query
    await query.answer()

    # Perhatikan, kita sekarang memanggil fungsi command handler secara langsung.
    # Ini akan menggunakan logika `send_or_edit_message` di dalamnya.
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
        await search_command(update, context)

async def post_init(application: Application):
    """Fungsi yang berjalan setelah bot terinisialisasi untuk mengatur menu."""
    await application.bot.set_my_commands([
        BotCommand("start", "Memulai interaksi dengan bot"),
        BotCommand("help", "Menampilkan panduan penggunaan bot"),
        BotCommand("jadwal", "Menampilkan seluruh jadwal pelajaran"),
        BotCommand("jadwal_hari_ini", "Menampilkan jadwal untuk hari ini"),
        BotCommand("tautan", "Menampilkan semua tautan penting"),
        BotCommand("cari", "Menampilkan fitur pencarian materi/pemateri/status"),
        BotCommand("sendtest", "Mengirim pesan percobaan ke channel")
    ])

    # Menjadwalkan pemeriksaan jadwal setiap menit
    # Ini akan dijalankan di latar belakang secara terus menerus
    logging.info("Memulai penjadwalan otomatis...")
    job_queue_instance = application.job_queue # Dapatkan instance JobQueue yang benar
    jakarta_tz = pytz.timezone('Asia/Jakarta') # Pastikan zona waktu didefinisikan
        
    # Jalankan setiap 60 detik (1 menit), mulai segera (first=datetime.now(jakarta_tz))
    job_queue_instance.run_repeating(check_and_send_reminders, interval=60, first=datetime.now(jakarta_tz), name="daily_reminder_job")

def main() -> None:
    """Fungsi utama untuk menjalankan bot."""
    application = Application.builder().token(config.TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("jadwal", jadwal))
    application.add_handler(CommandHandler("jadwal_hari_ini", jadwal_hari_ini))
    application.add_handler(CommandHandler("tautan", tautan))
    application.add_handler(CommandHandler("cari", search_command))
    # Perintah /sendtest hanya bisa digunakan oleh ADMIN_USER_ID
    application.add_handler(CommandHandler("sendtest", send_test_message, filters=filters.User(config.ADMIN_USER_ID)))

    application.add_handler(CallbackQueryHandler(handle_callback_query))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
