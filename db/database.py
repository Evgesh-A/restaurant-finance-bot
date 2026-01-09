# db/database.py
import sqlite3
import os
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font

DB_PATH = "finance.db"


def init_db():
    """Создаёт таблицы, если их нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER UNIQUE,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            category TEXT,
            description TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def add_user(tg_user_id: int):
    """Добавляет пользователя, если его нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (tg_user_id, created_at) VALUES (?, ?)",
                   (tg_user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_user_id(tg_user_id: int) -> int:
    """Возвращает внутренний ID пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_user_id = ?", (tg_user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def add_transaction(tg_user_id: int, trans_type: str, amount: float, category: str, description: str = ""):
    """Добавляет операцию (доход/расход)"""
    user_id = get_user_id(tg_user_id)
    if user_id is None:
        add_user(tg_user_id)
        user_id = get_user_id(tg_user_id)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (user_id, type, amount, category, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, trans_type, amount, category, description, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_daily_summary(user_id: int):
    """Возвращает доход, расход и прибыль за сегодня"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().date().isoformat()
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE user_id = ? AND DATE(created_at) = ?
    """, (user_id, today))
    row = cursor.fetchone()
    conn.close()
    income = row[0] or 0
    expense = row[1] or 0
    return income, expense, income - expense


def get_weekly_summary(user_id: int):
    """Возвращает итоги за последние 7 дней"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    week_ago = (datetime.now().date() - timedelta(days=7)).isoformat()
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE user_id = ? AND DATE(created_at) >= ?
    """, (user_id, week_ago))
    row = cursor.fetchone()
    conn.close()
    income = row[0] or 0
    expense = row[1] or 0
    return income, expense, income - expense


def get_monthly_summary(user_id: int):
    """Возвращает итоги за текущий месяц"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE user_id = ? AND created_at >= ?
    """, (user_id, month_start))
    row = cursor.fetchone()
    conn.close()
    income = row[0] or 0
    expense = row[1] or 0
    return income, expense, income - expense


def get_expense_categories_summary(user_id: int):
    """Возвращает расходы по категориям за всё время"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows  # список кортежей: [('продукты', 12000.0), ...]


def generate_excel_report(user_id: int, filename: str):
    """Генерирует Excel-файл с отчётом для пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Лист 1: Все операции
    cursor.execute("""
        SELECT created_at, type, category, amount, description
        FROM transactions
        WHERE user_id = ?
        ORDER BY created_at
    """, (user_id,))
    operations = cursor.fetchall()
    
    # Лист 2: Сводка по категориям
    cursor.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,))
    category_summary = cursor.fetchall()
    
    # Итоги за месяц — используем ту же логику, что и в get_monthly_summary
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE user_id = ? AND created_at >= ?
    """, (user_id, month_start))
    monthly = cursor.fetchone()
    monthly_income = monthly[0] or 0
    monthly_expense = monthly[1] or 0
    monthly_profit = monthly_income - monthly_expense
    
    conn.close()
    
    # Создаём Excel
    wb = Workbook()
    
    # Лист 1: Операции
    ws1 = wb.active
    ws1.title = "Операции"
    ws1.append(["Дата и время", "Тип", "Категория", "Сумма", "Комментарий"])
    for row in operations:
        dt = row[0].split(".")[0] if "." in row[0] else row[0]
        ws1.append([dt, row[1], row[2], row[3], row[4]])
    
    # Лист 2: Сводка
    ws2 = wb.create_sheet(title="Сводка")
    ws2.append(["Категория расходов", "Сумма (₽)"])
    for cat, total in category_summary:
        ws2.append([cat, total])
    
    ws2.append([])  # пустая строка
    ws2.append(["Итого за месяц", ""])
    ws2.append(["Доход", monthly_income])
    ws2.append(["Расход", monthly_expense])
    ws2.append(["Прибыль", monthly_profit])
    
    # Жирный шрифт для заголовков
    for ws in [ws1, ws2]:
        for cell in ws[1]:
            cell.font = Font(bold=True)
    

    wb.save(filename)
