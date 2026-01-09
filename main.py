# main.py
import re
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from db.database import init_db, add_transaction

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ Переменная окружения BOT_TOKEN не задана!")

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class FinanceStates(StatesGroup):
    waiting_for_income_amount = State()
    waiting_for_expense_amount = State()
    waiting_for_expense_category = State()

EXPENSE_CATEGORIES = ["продукты", "персонал", "аренда", "коммуналка", "реклама", "прочее"]

def main_menu():
    buttons = [
        [KeyboardButton(text="➕ Добавить доход")],
        [KeyboardButton(text="➖ Добавить расход")],
        [KeyboardButton(text="📊 Отчёты")],
        [KeyboardButton(text="📥 Выгрузить Excel")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def parse_amount(text: str) -> float:
    """Преобразует строку в число: удаляет всё лишнее, оставляет только цифры и одну точку"""
    if not text:
        raise ValueError("Пусто")
    cleaned = re.sub(r'[^\d.,]', '', text)
    if not cleaned:
        raise ValueError("Нет цифр")
    cleaned = cleaned.replace(',', '.', 1)
    parts = cleaned.split('.')
    if len(parts) > 2:
        cleaned = parts[0] + '.' + ''.join(parts[1:])
    return float(cleaned)

# === ОСНОВНЫЕ ОБРАБОТЧИКИ ===

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Привет! Я бот для учёта финансов ресторана.", reply_markup=main_menu())

@dp.message(lambda message: message.text == "➕ Добавить доход")
async def add_income_start(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму дохода (только цифры, например: 15000.50):")
    await state.set_state(FinanceStates.waiting_for_income_amount)

@dp.message(FinanceStates.waiting_for_income_amount)
async def add_income_amount(message: types.Message, state: FSMContext):
    try:
        amount = parse_amount(message.text)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
        add_transaction(message.from_user.id, "income", amount, "доход")
        await message.answer(f"✅ Доход {amount:.2f} ₽ добавлен!", reply_markup=main_menu())
        await state.clear()
    except Exception as e:
        logging.error(f"Ошибка парсинга дохода: {e}")
        await message.answer("❌ Неверный формат. Введите число, например: 25000")

@dp.message(lambda message: message.text == "➖ Добавить расход")
async def add_expense_start(message: types.Message, state: FSMContext):
    buttons = [[KeyboardButton(text=cat)] for cat in EXPENSE_CATEGORIES]
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("Выберите категорию расхода:", reply_markup=kb)
    await state.set_state(FinanceStates.waiting_for_expense_category)

@dp.message(FinanceStates.waiting_for_expense_category)
async def add_expense_category(message: types.Message, state: FSMContext):
    if message.text not in EXPENSE_CATEGORIES:
        await message.answer("Выберите категорию из списка:")
        return
    await state.update_data(category=message.text)
    await message.answer("Введите сумму расхода:")
    await state.set_state(FinanceStates.waiting_for_expense_amount)

@dp.message(FinanceStates.waiting_for_expense_amount)
async def add_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = parse_amount(message.text)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
        data = await state.get_data()
        category = data["category"]
        add_transaction(message.from_user.id, "expense", amount, category)
        await message.answer(f"✅ Расход {amount:.2f} ₽ в категории '{category}' добавлен!", reply_markup=main_menu())
        await state.clear()
    except Exception as e:
        logging.error(f"Ошибка парсинга расхода: {e}")
        await message.answer("❌ Неверный формат. Введите число, например: 8500")

# === ОТЧЁТЫ И EXCEL ===

@dp.message(lambda message: message.text == "📊 Отчёты")
async def show_reports(message: types.Message):
    try:
        from db.database import (
            get_user_id,
            get_daily_summary,
            get_weekly_summary,
            get_monthly_summary,
            get_expense_categories_summary
        )
        
        tg_user_id = message.from_user.id
        user_id = get_user_id(tg_user_id)
        
        if user_id is None:
            await message.answer("📭 Нет данных. Добавьте доход или расход.")
            return
        
        d_inc, d_exp, d_prof = get_daily_summary(user_id)
        w_inc, w_exp, w_prof = get_weekly_summary(user_id)
        m_inc, m_exp, m_prof = get_monthly_summary(user_id)
        cat_expenses = get_expense_categories_summary(user_id)
        
        if d_inc == 0 and d_exp == 0 and w_inc == 0 and w_exp == 0:
            await message.answer("📭 Нет данных для отчёта. Добавьте доход или расход.")
            return
        
        text = "📊 Ваши финансовые отчёты\n\n"
        text += f"🔹 Сегодня\nДоход: {d_inc:.2f} ₽\nРасход: {d_exp:.2f} ₽\nПрибыль: {d_prof:.2f} ₽\n\n"
        text += f"🔹 Последние 7 дней\nДоход: {w_inc:.2f} ₽\nРасход: {w_exp:.2f} ₽\nПрибыль: {w_prof:.2f} ₽\n\n"
        text += f"🔹 Текущий месяц\nДоход: {m_inc:.2f} ₽\nРасход: {m_exp:.2f} ₽\nПрибыль: {m_prof:.2f} ₽\n\n"
        
        if cat_expenses:
            text += "🔹 Расходы по категориям\n"
            for cat, total in cat_expenses:
                text += f"• {cat}: {total:.2f} ₽\n"
        
        await message.answer(text, reply_markup=main_menu())
        
    except Exception as e:
        logging.error(f"Ошибка отчёта: {e}")
        await message.answer("❌ Не удалось сформировать отчёт. Попробуйте позже.")

@dp.message(lambda message: message.text == "📥 Выгрузить Excel")
async def export_to_excel(message: types.Message):
    try:
        from db.database import get_user_id, generate_excel_report
        
        tg_user_id = message.from_user.id
        user_id = get_user_id(tg_user_id)
        
        if user_id is None:
            await message.answer("📭 Нет данных для выгрузки.")
            return
        
        filename = f"report_{tg_user_id}.xlsx"
        generate_excel_report(user_id, filename)
        
        # Отправляем файл
        await message.answer_document(FSInputFile(filename))
        
        # Удаляем файл (закомментируй, если хочешь оставить на сервере)
        os.remove(filename)
        
    except Exception as e:
        logging.error(f"Excel ошибка: {e}")
        await message.answer("❌ Не удалось создать Excel-файл.")

# === УНИВЕРСАЛЬНЫЙ ЛОГГЕР — В САМОМ КОНЦЕ ===
@dp.message()
async def log_all_messages(message: types.Message):
    logging.info(f"Получено сообщение от {message.from_user.id}: {message.text}")

# === ЗАПУСК ===
async def main():
    init_db()
    logging.info("✅ Бот запущен и ожидает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())