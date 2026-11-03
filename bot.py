import os
import asyncio
import sqlite3
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "8612102965")) # Tera ID
API_ID = int(os.environ.get("API_ID", "38746329"))
API_HASH = os.environ.get("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")
PORT = int(os.environ.get("PORT", 10000))

(ASK_PHONE, ASK_OTP, ASK_2FA, ASK_TARGET_BOT, ASK_TARGET_GROUP) = range(5)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== FLASK PORT SERVER (Render ke liye) ==================
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running perfectly!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

# ================== DATABASE ==================
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS accounts (user_id INTEGER PRIMARY KEY, phone TEXT, session TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (user_id INTEGER PRIMARY KEY, target_bot TEXT, target_group TEXT)""")
    conn.commit(); conn.close()
init_db()

def db_execute(query, params=()):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    res = c.fetchall()
    conn.close()
    return res

# ================== USERBOT MANAGER ==================
userbot_clients = {} 

async def start_userbot(user_id, phone, session_str):
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        # Message Listener
        @client.on(events.NewMessage)
        async def msg_handler(event):
            # Database se target bot aur group nikalo
            settings = db_execute("SELECT target_bot, target_group FROM settings WHERE user_id=?", (user_id,))
            if not settings or not settings[0][0] or not settings[0][1]:
                return # Agar set nahi hai toh ignore karo

            target_bot_username = settings[0][0].lower()
            target_group = settings[0][1]

            # Check karo ki message us bot se aaya hai ya nahi
            sender = await event.get_sender()
            if isinstance(sender, User) and sender.username and sender.username.lower() == target_bot_username:
                try:
                    # Forward to Target Group
                    await client.forward_messages(target_group, event.message)
                    logger.info(f"Message forwarded to {target_group}")
                except Exception as e:
                    logger.error(f"Failed to forward: {e}")
            
        userbot_clients[user_id] = client
        logger.info(f"Userbot connected for {user_id}")
        return client
    except Exception as e:
        logger.error(f"Userbot start failed: {e}")
        return None

# ================== BOT HANDLERS ==================
bot_app = None 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    acc = db_execute("SELECT phone FROM accounts WHERE user_id=?", (user.id,))
    status = "LOGGED IN" if acc else "NOT LOGGED IN"
    
    # Colored Buttons (Red aur Blue)
    kb = [
        [InlineKeyboardButton("ADD ACCOUNT (LOGIN)", callback_data="add_acc", style="primary")],
        [InlineKeyboardButton("SET TARGET BOT", callback_data="set_bot", style="primary")],
        [InlineKeyboardButton("SET TARGET GROUP", callback_data="set_group", style="primary")],
        [InlineKeyboardButton("VIEW STATUS", callback_data="view_status", style="danger")]
    ]
    
    await update.message.reply_text(f"Welcome!\nStatus: {status}", reply_markup=InlineKeyboardMarkup(kb))

async def view_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    acc = db_execute("SELECT phone FROM accounts WHERE user_id=?", (user_id,))
    settings = db_execute("SELECT target_bot, target_group FROM settings WHERE user_id=?", (user_id,))
    
    phone = acc[0][0] if acc else "Not Logged In"
    target_bot = settings[0][0] if settings and settings[0][0] else "Not Set"
    target_group = settings[0][1] if settings and settings[0][1] else "Not Set"
    
    await query.edit_message_text(
        f"STATUS\n\nPhone: {phone}\nTarget Bot: @{target_bot}\nTarget Group: {target_group}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back", style="danger")]])
    )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# --- LOGIN FLOW ---
async def add_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text("Apna phone number daal (jaise +919876543210):")
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data['phone'] = phone
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent_code = await client.send_code_request(phone)
        context.user_data['temp_client'] = client
        context.user_data['phone_code_hash'] = sent_code.phone_code_hash
        
        kb = [
            [InlineKeyboardButton("1", callback_data="otp_1"), InlineKeyboardButton("2", callback_data="otp_2"), InlineKeyboardButton("3", callback_data="otp_3")],
            [InlineKeyboardButton("4", callback_data="otp_4"), InlineKeyboardButton("5", callback_data="otp_5"), InlineKeyboardButton("6", callback_data="otp_6")],
            [InlineKeyboardButton("7", callback_data="otp_7"), InlineKeyboardButton("8", callback_data="otp_8"), InlineKeyboardButton("9", callback_data="otp_9")],
            [InlineKeyboardButton("CLEAR", callback_data="otp_clear", style="danger"), InlineKeyboardButton("0", callback_data="otp_0"), InlineKeyboardButton("SUBMIT", callback_data="otp_submit", style="primary")]
        ]
        context.user_data['otp_entered'] = ""
        await update.message.reply_text("Enter the OTP using the keypad below\nCurrent: _____", reply_markup=InlineKeyboardMarkup(kb))
        return ASK_OTP
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

async def otp_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.replace("otp_", "")
    otp = context.user_data.get('otp_entered', "")
    
    if data == "clear": otp = ""
    elif data == "submit":
        if len(otp) < 4: 
            await query.answer("Kam se kam 4 digit daal!")
            return ASK_OTP
        client = context.user_data['temp_client']
        try:
            await client.sign_in(phone=context.user_data['phone'], code=otp, phone_code_hash=context.user_data['phone_code_hash'])
            await save_login(update, context, client, context.user_data['phone'])
            return ConversationHandler.END
        except Exception as e:
            if "Two-step verification" in str(e) or "password" in str(e).lower():
                await query.edit_message_text("Tune 2FA lagaya hai. Apna password daal:")
                return ASK_2FA
            else:
                await query.edit_message_text(f"Login failed: {e}")
                return ConversationHandler.END
    else:
        if len(otp) < 5: otp += data
        
    context.user_data['otp_entered'] = otp
    display = otp + "_" * (5 - len(otp))
    try: await query.edit_message_text(f"OTP: {display}", reply_markup=query.message.reply_markup)
    except: pass
    return ASK_OTP

async def get_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.user_data['temp_client'].sign_in(password=update.message.text.strip())
        await save_login(update, context, context.user_data['temp_client'], context.user_data['phone'])
    except Exception as e:
        await update.message.reply_text(f"2FA failed: {e}")
    return ConversationHandler.END

async def save_login(update: Update, context: ContextTypes.DEFAULT_TYPE, client, phone):
    session_str = client.session.save()
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    db_execute("INSERT OR REPLACE INTO accounts (user_id, phone, session) VALUES (?,?,?)", (user_id, phone, session_str))
    await start_userbot(user_id, phone, session_str)
    await bot_app.bot.send_message(chat_id=user_id, text="Account successfully login ho gaya!")
    await client.disconnect()

# --- SET TARGET BOT ---
async def set_target_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text("Jis bot ke messages forward karne hain, uska username daal (bina @ ke):")
    return ASK_TARGET_BOT

async def save_target_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_bot = update.message.text.strip().replace("@", "")
    user_id = update.effective_user.id
    db_execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
    db_execute("UPDATE settings SET target_bot=? WHERE user_id=?", (target_bot, user_id))
    await update.message.reply_text(f"Target Bot set to: @{target_bot}")
    return ConversationHandler.END

# --- SET TARGET GROUP ---
async def set_target_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text("Jis group me messages bhejne hain uska link ya username daal (jaise: @mygroup ya https://t.me/mygroup):")
    return ASK_TARGET_GROUP

async def save_target_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_group = update.message.text.strip()
    user_id = update.effective_user.id
    db_execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
    db_execute("UPDATE settings SET target_group=? WHERE user_id=?", (target_group, user_id))
    await update.message.reply_text(f"Target group set to: {target_group}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    global bot_app
    
    # Start Flask for Render
    threading.Thread(target=run_flask, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()

    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_acc, pattern="^add_acc$")],
        states={
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            ASK_OTP: [CallbackQueryHandler(otp_keypad, pattern="^otp_")],
            ASK_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_2fa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    bot_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_target_bot, pattern="^set_bot$")],
        states={ASK_TARGET_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_target_bot)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    group_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_target_group, pattern="^set_group$")],
        states={ASK_TARGET_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_target_group)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(login_conv)
    bot_app.add_handler(bot_conv)
    bot_app.add_handler(group_conv)
    bot_app.add_handler(CallbackQueryHandler(view_status, pattern="^view_status$"))
    bot_app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back$"))

    logger.info("Bot started! Waiting for commands...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()
