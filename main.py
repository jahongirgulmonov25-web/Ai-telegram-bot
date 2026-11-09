import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# --- SOZLAMALAR ---
TELEGRAM_BOT_TOKEN = "9045580405:AAHoWen54NL3Cx4stuaXSOOGs2quOzYZs0w"
GEMINI_API_KEY = "AQ.Ab8RN6KQfDoGanOPoKlR8plFZNJVkp7KIdne09gQKis-kiRs0A"

# Gemini AI sozlamasi (Claude kabi insoniy yozishi uchun System Instruction)
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=(
        "Siz o'ta aqlli, samimiy, adabiy va insoniy tilda muloqot qiladigan yordamchisiz. "
        "Javoblaringiz quruq robotik tarzda emas, xuddi jonli inson suhbatlashayotgandek "
        "ravon, tushunarli va ta'sirchan bo'lsin. Ortiqcha rasmiyatchilikdan qoching."
    )
)

# --- BAZA BILAN ISHLASH (SQLite) ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance_requests INTEGER DEFAULT 5,
            is_premium INTEGER DEFAULT 0,
            referred_by INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance_requests, is_premium FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance_requests, is_premium) VALUES (?, 5, 0)", (user_id,))
        conn.commit()
        row = (5, 0)
    conn.close()
    return row

def update_balance(user_id, amount):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_requests = balance_requests + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- BOTNI ISHGA TUSHIRISH ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Referral tizimi (Agar boshqa birovning havolasi orqali kirgan bo'lsa)
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
            res = cursor.fetchone()
            if res and res[0] is None:
                cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (ref_id, user_id))
                cursor.execute("UPDATE users SET balance_requests = balance_requests + 3 WHERE user_id = ?", (ref_id,))
                conn.commit()
                try:
                    await bot.send_message(ref_id, "🎉 Tabriklaymiz! Yangi do'stingiz havolangiz orqali qo'shildi va sizga **+3 ta bepul urinish** qo'shildi!")
                except:
                    pass
            conn.close()

    get_user(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Bepul urinish olish (Referral)", callback_data="get_ref")],
        [InlineKeyboardButton(text="💎 Premium Sotib Olish", callback_data="buy_premium")]
    ])
    
    await message.answer(
        "Salom! Men sizning shaxsiy va aqlli AI yordamchingisiman.\n"
        "Menga istalgan savol yuboring, matn tuzib beraman yoki matnlaringizni xuddi inson yozgandek qayta ishlab beraman.\n\n"
        "📌 Har bir foydalanuvchiga **5 ta bepul urinish** berilgan.",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "get_ref")
async def process_ref(callback: types.CallbackQuery):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    await callback.message.answer(
        f"🔗 **Sizning shaxsiy havolangiz:**\n{ref_link}\n\n"
        f"Ushbu havolani do'stlaringizga yuboring. Har bir qo'shilgan do'st uchun sizga **+3 ta bepul urinish** beriladi!"
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_premium")
async def process_premium(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Click / Payme orqali to'lash", url="https://t.me/SIZNING_ADMIN_USERNAME")]
    ])
    await callback.message.answer(
        "💎 **Premium Obuna (Cheksiz so'rovlar):**\n"
        "• Kunlik cheklovlarsiz muloqot\n"
        "• Eng tezkor va kuchli rejim\n\n"
        "Narxi: Oyiga **15,000 so'm**.\n"
        "Sotib olish uchun quyidagi tugmani bosing:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    balance, is_premium = get_user(user_id)
    
    # Agar premium bo'lmasa va balansi tugagan bo'lsa
    if is_premium == 0 and balance <= 0:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Bepul urinish olish", callback_data="get_ref")],
            [InlineKeyboardButton(text="💎 Premium olish", callback_data="buy_premium")]
        ])
        await message.answer(
            "❌ Bepul urinishlaringiz tugadi!\n\n"
            "Davom etish uchun do'stlaringizni taklif qiling yoki Premium obuna oling.",
            reply_markup=keyboard
        )
        return

    # AI dan javob olish
    processing_msg = await message.answer("⏳ O'ylayapman...")
    
    try:
        response = ai_model.generate_content(message.text)
        answer_text = response.text
        
        # Agar foydalanuvchi premium bo'lmasa, bitta urinishni ayiramiz
        if is_premium == 0:
            update_balance(user_id, -1)
            remaining = balance - 1
            answer_text += f"\n\n*(Qolgan bepul urinishlaringiz: {remaining} ta)*"
            
        await bot.edit_message_text(answer_text, chat_id=message.chat.id, message_id=processing_msg.message_id)
    except Exception as e:
        await bot.edit_message_text("❌ Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.", chat_id=message.chat.id, message_id=processing_msg.message_id)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
