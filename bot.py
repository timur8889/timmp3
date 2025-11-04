import sqlite3
import pandas as pd
import gspread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройки
DB_PATH = 'construction.db'
GC_CREDENTIALS = 'credentials.json'  # Файл с ключами от Google API
GSHEET_NAME = 'Construction Tracker'

# Подключение к Google Sheets
gc = gspread.service_account(filename=GC_CREDENTIALS)
sh = gc.open(GSHEET_NAME)

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS projects
                   (id INTEGER PRIMARY KEY, name TEXT)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS materials
                   (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT,
                    quantity REAL, unit_price REAL)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS salaries
                   (id INTEGER PRIMARY KEY, project_id INTEGER,
                    description TEXT, amount REAL)''')
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Добавить объект", callback_data='add_project')],
        [InlineKeyboardButton("Добавить материал", callback_data='add_material')],
        [InlineKeyboardButton("Добавить зарплату", callback_data='add_salary')],
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Экспорт в Excel", callback_data='export_excel')],
        [InlineKeyboardButton("Синхронизировать с Google Sheets", callback_data='sync_gs')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите действие:', reply_markup=reply_markup)

# Обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_project':
        await query.message.reply_text('Введите название объекта:')
        context.user_data['awaiting'] = 'project_name'
    
    elif query.data == 'add_material':
        await show_projects(query.message, context, 'material')
    
    elif query.data == 'add_salary':
        await show_projects(query.message, context, 'salary')
    
    elif query.data == 'stats':
        await show_stats(query.message)
    
    elif query.data == 'export_excel':
        await export_to_excel(query.message)
    
    elif query.data == 'sync_gs':
        await sync_to_gsheets(query.message)

# Показать список проектов
async def show_projects(message, context, action):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    keyboard = [[InlineKeyboardButton(p[1], callback_data=f'{action}_{p[0]}')] for p in projects]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text('Выберите проект:', reply_markup=reply_markup)

# Добавление проекта
async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO projects (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f'Объект "{name}" добавлен!')

# Добавление материала
async def handle_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    project_id = context.user_data['selected_project']
    text = update.message.text
    name, quantity, price = text.split(';')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO materials (project_id, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
                 (project_id, name, float(quantity), float(price)))
    conn.commit()
    conn.close()
    await update.message.reply_text('Материал добавлен!')

# Добавление зарплаты
async def handle_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    project_id = context.user_data['selected_project']
    text = update.message.text
    desc, amount = text.split(';')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO salaries (project_id, description, amount) VALUES (?, ?, ?)",
                 (project_id, desc, float(amount)))
    conn.commit()
    conn.close()
    await update.message.reply_text('Зарплата добавлена!')

# Статистика
async def show_stats(message):
    conn = sqlite3.connect(DB_PATH)
    
    # Общая статистика
    total_materials = conn.execute("SELECT SUM(quantity * unit_price) FROM materials").fetchone()[0] or 0
    total_salaries = conn.execute("SELECT SUM(amount) FROM salaries").fetchone()[0] or 0
    total = total_materials + total_salaries
    
    stats_text = f"""Общая статистика:
    Материалы: {total_materials:.2f} руб.
    Зарплаты: {total_salaries:.2f} руб.
    Итого: {total:.2f} руб."""
    
    # Статистика по проектам
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    for project in projects:
        proj_materials = conn.execute("SELECT SUM(quantity * unit_price) FROM materials WHERE project_id = ?", 
                                      (project[0],)).fetchone()[0] or 0
        proj_salaries = conn.execute("SELECT SUM(amount) FROM salaries WHERE project_id = ?", 
                                     (project[0],)).fetchone()[0] or 0
        stats_text += f"\n\n{project[1]}:\n  Материалы: {proj_materials:.2f}\n  Зарплаты: {proj_salaries:.2f}"
    
    conn.close()
    await message.reply_text(stats_text)

# Экспорт в Excel
async def export_to_excel(message):
    conn = sqlite3.connect(DB_PATH)
    
    with pd.ExcelWriter('construction_data.xlsx') as writer:
        # Проекты
        pd.read_sql("SELECT * FROM projects", conn).to_excel(writer, sheet_name='Projects', index=False)
        # Материалы
        pd.read_sql("SELECT * FROM materials", conn).to_excel(writer, sheet_name='Materials', index=False)
        # Зарплаты
        pd.read_sql("SELECT * FROM salaries", conn).to_excel(writer, sheet_name='Salaries', index=False)
    
    conn.close()
    
    await message.reply_document(document=open('construction_data.xlsx', 'rb'))

# Синхронизация с Google Sheets
async def sync_to_gsheets(message):
    conn = sqlite3.connect(DB_PATH)
    
    # Обновляем листы
    def update_sheet(worksheet_name, query):
        worksheet = sh.worksheet(worksheet_name)
        data = conn.execute(query).fetchall()
        headers = [desc[0] for desc in conn.execute(query).description]
        worksheet.clear()
        worksheet.update([headers] + data)
    
    update_sheet('Projects', "SELECT * FROM projects")
    update_sheet('Materials', "SELECT * FROM materials")
    update_sheet('Salaries', "SELECT * FROM salaries")
    
    conn.close()
    await message.reply_text('Данные синхронизированы с Google Sheets!')

# Основная функция
def main():
    init_db()
    
    application = Application.builder().token("YOUR_BOT_TOKEN").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                         lambda update, context: handle_text(update, context)))
    
    application.run_polling()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('awaiting')
    
    if state == 'project_name':
        await handle_project_name(update, context)
    elif state == 'material':
        await handle_material(update, context)
    elif state == 'salary':
        await handle_salary(update, context)
    
    context.user_data['awaiting'] = None

if __name__ == '__main__':
    main()
