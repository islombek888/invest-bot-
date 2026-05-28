import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from src.config import config
from src.database import db_service

if not config.BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set in .env file!")
    exit(1)

from telebot import apihelper
apihelper.ENABLE_MIDDLEWARE = True

bot = telebot.TeleBot(config.BOT_TOKEN)

# Format currency
def format_money(val: float) -> str:
    return f"{int(val):,}".replace(",", " ") + " so'm"

# Format date
def format_date(date_str: str) -> str:
    try:
        clean_date_str = date_str.replace('Z', '')
        if '.' in clean_date_str:
            d = datetime.strptime(clean_date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
        else:
            d = datetime.fromisoformat(clean_date_str)
        return d.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return date_str

# User states
class UserState:
    def __init__(self):
        self.state = 'NONE'
        self.deposit_amount = None
        self.withdraw_card = None
        self.invest_amount = None
        self.lookup_user_id = None
        self.lookup_user_action = None

user_states = {}  # user_id -> UserState

def get_user_state(user_id: int) -> UserState:
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]

def set_user_state(user_id: int, **kwargs):
    state = get_user_state(user_id)
    for k, v in kwargs.items():
        setattr(state, k, v)

def reset_user_state(user_id: int):
    user_states[user_id] = UserState()

# Keyboards
def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('💳 Depozit'), KeyboardButton('💸 Pul Yechish'))
    markup.add(KeyboardButton('📈 Investitsiya'), KeyboardButton('👥 Referal Tizimi'))
    markup.add(KeyboardButton('👤 Kabinet'))
    return markup

def get_cancel_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(KeyboardButton('❌ Bekor qilish'))
    return markup

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('📊 Statistika'), KeyboardButton("💳 Karta o'zgartirish"))
    markup.add(KeyboardButton('⚙️ Sozlamalar'), KeyboardButton('📢 Xabar yuborish'))
    markup.add(KeyboardButton('🔍 Foydalanuvchi qidirish'))
    markup.add(KeyboardButton('🔙 Foydalanuvchi menyusi'))
    return markup

def get_settings_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton('💳 Min. Depozit', callback_data='admin_conf_min_dep'),
        InlineKeyboardButton('💸 Min. Yechish', callback_data='admin_conf_min_with')
    )
    markup.row(
        InlineKeyboardButton('👥 Referal Bonus', callback_data='admin_conf_ref_bonus'),
        InlineKeyboardButton('🏠 Admin Panel', callback_data='admin_panel_back')
    )
    return markup

# Middleware to reset user state on commands/menu clicks
@bot.middleware_handler(update_types=['message'])
def state_reset_middleware(bot_instance, message):
    user_id = message.from_user.id
    text = message.text
    if text:
        menu_buttons = [
            '💳 Depozit', '💸 Pul Yechish', '📈 Investitsiya', '👥 Referal Tizimi', '👤 Kabinet',
            '❌ Bekor qilish', '📊 Statistika', '💳 Karta o\'zgartirish', '⚙️ Sozlamalar',
            '📢 Xabar yuborish', '🔍 Foydalanuvchi qidirish', '🔙 Foydalanuvchi menyusi'
        ]
        if text in menu_buttons or text.startswith('/'):
            reset_user_state(user_id)

