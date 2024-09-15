import sqlite3
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging
from datetime import datetime

DATABASE = 'kino_bot.db'
ADMIN_IDS = [7099759329]  # Admin Telegram ID'lari

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kinolar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                file_id TEXT,
                title TEXT,
                release_year TEXT,
                language TEXT,
                view_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                active_date TEXT
            )
        ''')

def update_db_schema():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        schema_updates = [
            "ALTER TABLE kinolar ADD COLUMN title TEXT",
            "ALTER TABLE kinolar ADD COLUMN release_year TEXT",
            "ALTER TABLE kinolar ADD COLUMN language TEXT",
            "ALTER TABLE kinolar ADD COLUMN view_count INTEGER DEFAULT 0"
        ]
        for update in schema_updates:
            try:
                cursor.execute(update)
            except sqlite3.OperationalError:
                pass

async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Kanalga obuna bo'lish", url="https://t.me/uztarjimakino_no1")],
        [InlineKeyboardButton("Tasdiqlash", callback_data='verify')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Iltimos, kanalga obuna bo\'ling va "Tasdiqlash" tugmasini bosing.', reply_markup=reply_markup)

async def verify_subscription(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    chat_member = await context.bot.get_chat_member(chat_id="@uztarjimakino_no1", user_id=user_id)

    if chat_member.status in ['member', 'administrator', 'creator']:
        try:
            await query.message.delete()
        except Exception as e:
            logging.error(f"Xato: {e}")

        await query.message.reply_text("Ajoyib! Endi siz botdan to'liq foydalanishingiz mumkin. Kino kodini yuboring.")
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (user_id, active_date) VALUES (?, ?)",
                           (user_id, datetime.now().strftime('%Y-%m-%d')))
    else:
        await query.message.reply_text("Iltimos, avval kanalga obuna bo'ling!")

    await query.answer()

async def handle_kino_code(update: Update, context):
    kino_code = update.message.text
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, title, release_year, language, view_count FROM kinolar WHERE code=?", (kino_code,))
        result = cursor.fetchone()

    if result:
        file_id, title, release_year, language, view_count = result
        view_count += 1

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE kinolar SET view_count = ? WHERE code = ?", (view_count, kino_code))

        await update.message.reply_video(file_id, caption=f"Yuklashlar soni: {view_count}")
    else:
        await update.message.reply_text("Kechirasiz, bunday kino topilmadi. Iltimos, to'g'ri kodni yuboring!")

async def admin_panel(update: Update, context):
    if update.message.from_user.id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("Kino Qo'shish", callback_data='add_movie')],
            [InlineKeyboardButton("Eng Oxirgi Kino O'chirish", callback_data='delete_last_movie')],
            [InlineKeyboardButton("Foydalanuvchilar Sonini Ko'rish", callback_data='view_users')],
            [InlineKeyboardButton("Kunning Statistikasi", callback_data='daily_stats')],
            [InlineKeyboardButton("Kino Sonini Ko'rish", callback_data='count_movies')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Admin Panel:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Sizda bu buyruqni bajarish huquqi yo'q.")

async def admin_callback(update: Update, context):
    query = update.callback_query
    action = query.data

    if update.callback_query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("Sizda bu buyruqni bajarish huquqi yo'q.")
        return

    if action == 'add_movie':
        await query.message.reply_text("Kino qo'shish uchun video yuboring.")
        context.user_data['admin_action'] = 'add_movie'
    elif action == 'delete_last_movie':
        # Eng oxirgi kino o'chirilishini amalga oshirish
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code FROM kinolar ORDER BY id DESC LIMIT 1")
            result = cursor.fetchone()

        if result:
            kino_code = result[0]
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM kinolar WHERE code=?", (kino_code,))
                conn.commit()
            await query.message.reply_text(f"Eng oxirgi kino o'chirildi: {kino_code}")
        else:
            await query.message.reply_text("O'chiradigan kino topilmadi!")
    elif action == 'view_users':
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            result = cursor.fetchone()[0]
        await query.message.reply_text(f"Jami foydalanuvchilar soni: {result}")
    elif action == 'daily_stats':
        today = datetime.now().strftime('%Y-%m-%d')
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE active_date=?", (today,))
            result = cursor.fetchone()[0]
        await query.message.reply_text(f"Bugun botga kirgan foydalanuvchilar soni: {result}")
    elif action == 'count_movies':
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM kinolar")
            result = cursor.fetchone()[0]
        await query.message.reply_text(f"Jami kino soni: {result}")

    try:
        await query.answer()
    except Exception as e:
        logging.error(f"Callback query xatosi: {e}")

async def receive_kino(update: Update, context):
    if 'admin_action' in context.user_data:
        action = context.user_data['admin_action']
        if action == 'add_movie':
            video = update.message.video

            if video:
                code = generate_unique_code()
                with sqlite3.connect(DATABASE) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO kinolar (code, file_id) VALUES (?, ?)",
                                   (code, video.file_id))

                await update.message.reply_text(f"Kino muvaffaqiyatli qo'shildi. Unikal kod: {code}")
                context.user_data['admin_action'] = None
            else:
                await update.message.reply_text("Iltimos, faqat video fayllarni yuboring!")
        elif action == 'delete_last_movie':
            # Bu yerda kino o'chirish kodi amalga oshiriladi
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT code FROM kinolar ORDER BY id DESC LIMIT 1")
                result = cursor.fetchone()

            if result:
                kino_code = result[0]
                with sqlite3.connect(DATABASE) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM kinolar WHERE code=?", (kino_code,))
                    conn.commit()
                await update.message.reply_text(f"Eng oxirgi kino o'chirildi: {kino_code}")
            else:
                await update.message.reply_text("O'chiradigan kino topilmadi!")
            context.user_data['admin_action'] = None

def generate_unique_code():
    return str(random.randint(1000, 9999))

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    application = Application.builder().token("7249927470:AAEAkLItCrzI7dWsTpsmrz4-EhVuqn7MlXM").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern='verify'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_kino_code))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.VIDEO, receive_kino))

    init_db()
    update_db_schema()

    application.run_polling()

if __name__ == '__main__':
    main()


