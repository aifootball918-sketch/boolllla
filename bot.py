import sqlite3
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

BOT_TOKEN = "8740301786:AAHRxv9tD58U-kyjpqecpPupxMxWEV5-m_U"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- DATABASE SETUP ---
conn = sqlite3.connect("hisobchi.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS goal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_amount REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT, -- 'in' (kirdi) yoki 'out' (chiqdi)
    amount REAL
)
""")
conn.commit()


# --- FSM (STATE) HOLATLAR ---
class FinanceStates(StatesGroup):
    waiting_for_add = State()
    waiting_for_spend = State()
    waiting_for_goal = State()


# --- ASOSIY TUGMALAR (REPLY KEYBOARD) ---
def get_reply_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Pul qo'shish"), KeyboardButton(text="📤 Pul ishlatish")],
            [KeyboardButton(text="🎯 Maqsad qo'yish"), KeyboardButton(text="📊 Umumiy Hisobot")]
        ],
        resize_keyboard=True
    )
    return kb


# --- HANDLERLAR ---

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "👋 **Hisobchi Botga xush kelibsiz!**\n\n"
        "Siz quyidagi amallarni bajarishingiz mumkin:\n"
        "• To'g'ridan-to'g'ri yozish: `Ali 50000` yoki `Ali -20000`\n"
        "• Yoki pastdagi tugmalar yordamida oson boshqaring 👇"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_reply_keyboard())


@dp.message(F.text == "📊 Umumiy Hisobot")
async def show_stat_btn(message: Message):
    await show_stat_logic(message)


@dp.message(Command("stat"))
async def show_stat_cmd(message: Message):
    await show_stat_logic(message)


async def show_stat_logic(message: Message):
    # Maqsadni olish
    cursor.execute("SELECT target_amount FROM goal ORDER BY id DESC LIMIT 1")
    goal_row = cursor.fetchone()
    target_amount = goal_row[0] if goal_row else 0

    # Jami yig'ilgan va ishlatilgan
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='in'")
    total_in = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='out'")
    total_out = cursor.fetchone()[0] or 0

    balance = total_in - total_out
    remaining = max(0, target_amount - balance)

    # Odamlar kesimida
    cursor.execute("""
        SELECT name, 
               SUM(CASE WHEN type='in' THEN amount ELSE 0 END) as in_amt,
               SUM(CASE WHEN type='out' THEN amount ELSE 0 END) as out_amt
        FROM transactions 
        GROUP BY name
    """)
    people = cursor.fetchall()

    msg = f"📊 **UMUMIY HISOBOT**\n\n"
    msg += f"🎯 **Maqsad:** {target_amount:,.0f} so'm\n"
    msg += f"📥 **Jami Yig'ilgan:** {total_in:,.0f} so'm\n"
    msg += f"📤 **Jami Ishlatilgan:** {total_out:,.0f} so'm\n"
    msg += f"💰 **Kassada Bori (Balans):** {balance:,.0f} so'm\n"
    
    if target_amount > 0:
        msg += f"⏳ **Maqsadga Qolgani:** {remaining:,.0f} so'm\n"

    msg += "\n👥 **A'zolar bo'yicha:**\n"
    if people:
        for name, p_in, p_out in people:
            msg += f"• **{name}**: +{p_in:,.0f} so'm | -{p_out:,.0f} so'm\n"
    else:
        msg += "Hali hech qanday amaliyot bajarilmadi."

    await message.answer(msg, parse_mode="Markdown", reply_markup=get_reply_keyboard())


# --- TUGMA BOSILGANDA HOLATLARNI BOSHQARISH ---

@dp.message(F.text == "📥 Pul qo'shish")
async def ask_add(message: Message, state: FSMContext):
    await state.set_state(FinanceStates.waiting_for_add)
    await message.answer("Kirim qilish uchun quyidagi formatda yozing:\n\n`Ism Summa` (Masalan: `Ali 50000`)", parse_mode="Markdown")

@dp.message(F.text == "📤 Pul ishlatish")
async def ask_spend(message: Message, state: FSMContext):
    await state.set_state(FinanceStates.waiting_for_spend)
    await message.answer("Chiqim qilish uchun quyidagi formatda yozing:\n\n`Ism Summa` (Masalan: `Vali 20000`)", parse_mode="Markdown")

@dp.message(F.text == "🎯 Maqsad qo'yish")
async def ask_goal(message: Message, state: FSMContext):
    await state.set_state(FinanceStates.waiting_for_goal)
    await message.answer("Yangi maqsad summasini kiriting (faqat raqam):\n\nMasalan: `1000000`", parse_mode="Markdown")


# --- FSM QABUL QILISH QISMI ---

@dp.message(FinanceStates.waiting_for_add)
async def process_add_state(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) >= 2 and parts[-1].isdigit():
        name = " ".join(parts[:-1]).capitalize()
        amount = float(parts[-1])
        cursor.execute("INSERT INTO transactions (name, type, amount) VALUES (?, 'in', ?)", (name, amount))
        conn.commit()
        await state.clear()
        await message.answer(f"✅ **{name}** dan {amount:,.0f} so'm qabul qilindi!", parse_mode="Markdown", reply_markup=get_reply_keyboard())
    else:
        await message.answer("❌ Noto'g'ri format! Qaytadan kiriting (Masalan: `Ali 50000`):")

@dp.message(FinanceStates.waiting_for_spend)
async def process_spend_state(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) >= 2 and parts[-1].isdigit():
        name = " ".join(parts[:-1]).capitalize()
        amount = float(parts[-1])
        cursor.execute("INSERT INTO transactions (name, type, amount) VALUES (?, 'out', ?)", (name, amount))
        conn.commit()
        await state.clear()
        await message.answer(f"💸 **{name}** tomonidan {amount:,.0f} so'm ishlatildi!", parse_mode="Markdown", reply_markup=get_reply_keyboard())
    else:
        await message.answer("❌ Noto'g'ri format! Qaytadan kiriting (Masalan: `Vali 20000`):")

@dp.message(FinanceStates.waiting_for_goal)
async def process_goal_state(message: Message, state: FSMContext):
    if message.text.isdigit():
        amount = float(message.text)
        cursor.execute("INSERT INTO goal (target_amount) VALUES (?)", (amount,))
        conn.commit()
        await state.clear()
        await message.answer(f"🎯 Yangi maqsad muvaffaqiyatli belgilandi: **{amount:,.0f} so'm**", parse_mode="Markdown", reply_markup=get_reply_keyboard())
    else:
        await message.answer("❌ Faqat raqam kiriting! Masalan: `1000000`")


# --- MATNNI TO'G'RIDAN-TO'G'RI TAHLIL QILISH (REGEX) ---
@dp.message(F.text)
async def process_text_message(message: Message):
    text = message.text.strip()

    # 1. Maqsad o'rnatish: "Maqsad 500000" (re.IGNORECASE to'g'rilangan holatda)
    match_goal = re.match(r'^maqsad\s+(\d+)$', text, re.IGNORECASE)
    if match_goal:
        amount = float(match_goal.group(1))
        cursor.execute("INSERT INTO goal (target_amount) VALUES (?)", (amount,))
        conn.commit()
        await message.answer(f"🎯 Yangi maqsad belgilandi: **{amount:,.0f} so'm**", parse_mode="Markdown")
        return

    # 2. Ishlatilgan pul: "Ali -20000"
    match_spend = re.match(r'^([a-zA-UzʻoʻGʻgʻА-яЎўҚқҒғ]+)\s+-(\d+)$', text)
    if match_spend:
        name = match_spend.group(1).capitalize()
        amount = float(match_spend.group(2))
        cursor.execute("INSERT INTO transactions (name, type, amount) VALUES (?, 'out', ?)", (name, amount))
        conn.commit()
        await message.answer(f"💸 **{name}** {amount:,.0f} so'm ishlatdi!", parse_mode="Markdown")
        return

    # 3. Yig'ilgan pul (qo'shildi): "Ali 50000" yoki "Ali +50000"
    match_add = re.match(r'^([a-zA-UzʻoʻGʻgʻА-яЎўҚқҒғ]+)\s+\+?(\d+)$', text)
    if match_add:
        name = match_add.group(1).capitalize()
        amount = float(match_add.group(2))
        cursor.execute("INSERT INTO transactions (name, type, amount) VALUES (?, 'in', ?)", (name, amount))
        conn.commit()
        await message.answer(f"✅ **{name}** {amount:,.0f} so'm qo'shdi!", parse_mode="Markdown")
        return


if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))