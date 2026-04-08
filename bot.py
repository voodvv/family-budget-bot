import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

# ──────────────────────────────────────────────
# НАЛАШТУВАННЯ — замінити свої значення
# ──────────────────────────────────────────────

BOT_TOKEN = os.environ.get("8253838404:AAFQK6X1PX2o-5w0GHm73FBWmxtAmIooEoU", "8253838404:AAFQK6X1PX2o-5w0GHm73FBWmxtAmIooEoU")

SPREADSHEET_ID = "1-LeXy4MAF35ntYfB94tVKVsU68dEl1hy50O-ynbx7jE"  # вже вставлено з твого посилання

# Члени сім'ї: Telegram ID → ім'я
FAMILY_MEMBERS = {
    357557645: "Вадим",
    # 123456789: "Марія",   ← розкоментуй і встав ID Марії коли буде
}

# ──────────────────────────────────────────────
# КАТЕГОРІЇ
# ──────────────────────────────────────────────

CATEGORIES = {
    "🍕 Їжа": ["Супермаркет", "Ресторан", "Доставка", "Ринок"],
    "🚗 Авто": ["Бензин", "Паркінг", "Ремонт", "Мийка"],
    "🏠 Комунальні": ["Світло", "Вода", "Газ", "Інтернет", "Інше"],
    "👗 Одяг": ["Одяг", "Взуття", "Аксесуари"],
    "💊 Здоров'я": ["Аптека", "Лікар", "Спорт"],
    "🎉 Розваги": ["Кіно", "Подорожі", "Кафе", "Інше"],
    "📦 Інше": ["Інше"],
}

# ──────────────────────────────────────────────
# GOOGLE SHEETS
# ──────────────────────────────────────────────

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    return sheet

def init_sheet():
    sheet = get_sheet()
    if sheet.row_count == 0 or sheet.cell(1, 1).value != "Дата":
        sheet.insert_row(
            ["Дата", "Час", "Хто", "Категорія", "Підкатегорія", "Сума (грн)", "Коментар"],
            index=1
        )

def save_expense(name, category, subcategory, amount, comment=""):
    sheet = get_sheet()
    now = datetime.now()
    sheet.append_row([
        now.strftime("%d.%m.%Y"),
        now.strftime("%H:%M"),
        name,
        category,
        subcategory,
        amount,
        comment,
    ])

def get_monthly_report():
    sheet = get_sheet()
    records = sheet.get_all_records()
    current_month = datetime.now().strftime("%m.%Y")

    totals = {}
    by_person = {}

    for row in records:
        date_str = row.get("Дата", "")
        if not date_str or date_str[3:] != current_month:
            continue
        cat = row.get("Категорія", "Інше")
        person = row.get("Хто", "?")
        try:
            amount = float(str(row.get("Сума (грн)", 0)).replace(",", "."))
        except:
            continue
        totals[cat] = totals.get(cat, 0) + amount
        by_person[person] = by_person.get(person, 0) + amount

    return totals, by_person

# ──────────────────────────────────────────────
# FSM СТАНИ
# ──────────────────────────────────────────────

class ExpenseState(StatesGroup):
    waiting_amount = State()
    waiting_category = State()
    waiting_subcategory = State()
    waiting_comment = State()

# ──────────────────────────────────────────────
# БОТ
# ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def get_user_name(user_id: int) -> str:
    return FAMILY_MEMBERS.get(user_id, f"Користувач {user_id}")

def is_allowed(user_id: int) -> bool:
    return user_id in FAMILY_MEMBERS

# ── /start ──

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("❌ У тебе немає доступу до цього бота.")
        return
    name = get_user_name(message.from_user.id)
    await message.answer(
        f"👋 Привіт, {name}!\n\n"
        f"Команди:\n"
        f"💸 /add — додати витрату\n"
        f"📊 /report — звіт за місяць\n"
        f"❓ /help — допомога"
    )

# ── /add ──

@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        await message.answer("❌ У тебе немає доступу.")
        return
    await state.set_state(ExpenseState.waiting_amount)
    await message.answer("💰 Введи суму витрати (наприклад: 150):")

@dp.message(ExpenseState.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи коректну суму, наприклад: 150 або 49.99")
        return

    await state.update_data(amount=amount)
    await state.set_state(ExpenseState.waiting_category)

    builder = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        builder.button(text=cat, callback_data=f"cat:{cat}")
    builder.adjust(2)
    await message.answer("📂 Оберіть категорію:", reply_markup=builder.as_markup())

@dp.callback_query(ExpenseState.waiting_category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("cat:", 1)[1]
    await state.update_data(category=category)
    await state.set_state(ExpenseState.waiting_subcategory)

    subcats = CATEGORIES.get(category, ["Інше"])
    builder = InlineKeyboardBuilder()
    for sub in subcats:
        builder.button(text=sub, callback_data=f"sub:{sub}")
    builder.adjust(2)
    await callback.message.edit_text(f"📁 Категорія: {category}\n\nОберіть підкатегорію:", reply_markup=builder.as_markup())

@dp.callback_query(ExpenseState.waiting_subcategory, F.data.startswith("sub:"))
async def process_subcategory(callback: CallbackQuery, state: FSMContext):
    subcategory = callback.data.split("sub:", 1)[1]
    await state.update_data(subcategory=subcategory)
    await state.set_state(ExpenseState.waiting_comment)
    await callback.message.edit_text(
        f"✅ Підкатегорія: {subcategory}\n\n"
        f"💬 Додай коментар (необов'язково).\nАбо напиши «-» щоб пропустити:"
    )

@dp.message(ExpenseState.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    comment = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    name = get_user_name(message.from_user.id)

    try:
        save_expense(name, data["category"], data["subcategory"], data["amount"], comment)
        await message.answer(
            f"✅ Записано!\n\n"
            f"👤 {name}\n"
            f"📂 {data['category']} → {data['subcategory']}\n"
            f"💰 {data['amount']} грн\n"
            f"💬 {comment if comment else '—'}"
        )
    except Exception as e:
        await message.answer(f"❌ Помилка запису: {e}")

    await state.clear()

# ── /report ──

@dp.message(Command("report"))
async def cmd_report(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("❌ У тебе немає доступу.")
        return

    await message.answer("⏳ Формую звіт...")

    try:
        totals, by_person = get_monthly_report()
        month = datetime.now().strftime("%B %Y")

        if not totals:
            await message.answer(f"📊 За {month} витрат ще немає.")
            return

        lines = [f"📊 *Звіт за {month}*\n"]

        lines.append("*По категоріях:*")
        for cat, amount in sorted(totals.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {amount:.0f} грн")

        total_all = sum(totals.values())
        lines.append(f"\n💰 *Разом: {total_all:.0f} грн*\n")

        lines.append("*По членах сім'ї:*")
        for person, amount in sorted(by_person.items(), key=lambda x: -x[1]):
            lines.append(f"  👤 {person}: {amount:.0f} грн")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")

# ── /help ──

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ *Сімейний бюджет бот*\n\n"
        "💸 /add — додати витрату\n"
        "📊 /report — звіт за поточний місяць\n\n"
        "Всі витрати зберігаються в Google Sheets.",
        parse_mode="Markdown"
    )

# ──────────────────────────────────────────────
# ЗАПУСК
# ──────────────────────────────────────────────

async def main():
    try:
        init_sheet()
        logging.info("Google Sheets підключено ✅")
    except Exception as e:
        logging.warning(f"Sheets не підключено: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