# Start Command
@bot.message_handler(commands=['start'])
def start_command_handler(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or 'Foydalanuvchi'
    
    # Parse payload if present (for referrals: /start ref_123456)
    start_payload = ""
    parts = message.text.split()
    if len(parts) > 1:
        start_payload = parts[1]
        
    referrer_id = None
    if start_payload and start_payload.startswith('ref_'):
        ref_str = start_payload.replace('ref_', '')
        try:
            parsed_ref = int(ref_str)
            if parsed_ref != user_id:
                referrer_id = parsed_ref
        except ValueError:
            pass

    existing_user = db_service.get_user(user_id)
    
    # Create or update user
    db_service.create_user(
        id=user_id,
        username=username,
        first_name=first_name,
        referred_by=existing_user['referred_by'] if existing_user else referrer_id
    )
    
    # Reward referrer if new user
    if not existing_user and referrer_id:
        referrer = db_service.get_user(referrer_id)
        if referrer:
            ref_bonus = float(db_service.get_setting('referral_bonus', str(config.REFERRAL_BONUS)))
            db_service.update_balance(referrer_id, ref_bonus)
            
            # Notify referrer
            try:
                bot.send_message(
                    referrer_id,
                    f"👥 **Yangi hamkor!**\n\nSizning taklif havolangiz orqali yangi do'stingiz botga qo'shildi. "
                    f"Balansingizga **+{format_money(ref_bonus)}** qo'shildi!",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print('Failed to notify referrer:', e)

    reset_user_state(user_id)
    
    bot.send_message(
        user_id,
        f"👋 **Assalomu alaykum, {first_name}!**\n\n"
        f"🤖 Professional investitsiya va hamkorlik botimizga xush kelibsiz.\n\n"
        f"Bu yerda siz pulingizni investitsiya qilib, kunlik **25%** daromad olishingiz va "
        f"do'stlaringizni taklif qilib pul ishlashingiz mumkin.",
        reply_markup=get_user_keyboard()
    )
    
    if user_id == config.ADMIN_ID:
        bot.send_message(user_id, "👨‍💻 Siz adminsiz. Admin panelga o'tish uchun /admin buyrug'ini yozing.")

# Admin commands
@bot.message_handler(commands=['admin'])
def admin_command_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        bot.send_message(user_id, "❌ Kechirasiz, siz admin emassiz.")
        return
        
    reset_user_state(user_id)
    bot.send_message(
        user_id,
        "👨‍💻 **Admin paneliga xush kelibsiz!**\n\nKerakli bo'limni tanlang:",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(commands=['give'])
def give_command_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        bot.send_message(user_id, "❌ Kechirasiz, siz admin emassiz.")
        return
        
    args = message.text.split()
    if len(args) < 3:
        bot.send_message(
            user_id,
            "⚠️ To'g'ri foydalanish: `/give <Telegram_ID> <miqdor>`\nMasalan: `/give 123456789 50000`",
            parse_mode='Markdown'
        )
        return
        
    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    if amount <= 0:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    target_user = db_service.get_user(target_id)
    if not target_user:
        bot.send_message(user_id, f"❌ Foydalanuvchi topilmadi (ID: {target_id}).")
        return
        
    db_service.update_balance(target_id, amount)
    bot.send_message(
        user_id,
        f"✅ Foydalanuvchi {target_user['first_name']} (ID: {target_id}) balansiga **+{format_money(amount)}** qo'shildi.",
        reply_markup=get_admin_keyboard()
    )
    
    try:
        bot.send_message(
            target_id,
            f"💰 Balansingiz admin tomonidan **+{format_money(amount)}** ga ko'paytirildi!\n"
            f"Joriy balans: **{format_money(target_user['balance'] + amount)}**",
            parse_mode='Markdown'
        )
    except Exception:
        pass

@bot.message_handler(commands=['take'])
def take_command_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        bot.send_message(user_id, "❌ Kechirasiz, siz admin emassiz.")
        return
        
    args = message.text.split()
    if len(args) < 3:
        bot.send_message(
            user_id,
            "⚠️ To'g'ri foydalanish: `/take <Telegram_ID> <miqdor>`\nMasalan: `/take 123456789 50000`",
            parse_mode='Markdown'
        )
        return
        
    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    if amount <= 0:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    target_user = db_service.get_user(target_id)
    if not target_user:
        bot.send_message(user_id, f"❌ Foydalanuvchi topilmadi (ID: {target_id}).")
        return
        
    db_service.update_balance(target_id, -amount)
    bot.send_message(
        user_id,
        f"✅ Foydalanuvchi {target_user['first_name']} (ID: {target_id}) balansidan **-{format_money(amount)}** ayirildi.",
        reply_markup=get_admin_keyboard()
    )
    
    new_bal = max(0.0, target_user['balance'] - amount)
    try:
        bot.send_message(
            target_id,
            f"💰 Balansingizdan admin tomonidan **-{format_money(amount)}** ayirildi.\n"
            f"Joriy balans: **{format_money(new_bal)}**",
            parse_mode='Markdown'
        )
    except Exception:
        pass

@bot.message_handler(commands=['setbal'])
def setbal_command_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        bot.send_message(user_id, "❌ Kechirasiz, siz admin emassiz.")
        return
        
    args = message.text.split()
    if len(args) < 3:
        bot.send_message(
            user_id,
            "⚠️ To'g'ri foydalanish: `/setbal <Telegram_ID> <miqdor>`\nMasalan: `/setbal 123456789 100000`",
            parse_mode='Markdown'
        )
        return
        
    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    if amount < 0:
        bot.send_message(user_id, "❌ Xato: Iltimos to'g'ri ID va musbat miqdor yozing.")
        return
        
    target_user = db_service.get_user(target_id)
    if not target_user:
        bot.send_message(user_id, f"❌ Foydalanuvchi topilmadi (ID: {target_id}).")
        return
        
    db_service.set_balance(target_id, amount)
    bot.send_message(
        user_id,
        f"✅ Foydalanuvchi {target_user['first_name']} (ID: {target_id}) balansi **{format_money(amount)}** qilib o'rnatildi.",
        reply_markup=get_admin_keyboard()
    )
    
    try:
        bot.send_message(
            target_id,
            f"💰 Balansingiz admin tomonidan **{format_money(amount)}** qilib o'rnatildi!",
            parse_mode='Markdown'
        )
    except Exception:
        pass

# Cancel button handler
@bot.message_handler(func=lambda message: message.text == '❌ Bekor qilish')
def cancel_handler(message):
    user_id = message.from_user.id
    reset_user_state(user_id)
    markup = get_admin_keyboard() if user_id == config.ADMIN_ID else get_user_keyboard()
    bot.send_message(user_id, '❌ Amaliyot bekor qilindi.', reply_markup=markup)

# Admin keyboard handlers
@bot.message_handler(func=lambda message: message.text == '🔙 Foydalanuvchi menyusi')
def back_to_user_menu(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    reset_user_state(user_id)
    bot.send_message(user_id, '🔙 Foydalanuvchi menyusiga qaytildi.', reply_markup=get_user_keyboard())

@bot.message_handler(func=lambda message: message.text == '📊 Statistika')
def statistics_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    stats = db_service.get_stats()
    msg = (
        f"📊 **Bot Statistikasi:**\n\n"
        f"👥 **Jami foydalanuvchilar:** {stats['totalUsers']} ta\n"
        f"💰 **Jami tasdiqlangan depozitlar:** {format_money(stats['totalDeposits'])}\n"
        f"💸 **Jami tasdiqlangan to'lovlar (yechish):** {format_money(stats['totalWithdrawals'])}\n\n"
        f"📈 **Faol investitsiyalar soni:** {stats['activeInvestmentsCount']} ta\n"
        f"💰 **Faol investitsiyalar hajmi:** {format_money(stats['activeInvestmentsSum'])}"
    )
    bot.send_message(user_id, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "💳 Karta o'zgartirish")
def card_change_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    current_card = db_service.get_setting('card_details', config.CARD_DETAILS)
    set_user_state(user_id, state='ADMIN_CARD_CHANGE')
    msg = (
        f"💳 **Karta raqamini o'zgartirish:**\n\n"
        f"Joriy karta ma'lumotlari:\n"
        f"`{current_card}`\n\n"
        f"Yangi karta ma'lumotlarini kiriting (karta raqami va egasining ismi):"
    )
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=get_cancel_keyboard())

@bot.message_handler(func=lambda message: message.text == '⚙️ Sozlamalar')
def settings_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    min_dep = float(db_service.get_setting('min_deposit', str(config.MIN_DEPOSIT)))
    min_with = float(db_service.get_setting('min_withdrawal', str(config.MIN_WITHDRAWAL)))
    ref_bonus = float(db_service.get_setting('referral_bonus', str(config.REFERRAL_BONUS)))
    msg = (
        f"⚙️ **Tizim Sozlamalari:**\n\n"
        f"💳 **Minimal depozit:** {format_money(min_dep)}\n"
        f"💸 **Minimal yechish:** {format_money(min_with)}\n"
        f"👥 **Referal bonus:** {format_money(ref_bonus)}\n\n"
        f"O'zgartirmoqchi bo'lgan sozlamani tanlang:"
    )
    bot.send_message(user_id, msg, reply_markup=get_settings_keyboard(), parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '📢 Xabar yuborish')
def broadcast_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    set_user_state(user_id, state='ADMIN_BROADCAST')
    msg = (
        f"📢 **Foydalanuvchilarga xabar yuborish:**\n\n"
        f"Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (rasm, matn, havola hammasi bo'lishi mumkin):"
    )
    bot.send_message(user_id, msg, reply_markup=get_cancel_keyboard(), parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🔍 Foydalanuvchi qidirish')
def user_lookup_handler(message):
    user_id = message.from_user.id
    if user_id != config.ADMIN_ID:
        return
    set_user_state(user_id, state='ADMIN_USER_LOOKUP')
    msg = (
        f"🔍 **Foydalanuvchini qidirish:**\n\n"
        f"Foydalanuvchining Telegram ID yoki username (boshida @ belgisiz) kiriting:"
    )
    bot.send_message(user_id, msg, reply_markup=get_cancel_keyboard(), parse_mode='Markdown')

# User keyboard handlers
@bot.message_handler(func=lambda message: message.text == '👤 Kabinet')
def cabinet_handler(message):
    user_id = message.from_user.id
    user = db_service.get_user(user_id)
    if not user:
        username = message.from_user.username
        first_name = message.from_user.first_name or 'Foydalanuvchi'
        user = db_service.create_user(user_id, username, first_name)
        
    ref_count = db_service.get_referral_count(user_id)
    all_invs = db_service.get_user_investments(user_id)
    active_invs = [i for i in all_invs if i['status'] == 'active']
    
    msg = (
        f"👤 **Sizning Kabinetingiz:**\n\n"
        f"🆔 **ID:** `{user['id']}`\n"
        f"👤 **Ism:** {user['first_name']}\n"
        f"💰 **Balans:** **{format_money(user['balance'])}**\n\n"
        f"👥 **Siz taklif qilgan hamkorlar:** **{ref_count} ta**\n"
        f"📈 **Faol investitsiyalaringiz:** **{len(active_invs)} ta**"
    )
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=get_user_keyboard())

@bot.message_handler(func=lambda message: message.text == '👥 Referal Tizimi')
def referral_handler(message):
    user_id = message.from_user.id
    ref_count = db_service.get_referral_count(user_id)
    ref_bonus = float(db_service.get_setting('referral_bonus', str(config.REFERRAL_BONUS)))
    
    bot_info = bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    msg = (
        f"👥 **Hamkorlik (Referal) Dasturi:**\n\n"
        f"Do'stlaringizni botga taklif qiling va har bir muvaffaqiyatli ro'yxatdan o'tgan do'stingiz uchun **{format_money(ref_bonus)}** bonus oling!\n\n"
        f"🔗 **Sizning taklif havolangiz:**\n`{ref_link}`\n\n"
        f"📊 **Statistika:**\n"
        f"Taklif qilingan do'stlar: **{ref_count} ta**\n"
        f"Ishlab topilgan jami mukofot: **{format_money(ref_count * ref_bonus)}**"
    )
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=get_user_keyboard())

@bot.message_handler(func=lambda message: message.text == '💳 Depozit')
def deposit_init_handler(message):
    user_id = message.from_user.id
    current_card = db_service.get_setting('card_details', config.CARD_DETAILS)
    min_dep = float(db_service.get_setting('min_deposit', str(config.MIN_DEPOSIT)))
    
    set_user_state(user_id, state='DEPOSIT_AMOUNT')
    msg = (
        f"💳 **Balansni to'ldirish (Depozit):**\n\n"
        f"Siz bizning rasmiy kartamizga pul o'tkazishingiz kerak:\n"
        f"➡️ Karta: `{current_card}`\n\n"
        f"⚠️ Minimal depozit miqdori: **{format_money(min_dep)}**\n\n"
        f"O'tkazma tugagach, to'lovni tasdiqlash uchun botga yuborishingiz kerak.\n\n"
        f"💰 **Qancha pul o'tkazdingiz?** (Faqat raqamlar bilan yozing, masalan: 50000):"
    )
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=get_cancel_keyboard())

@bot.message_handler(func=lambda message: message.text == '💸 Pul Yechish')
def withdraw_init_handler(message):
    user_id = message.from_user.id
    user = db_service.get_user(user_id)
    if not user:
        return
        
    min_with = float(db_service.get_setting('min_withdrawal', str(config.MIN_WITHDRAWAL)))
    if user['balance'] < min_with:
        bot.send_message(
            user_id,
            f"❌ **Balansingiz yetarli emas!**\n\n"
            f"Minimal yechib olish miqdori: **{format_money(min_with)}**\n"
            f"Sizning balansingiz: **{format_money(user['balance'])}**"
        )
        return
        
    set_user_state(user_id, state='WITHDRAWAL_CARD')
    msg = (
        f"💸 **Pul yechish (Kassa):**\n\n"
        f"Sizning balansingiz: **{format_money(user['balance'])}**\n"
        f"Minimal yechish: **{format_money(min_with)}**\n\n"
        f"💳 **Pul o'tkaziladigan karta raqamini kiriting:**\n"
        f"(Karta raqamini va agar kerak bo'lsa egasining ismini ham yozishingiz mumkin, masalan: 8600123456789012 - Ali Valiyev):"
    )
    bot.send_message(user_id, msg, reply_markup=get_cancel_keyboard())

@bot.message_handler(func=lambda message: message.text == '📈 Investitsiya')
def invest_init_handler(message):
    user_id = message.from_user.id
    user = db_service.get_user(user_id)
    if not user:
        return
        
    user_invs = db_service.get_user_investments(user_id)
    active_invs = [i for i in user_invs if i['status'] == 'active']
    min_dep = float(db_service.get_setting('min_deposit', str(config.MIN_DEPOSIT)))
    
    msg = (
        f"📈 **Investitsiya bo'limi**\n\n"
        f"Sarmoya kiriting va pulingizni har kuni **25%** ga ko'paytiring!\n"
        f"⏳ Minimal investitsiya muddati: **7 kun**.\n"
        f"Foyda har kuni hisoblab boriladi va muddat yakunida sarmoyangiz bilan birga balansingizga qo'shiladi.\n\n"
        f"📊 **Misol uchun:**\n"
        f"- 100,000 so'm investitsiya qilsangiz:\n"
        f"  Kuniga: 25,000 so'mdan foyda\n"
        f"  7 kunda jami foyda: 175,000 so'm\n"
        f"  💰 Yakunda balansingizga qo'shiladi: **275,000 so'm**\n\n"
        f"💵 Sizning balansingiz: **{format_money(user['balance'])}**\n"
        f"⚠️ Minimal investitsiya miqdori: **{format_money(min_dep)}**\n\n"
    )
    
    if len(active_invs) > 0:
        msg += f"💼 **Sizning faol investitsiyalaringiz:**\n"
        for index, inv in enumerate(active_invs):
            try:
                start_dt = datetime.fromisoformat(inv['start_date'].replace('Z', ''))
                now_dt = datetime.now()
                elapsed_days = (now_dt - start_dt).days
            except Exception:
                elapsed_days = 0
                
            actual_elapsed = min(elapsed_days, inv['duration_days'])
            current_profit = inv['amount'] * 0.25 * actual_elapsed
            expected_total = inv['amount'] * (1.0 + 0.25 * inv['duration_days'])
            
            msg += (
                f"\n{index + 1}. **ID: #INV_{inv['id']}**\n"
                f"   Sarmoya: {format_money(inv['amount'])}\n"
                f"   Kunlar: {actual_elapsed}/{inv['duration_days']} kun o'tdi\n"
                f"   Joriy foyda: +{format_money(current_profit)}\n"
                f"   Kutilayotgan umumiy: {format_money(expected_total)}\n"
                f"   Tugash vaqti: {format_date(inv['end_date'])}\n"
            )
        msg += "\n"
        
    set_user_state(user_id, state='INVEST_AMOUNT')
    bot.send_message(
        user_id,
        msg + f"💰 **Investitsiya qilmoqchi bo'lgan miqdoringizni yozing:**\n(Faqat raqamlar bilan, masalan: 100000):",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )

# Inline Callbacks
@bot.callback_query_handler(func=lambda call: call.data == 'admin_conf_min_dep')
def callback_min_dep(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
    set_user_state(user_id, state='ADMIN_SET_MIN_DEP')
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        "💳 **Minimal depozit miqdorini o'zgartirish:**\n\nYangi miqdorni yozing (masalan: 15000):",
        reply_markup=get_cancel_keyboard(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_conf_min_with')
def callback_min_with(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
    set_user_state(user_id, state='ADMIN_SET_MIN_WITHDRAW')
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        "💸 **Minimal yechish miqdorini o'zgartirish:**\n\nYangi miqdorni yozing (masalan: 20000):",
        reply_markup=get_cancel_keyboard(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_conf_ref_bonus')
def callback_ref_bonus(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
    set_user_state(user_id, state='ADMIN_SET_REF_BONUS')
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        "👥 **Referal bonus miqdorini o'zgartirish:**\n\nYangi bonus miqdorini yozing (masalan: 2000):",
        reply_markup=get_cancel_keyboard(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_panel_back')
def callback_panel_back(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
    bot.answer_callback_query(call.id)
    reset_user_state(user_id)
    bot.send_message(user_id, "👨‍💻 Admin panel bosh sahifasi:", reply_markup=get_admin_keyboard())

# Regex Inline Actions for Admin User Lookup
@bot.callback_query_handler(func=lambda call: re.match(r'^admin_bal_(add|sub|set)_(\d+)$', call.data))
def callback_admin_bal_action(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
        
    match = re.match(r'^admin_bal_(add|sub|set)_(\d+)$', call.data)
    action = match.group(1)
    target_id = int(match.group(2))
    
    target_user = db_service.get_user(target_id)
    if not target_user:
        bot.send_message(user_id, "❌ Foydalanuvchi topilmadi.")
        return
        
    set_user_state(
        user_id,
        state='ADMIN_CHANGE_BALANCE_AMOUNT',
        lookup_user_id=target_id,
        lookup_user_action=action
    )
    
    action_text = ''
    if action == 'add':
        action_text = "qo'shmoqchi bo'lgan"
    elif action == 'sub':
        action_text = "ayirmoqchi bo'lgan"
    elif action == 'set':
        action_text = "o'rnatmoqchi bo'lgan yangi"
        
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        f"💰 Foydalanuvchi: {target_user['first_name']} ({target_user['id']})\n"
        f"Joriy balans: {format_money(target_user['balance'])}\n\n"
        f"Foydalanuvchi balansiga {action_text} miqdorni yozing:",
        reply_markup=get_cancel_keyboard()
    )

# Approve/Reject deposits
@bot.callback_query_handler(func=lambda call: re.match(r'^deposit_app_(\d+)$', call.data))
def callback_deposit_approve(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
        
    match = re.match(r'^deposit_app_(\d+)$', call.data)
    deposit_id = int(match.group(1))
    
    deposit = db_service.get_deposit(deposit_id)
    if not deposit:
        bot.send_message(user_id, "❌ Depozit so'rovi topilmadi.")
        return
        
    if deposit['status'] != 'pending':
        bot.send_message(user_id, f"❌ Bu so'rov allaqachon qayta ishlangan. Holat: {deposit['status']}")
        return
        
    db_service.update_deposit_status(deposit_id, 'approved')
    db_service.update_balance(deposit['user_id'], deposit['amount'])
    
    bot.answer_callback_query(call.id, "Depozit tasdiqlandi")
    
    try:
        bot.edit_message_caption(
            chat_id=user_id,
            message_id=call.message.message_id,
            caption=f"✅ **Depozit Tasdiqlandi (ID: #{deposit_id})**\n\n"
                    f"👤 Foydalanuvchi: {deposit['user_id']} ga **{format_money(deposit['amount'])}** qo'shildi.",
            reply_markup=None
        )
    except Exception:
        bot.send_message(user_id, f"✅ Depozit #{deposit_id} tasdiqlandi.")
        
    try:
        bot.send_message(
            deposit['user_id'],
            f"🎉 **Depozitingiz tasdiqlandi!**\n\n"
            f"Balansingizga **+{format_money(deposit['amount'])}** muvaffaqiyatli qo'shildi.\n"
            f"Hozirda bemalol investitsiya qilishingiz mumkin!",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
    except Exception as e:
        print('Failed to notify user about deposit approval:', e)

@bot.callback_query_handler(func=lambda call: re.match(r'^deposit_rej_(\d+)$', call.data))
def callback_deposit_reject(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
        
    match = re.match(r'^deposit_rej_(\d+)$', call.data)
    deposit_id = int(match.group(1))
    
    deposit = db_service.get_deposit(deposit_id)
    if not deposit:
        bot.send_message(user_id, "❌ Depozit so'rovi topilmadi.")
        return
        
    if deposit['status'] != 'pending':
        bot.send_message(user_id, f"❌ Bu so'rov allaqachon qayta ishlangan. Holat: {deposit['status']}")
        return
        
    db_service.update_deposit_status(deposit_id, 'rejected')
    
    bot.answer_callback_query(call.id, "Depozit rad etildi")
    
    try:
        bot.edit_message_caption(
            chat_id=user_id,
            message_id=call.message.message_id,
            caption=f"❌ **Depozit Rad Etildi (ID: #{deposit_id})**\n\n"
                    f"Foydalanuvchi: {deposit['user_id']}\n"
                    f"Miqdor: {format_money(deposit['amount'])}",
            reply_markup=None
        )
    except Exception:
        bot.send_message(user_id, f"❌ Depozit #{deposit_id} rad etildi.")
        
    try:
        bot.send_message(
            deposit['user_id'],
            f"❌ **Depozitingiz rad etildi!**\n\n"
            f"Siz yuborgan **{format_money(deposit['amount'])}** lik to'lov skrinshoti tasdiqlanmadi.\n"
            f"Muammo yuzasidan adminga murojaat qiling.",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
    except Exception as e:
        print('Failed to notify user about deposit rejection:', e)

# Approve/Reject withdrawals
@bot.callback_query_handler(func=lambda call: re.match(r'^withdraw_app_(\d+)$', call.data))
def callback_withdraw_approve(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
        
    match = re.match(r'^withdraw_app_(\d+)$', call.data)
    withdrawal_id = int(match.group(1))
    
    withdrawal = db_service.get_withdrawal(withdrawal_id)
    if not withdrawal:
        bot.send_message(user_id, "❌ Pul yechish so'rovi topilmadi.")
        return
        
    if withdrawal['status'] != 'pending':
        bot.send_message(user_id, f"❌ Bu so'rov allaqachon qayta ishlangan. Holat: {withdrawal['status']}")
        return
        
    db_service.update_withdrawal_status(withdrawal_id, 'approved')
    
    bot.answer_callback_query(call.id, "Pul yechish tasdiqlandi")
    
    try:
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=f"✅ **Pul Yechish Tasdiqlandi (ID: #{withdrawal_id})**\n\n"
                 f"Foydalanuvchi: {withdrawal['user_id']}\n"
                 f"Karta: `{withdrawal['card_number']}`\n"
                 f"Miqdor: **{format_money(withdrawal['amount'])}** o'tkazib berildi.",
            parse_mode='Markdown',
            reply_markup=None
        )
    except Exception:
        bot.send_message(user_id, f"✅ Pul yechish #{withdrawal_id} tasdiqlandi.")
        
    try:
        bot.send_message(
            withdrawal['user_id'],
            f"🎉 **Pul yechish so'rovingiz tasdiqlandi!**\n\n"
            f"Karta: `{withdrawal['card_number']}`\n"
            f"Miqdor: **{format_money(withdrawal['amount'])}** o'tkazib berildi.\n"
            f"Hisobingizni tekshirib ko'ring!",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
    except Exception as e:
        print('Failed to notify user about withdrawal approval:', e)

@bot.callback_query_handler(func=lambda call: re.match(r'^withdraw_rej_(\d+)$', call.data))
def callback_withdraw_reject(call):
    user_id = call.from_user.id
    if user_id != config.ADMIN_ID:
        return
        
    match = re.match(r'^withdraw_rej_(\d+)$', call.data)
    withdrawal_id = int(match.group(1))
    
    withdrawal = db_service.get_withdrawal(withdrawal_id)
    if not withdrawal:
        bot.send_message(user_id, "❌ Pul yechish so'rovi topilmadi.")
        return
        
    if withdrawal['status'] != 'pending':
        bot.send_message(user_id, f"❌ Bu so'rov allaqachon qayta ishlangan. Holat: {withdrawal['status']}")
        return
        
    db_service.update_withdrawal_status(withdrawal_id, 'rejected')
    db_service.update_balance(withdrawal['user_id'], withdrawal['amount'])
    
    bot.answer_callback_query(call.id, "Pul yechish rad etildi, pul qaytarildi")
    
    try:
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=f"❌ **Pul Yechish Rad Etildi (ID: #{withdrawal_id})**\n\n"
                 f"Foydalanuvchi: {withdrawal['user_id']}\n"
                 f"Karta: `{withdrawal['card_number']}`\n"
                 f"Miqdor: **{format_money(withdrawal['amount'])}** qaytarildi.",
            parse_mode='Markdown',
            reply_markup=None
        )
    except Exception:
        bot.send_message(user_id, f"❌ Pul yechish #{withdrawal_id} rad etildi, mablag' qaytarildi.")
        
    try:
        bot.send_message(
            withdrawal['user_id'],
            f"❌ **Pul yechish so'rovingiz rad etildi!**\n\n"
            f"Miqdor: **{format_money(withdrawal['amount'])}** balansingizga qaytarildi.\n"
            f"Muammo bo'lsa adminga murojaat qiling.",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
    except Exception as e:
        print('Failed to notify user about withdrawal rejection:', e)

# Generic message handler for state inputs
@bot.message_handler(content_types=['text', 'photo', 'document', 'video', 'voice'])
def generic_message_handler(message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # Check for ADMIN_BROADCAST first as it accepts all content types
    if user_state.state == 'ADMIN_BROADCAST':
        if user_id != config.ADMIN_ID:
            return
            
        reset_user_state(user_id)
        bot.send_message(user_id, "⏳ Xabar barcha foydalanuvchilarga yuborilmoqda. Iltimos kuting...")
        
        user_ids = db_service.get_all_user_ids()
        success = 0
        failed = 0
        
        for target_user_id in user_ids:
            try:
                bot.copy_message(
                    chat_id=target_user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                success += 1
            except Exception:
                failed += 1
                
        bot.send_message(
            user_id,
            f"📢 **Xabar tarqatish yakunlandi!**\n\n"
            f"✅ Muvaffaqiyatli: {success} ta\n"
            f"❌ Muvaffaqiyatsiz: {failed} ta",
            reply_markup=get_admin_keyboard(),
            parse_mode='Markdown'
        )
        return

    text = message.text or ""

    # DEPOSIT_AMOUNT
    if user_state.state == 'DEPOSIT_AMOUNT':
        try:
            amount = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting (masalan: 50000):")
            return
            
        if amount <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting (masalan: 50000):")
            return
            
        min_dep = float(db_service.get_setting('min_deposit', str(config.MIN_DEPOSIT)))
        if amount < min_dep:
            bot.send_message(
                user_id,
                f"❌ Minimal depozit miqdori: **{format_money(min_dep)}**.\nIltimos, qayta kiriting:",
                parse_mode='Markdown'
            )
            return
            
        set_user_state(user_id, state='DEPOSIT_SCREENSHOT', deposit_amount=amount)
        bot.send_message(
            user_id,
            f"💸 Katta rahmat!\n"
            f"Miqdor: **{format_money(amount)}**\n\n"
            f"Endi ushbu to'lovni tasdiqlovchi **skrinshot (check rasm ko'rinishida)** ni botga yuboring:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return

    # DEPOSIT_SCREENSHOT
    if user_state.state == 'DEPOSIT_SCREENSHOT':
        if message.content_type != 'photo':
            bot.send_message(
                user_id,
                "❌ Iltimos, faqat rasm (screenshot) shaklida to'lov chekini yuboring. "
                "Amaldagi chekni bekor qilish uchun pastdagi tugmani bosing:"
            )
            return
            
        photo_file_id = message.photo[-1].file_id
        amount = user_state.deposit_amount
        
        deposit = db_service.create_deposit(user_id, amount, photo_file_id)
        reset_user_state(user_id)
        
        bot.send_message(
            user_id,
            "✅ **To'lov ma'lumotlari adminga tasdiqlash uchun yuborildi.**\n"
            "Iltimos biroz kuting, admin tomonidan tekshirilib tasdiqlangach pul hisobingizga tushadi.",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
        
        try:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"deposit_app_{deposit['id']}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"deposit_rej_{deposit['id']}")
            )
            
            caption = (
                f"📥 **Yangi Depozit So'rovi (ID: #{deposit['id']})**\n\n"
                f"👤 Foydalanuvchi: {message.from_user.first_name} {f'(@{message.from_user.username})' if message.from_user.username else ''}\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"💰 Miqdor: **{format_money(amount)}**\n\n"
                f"Iltimos, depozit to'lovini tekshirib tasdiqlang:"
            )
            
            bot.send_photo(
                config.ADMIN_ID,
                photo_file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            print('Failed to notify admin about new deposit:', e)
        return

    # WITHDRAWAL_CARD
    if user_state.state == 'WITHDRAWAL_CARD':
        if not text or len(text.strip()) < 8:
            bot.send_message(user_id, "❌ Iltimos, to'g'ri karta ma'lumotlarini kiriting (masalan: 8600123456789012):")
            return
            
        set_user_state(user_id, state='WITHDRAWAL_AMOUNT', withdraw_card=text)
        user = db_service.get_user(user_id)
        
        bot.send_message(
            user_id,
            f"💳 Karta: `{text}`\n\n"
            f"Endi balansingizdan yechmoqchi bo'lgan miqdorni kiriting (faqat raqamlar bilan):\n"
            f"Sizning balansingiz: **{format_money(user['balance'])}**",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return

    # WITHDRAWAL_AMOUNT
    if user_state.state == 'WITHDRAWAL_AMOUNT':
        try:
            amount = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat son yozing (masalan: 50000):")
            return
            
        if amount <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat son yozing (masalan: 50000):")
            return
            
        user = db_service.get_user(user_id)
        min_with = float(db_service.get_setting('min_withdrawal', str(config.MIN_WITHDRAWAL)))
        
        if amount < min_with:
            bot.send_message(user_id, f"❌ Minimal yechish miqdori: **{format_money(min_with)}**.\nQayta kiriting:")
            return
            
        if amount > user['balance']:
            bot.send_message(user_id, f"❌ Balansingizda mablag' yetarli emas!\nBalansingiz: **{format_money(user['balance'])}**\nQayta kiriting:")
            return
            
        # Deduct balance immediately
        db_service.update_balance(user_id, -amount)
        withdrawal = db_service.create_withdrawal(user_id, amount, user_state.withdraw_card)
        reset_user_state(user_id)
        
        bot.send_message(
            user_id,
            "✅ **Pul yechish so'rovingiz adminga yuborildi.**\n"
            "Biroz kuting, admin tomonidan to'lov amalga oshirilgach sizga xabar beriladi.",
            reply_markup=get_user_keyboard()
        )
        
        try:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ To'lov qilindi (Tasdiqlash)", callback_data=f"withdraw_app_{withdrawal['id']}"),
                InlineKeyboardButton("❌ Rad etish (Pulni qaytarish)", callback_data=f"withdraw_rej_{withdrawal['id']}")
            )
            
            msg = (
                f"📤 **Yangi Pul Yechish So'rovi (ID: #{withdrawal['id']})**\n\n"
                f"👤 Foydalanuvchi: {message.from_user.first_name} {f'(@{message.from_user.username})' if message.from_user.username else ''}\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"💳 Karta: `{user_state.withdraw_card}`\n"
                f"💰 Yechish miqdori: **{format_money(amount)}**\n\n"
                f"To'lovni amalga oshirgach quyidagi tugmalarni bosing:"
            )
            
            bot.send_message(
                config.ADMIN_ID,
                msg,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            print('Failed to notify admin about withdrawal:', e)
        return

    # INVEST_AMOUNT
    if user_state.state == 'INVEST_AMOUNT':
        try:
            amount = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting (masalan: 100000):")
            return
            
        if amount <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting (masalan: 100000):")
            return
            
        user = db_service.get_user(user_id)
        min_dep = float(db_service.get_setting('min_deposit', str(config.MIN_DEPOSIT)))
        
        if amount < min_dep:
            bot.send_message(user_id, f"❌ Minimal investitsiya miqdori: **{format_money(min_dep)}**.\nQayta kiriting:")
            return
            
        if amount > user['balance']:
            bot.send_message(
                user_id,
                f"❌ Balansingizda sarmoya kiritish uchun yetarli mablag' yo'q!\n"
                f"Balansingiz: **{format_money(user['balance'])}**\n"
                f"Iltimos, avval depozit qiling yoki kamroq miqdor kiriting:"
            )
            return
            
        set_user_state(user_id, state='INVEST_DURATION', invest_amount=amount)
        bot.send_message(
            user_id,
            f"💰 Sarmoya miqdori: **{format_money(amount)}**\n\n"
            f"Necha kunga investitsiya kiritmoqchisiz?\n"
            f"📅 **Eng kam muddat: 7 kun**\n"
            f"Kunlik daromad: **25%**\n\n"
            f"Iltimos, kunlar sonini yozing (faqat raqamlar, masalan: 7):",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        return

    # INVEST_DURATION
    if user_state.state == 'INVEST_DURATION':
        try:
            days = int(text)
        except ValueError:
            bot.send_message(user_id, "❌ Eng kam investitsiya muddati 7 kun bo'lishi kerak. Iltimos, 7 yoki undan katta son kiriting:")
            return
            
        if days < 7:
            bot.send_message(user_id, "❌ Eng kam investitsiya muddati 7 kun bo'lishi kerak. Iltimos, 7 yoki undan katta son kiriting:")
            return
            
        amount = user_state.invest_amount
        user = db_service.get_user(user_id)
        
        if amount > user['balance']:
            reset_user_state(user_id)
            bot.send_message(user_id, "❌ Xatolik: Balansingizda yetarli mablag' qolmadi.", reply_markup=get_user_keyboard())
            return
            
        db_service.update_balance(user_id, -amount)
        inv = db_service.create_investment(user_id, amount, days)
        reset_user_state(user_id)
        
        daily_profit = amount * 0.25
        total_profit = daily_profit * days
        expected_payout = amount + total_profit
        
        bot.send_message(
            user_id,
            f"✅ **Investitsiya muvaffaqiyatli boshlandi!**\n\n"
            f"📈 Investitsiya ID: `#INV_{inv['id']}`\n"
            f"💰 Kiritilgan sarmoya: **{format_money(amount)}**\n"
            f"📅 Muddat: **{days} kun**\n"
            f"🔥 Kunlik foyda: **25% (+{format_money(daily_profit)})**\n"
            f"💸 Kutilayotgan jami foyda: **+{format_money(total_profit)}**\n"
            f"💰 Yakuniy umumiy to'lov: **{format_money(expected_payout)}**\n"
            f"⏳ Tugash sanasi: **{format_date(inv['end_date'])}**\n\n"
            f"Muddati tugagach, barcha pul va daromad avtomatik ravishda balansingizga qaytadi!",
            parse_mode='Markdown',
            reply_markup=get_user_keyboard()
        )
        return

    # ADMIN_CARD_CHANGE
    if user_state.state == 'ADMIN_CARD_CHANGE':
        if user_id != config.ADMIN_ID:
            return
        if not text or len(text.strip()) == 0:
            bot.send_message(user_id, "❌ Karta ma'lumotlari bo'sh bo'lishi mumkin emas. Iltimos yozing:")
            return
            
        db_service.set_setting('card_details', text)
        reset_user_state(user_id)
        bot.send_message(
            user_id,
            f"✅ **Karta ma'lumotlari yangilandi!**\n\nYangi karta:\n`{text}`",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )
        return

    # ADMIN_SET_MIN_DEP
    if user_state.state == 'ADMIN_SET_MIN_DEP':
        if user_id != config.ADMIN_ID:
            return
        try:
            val = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        if val <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        db_service.set_setting('min_deposit', str(val))
        reset_user_state(user_id)
        bot.send_message(user_id, f"✅ **Minimal depozit miqdori o'rnatildi:** {format_money(val)}", reply_markup=get_admin_keyboard())
        return

    # ADMIN_SET_MIN_WITHDRAW
    if user_state.state == 'ADMIN_SET_MIN_WITHDRAW':
        if user_id != config.ADMIN_ID:
            return
        try:
            val = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        if val <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        db_service.set_setting('min_withdrawal', str(val))
        reset_user_state(user_id)
        bot.send_message(user_id, f"✅ **Minimal yechish miqdori o'rnatildi:** {format_money(val)}", reply_markup=get_admin_keyboard())
        return

    # ADMIN_SET_REF_BONUS
    if user_state.state == 'ADMIN_SET_REF_BONUS':
        if user_id != config.ADMIN_ID:
            return
        try:
            val = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        if val <= 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        db_service.set_setting('referral_bonus', str(val))
        reset_user_state(user_id)
        bot.send_message(user_id, f"✅ **Referal bonus miqdori o'rnatildi:** {format_money(val)}", reply_markup=get_admin_keyboard())
        return

    # ADMIN_SET_MIN_REF
    if user_state.state == 'ADMIN_SET_MIN_REF':
        if user_id != config.ADMIN_ID:
            return
        try:
            val = int(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam yoki 0 kiriting:")
            return
            
        if val < 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam yoki 0 kiriting:")
            return
            
        db_service.set_setting('min_referrals', str(val))
        reset_user_state(user_id)
        bot.send_message(user_id, f"✅ **Minimal referal soni o'rnatildi:** {val} ta", reply_markup=get_admin_keyboard())
        return

    # ADMIN_USER_LOOKUP
    if user_state.state == 'ADMIN_USER_LOOKUP':
        if user_id != config.ADMIN_ID:
            return
            
        target_user = None
        try:
            parsed_id = int(text)
            target_user = db_service.get_user(parsed_id)
        except ValueError:
            target_user = db_service.get_user_by_username(text)
            
        if not target_user:
            bot.send_message(user_id, "❌ Bunday foydalanuvchi topilmadi. Qayta kiriting (ID yoki username):")
            return
            
        reset_user_state(user_id)
        ref_count = db_service.get_referral_count(target_user['id'])
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("➕ Balans qo'shish", callback_data=f"admin_bal_add_{target_user['id']}"),
            InlineKeyboardButton("➖ Balans ayirish", callback_data=f"admin_bal_sub_{target_user['id']}")
        )
        markup.row(
            InlineKeyboardButton("✏️ Balans o'rnatish", callback_data=f"admin_bal_set_{target_user['id']}"),
            InlineKeyboardButton("🏠 Admin Panel", callback_data="admin_panel_back")
        )
        
        msg = (
            f"🔍 **Foydalanuvchi ma'lumotlari:**\n\n"
            f"👤 Ism: {target_user['first_name']}\n"
            f"🆔 ID: `{target_user['id']}`\n"
            f"👤 Username: {f'@{target_user['username']}' if target_user['username'] else 'yo\'q'}\n"
            f"💰 Balans: **{format_money(target_user['balance'])}**\n"
            f"👥 Taklif etilgan do'stlar: **{ref_count} ta**\n"
            f"📅 Ro'yxatdan o'tgan: {format_date(target_user['created_at'])}\n\n"
            f"Balansni o'zgartirish:"
        )
        bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=markup)
        return

    # ADMIN_CHANGE_BALANCE_AMOUNT
    if user_state.state == 'ADMIN_CHANGE_BALANCE_AMOUNT':
        if user_id != config.ADMIN_ID:
            return
        try:
            amount = float(text)
        except ValueError:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        if amount < 0:
            bot.send_message(user_id, "❌ Iltimos, musbat raqam kiriting:")
            return
            
        target_id = user_state.lookup_user_id
        action = user_state.lookup_user_action
        
        target_user = db_service.get_user(target_id)
        if not target_user:
            reset_user_state(user_id)
            bot.send_message(user_id, "❌ Foydalanuvchi topilmadi.", reply_markup=get_admin_keyboard())
            return
            
        if action == 'add':
            db_service.update_balance(target_id, amount)
            bot.send_message(user_id, f"✅ {target_user['first_name']} balansiga **+{format_money(amount)}** qo'shildi.", reply_markup=get_admin_keyboard())
            try:
                bot.send_message(target_id, f"💰 Balansingizga admin tomonidan **+{format_money(amount)}** qo'shildi!")
            except Exception:
                pass
        elif action == 'sub':
            db_service.update_balance(target_id, -amount)
            bot.send_message(user_id, f"✅ {target_user['first_name']} balansidan **-{format_money(amount)}** ayirildi.", reply_markup=get_admin_keyboard())
            try:
                bot.send_message(target_id, f"💰 Balansingizdan admin tomonidan **-{format_money(amount)}** ayirildi.")
            except Exception:
                pass
        elif action == 'set':
            db_service.set_balance(target_id, amount)
            bot.send_message(user_id, f"✅ {target_user['first_name']} balansi **{format_money(amount)}** deb belgilandi.", reply_markup=get_admin_keyboard())
            try:
                bot.send_message(target_id, f"💰 Balansingiz admin tomonidan **{format_money(amount)}** qilib o'rnatildi!")
            except Exception:
                pass
                
        reset_user_state(user_id)
        return

# Scheduler for checking investments
def check_completed_investments():
    while True:
        try:
            active = db_service.get_active_investments()
            now = datetime.now()
            for inv in active:
                try:
                    end_date_str = inv['end_date'].replace('Z', '')
                    if '.' in end_date_str:
                        end_dt = datetime.strptime(end_date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                    else:
                        end_dt = datetime.fromisoformat(end_date_str)
                except Exception:
                    continue
                
                if now >= end_dt:
                    db_service.complete_investment(inv['id'])
                    daily_profit = inv['amount'] * 0.25
                    total_profit = daily_profit * inv['duration_days']
                    payout = inv['amount'] + total_profit
                    
                    db_service.update_balance(inv['user_id'], payout)
                    
                    try:
                        bot.send_message(
                            inv['user_id'],
                            f"🎉 **Investitsiya muddati yakunlandi!**\n\n"
                            f"📈 ID: `#INV_{inv['id']}`\n"
                            f"💰 Kiritilgan sarmoya: **{format_money(inv['amount'])}**\n"
                            f"📅 Muddat: **{inv['duration_days']} kun**\n"
                            f"🔥 Kunlik foyda: **25%** (+{format_money(daily_profit)})\n"
                            f"💸 Umumiy ko'rilgan foyda: **+{format_money(total_profit)}**\n"
                            f"💰 Balansingizga jami **{format_money(payout)}** o'tkazildi!",
                            parse_mode='Markdown'
                        )
                    except Exception as err:
                        print(f"Could not notify user {inv['user_id']} about completed investment: {err}")
        except Exception as e:
            print("Error in checking completed investments:", e)
            
        time.sleep(30)

# Dummy web server to keep Render deployment alive
class DummyHTTPServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running successfully!\n")

def run_http_server():
    port = int(os.getenv('PORT', '3000'))
    try:
        server = HTTPServer(('0.0.0.0', port), DummyHTTPServer)
        print(f"Web server listening on port {port} to keep Render deployment alive.")
        server.serve_forever()
    except Exception as e:
        print("Failed to start Web Server:", e)

if __name__ == '__main__':
    # Start scheduler thread
    scheduler_thread = threading.Thread(target=check_completed_investments, daemon=True)
    scheduler_thread.start()
    
    # Start web server thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    print("🚀 Investment & Referral Bot starts successfully!")
    try:
        bot.infinity_polling(skip_pending=False)
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print("Error during bot polling:", e)
