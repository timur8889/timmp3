import sqlite3
import pandas as pd
import gspread
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv
import re
from datetime import datetime

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_PATH = 'construction.db'
GC_CREDENTIALS = 'credentials.json'
GSHEET_NAME = 'Construction Tracker'

# Проверка наличия токена
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация БД с новыми полями
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS projects
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT UNIQUE,
                    address TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS materials
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    project_id INTEGER,
                    name TEXT,
                    quantity REAL,
                    unit TEXT,
                    unit_price REAL,
                    total_price REAL,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id))''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS salaries
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    project_id INTEGER,
                    work_type TEXT,
                    description TEXT,
                    amount REAL,
                    work_date DATE,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id))''')
    conn.commit()
    conn.close()

# Клавиатуры
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏗️ Добавить объект", callback_data='add_project')],
        [InlineKeyboardButton("📦 Управление материалами", callback_data='materials_menu')],
        [InlineKeyboardButton("💰 Управление зарплатами", callback_data='salaries_menu')],
        [InlineKeyboardButton("📊 Статистика и отчеты", callback_data='reports_menu')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def materials_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 Добавить материал", callback_data='add_material')],
        [InlineKeyboardButton("📋 Список материалов", callback_data='list_materials')],
        [InlineKeyboardButton("🔍 Поиск материалов", callback_data='search_materials')],
        [InlineKeyboardButton("✏️ Редактировать материал", callback_data='edit_material')],
        [InlineKeyboardButton("🗑️ Удалить материал", callback_data='delete_material')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def salaries_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💵 Добавить зарплату", callback_data='add_salary')],
        [InlineKeyboardButton("📋 Список зарплат", callback_data='list_salaries')],
        [InlineKeyboardButton("🔍 Поиск по зарплатам", callback_data='search_salaries')],
        [InlineKeyboardButton("✏️ Редактировать зарплату", callback_data='edit_salary')],
        [InlineKeyboardButton("🗑️ Удалить зарплату", callback_data='delete_salary')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def reports_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📈 Общая статистика", callback_data='overall_stats')],
        [InlineKeyboardButton("🏗️ Статистика по объекту", callback_data='project_stats')],
        [InlineKeyboardButton("📊 Детальный отчет", callback_data='detailed_report')],
        [InlineKeyboardButton("📤 Экспорт в Excel", callback_data='export_excel')],
        [InlineKeyboardButton("☁️ Синхронизация с Google Sheets", callback_data='sync_gs')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать объект", callback_data='edit_project')],
        [InlineKeyboardButton("🗑️ Удалить объект", callback_data='delete_project')],
        [InlineKeyboardButton("🔄 Очистить все данные", callback_data='clear_data')],
        [InlineKeyboardButton("📋 Список объектов", callback_data='list_projects')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def projects_keyboard(action):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects ORDER BY created_date DESC").fetchall()
    conn.close()
    
    keyboard = []
    for project in projects:
        keyboard.append([InlineKeyboardButton(f"🏗️ {project[1]}", callback_data=f'{action}_project_{project[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data=f'back_to_{action}_menu')])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

def confirmation_keyboard(action, item_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f'confirm_{action}_{item_id}')],
        [InlineKeyboardButton("❌ Отмена", callback_data=f'cancel_{action}')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button(target_menu):
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data=target_menu)]]
    return InlineKeyboardMarkup(keyboard)

def unit_selection_keyboard():
    keyboard = [
        [InlineKeyboardButton("шт", callback_data='unit_sh')],
        [InlineKeyboardButton("кг", callback_data='unit_kg')],
        [InlineKeyboardButton("т", callback_data='unit_t')],
        [InlineKeyboardButton("м³", callback_data='unit_m3')],
        [InlineKeyboardButton("м²", callback_data='unit_m2')],
        [InlineKeyboardButton("м", callback_data='unit_m')],
        [InlineKeyboardButton("л", callback_data='unit_l')],
        [InlineKeyboardButton("упак", callback_data='unit_pack')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_add_material')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    welcome_text = f"""
🏢 *ООО «ИСК ГЕОСТРОЙ»*
*СИСТЕМА УЧЕТА СТРОИТЕЛЬНЫХ ПРОЕКТОВ*

👤 Добро пожаловать, {user.first_name}!
📅 {current_date}

*КОРПОРАТИВНЫЙ ФУНКЦИОНАЛ:*

• 🏗️ **УЧЕТ ОБЪЕКТОВ** - Ведение реестра строительных проектов
• 📦 **МАТЕРИАЛЬНЫЕ РЕСУРСЫ** - Контроль закупок и расходов
• 💰 **ФОНД ОПЛАТЫ ТРУДА** - Учет заработной платы сотрудников
• 📊 **АНАЛИТИКА И ОТЧЕТНОСТЬ** - Финансовый мониторинг проектов
• 📈 **ПЛАНИРОВАНИЕ** - Оптимизация затрат и ресурсов

*ВЫБЕРИТЕ РАЗДЕЛ ДЛЯ РАБОТЫ:*
    """
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

# Меню
async def show_main_menu(query):
    current_date = datetime.now().strftime("%d.%m.%Y")
    await query.edit_message_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n"
        f"📅 {current_date}\n\n"
        "*ГЛАВНОЕ МЕНЮ СИСТЕМЫ*\n"
        "Выберите раздел для работы:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def show_materials_menu(query):
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📦 *УПРАВЛЕНИЕ МАТЕРИАЛЬНЫМИ РЕСУРСАМИ*\n\n"
        "Выберите операцию:",
        parse_mode='Markdown',
        reply_markup=materials_menu_keyboard()
    )

async def show_salaries_menu(query):
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "💰 *УПРАВЛЕНИЕ ФОНДОМ ОПЛАТЫ ТРУДА*\n\n"
        "Выберите операцию:",
        parse_mode='Markdown',
        reply_markup=salaries_menu_keyboard()
    )

async def show_reports_menu(query):
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📊 *АНАЛИТИКА И ОТЧЕТНОСТЬ*\n\n"
        "Выберите тип отчета:",
        parse_mode='Markdown',
        reply_markup=reports_menu_keyboard()
    )

async def show_settings_menu(query):
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "⚙️ *АДМИНИСТРИРОВАНИЕ СИСТЕМЫ*\n\n"
        "Выберите операцию:",
        parse_mode='Markdown',
        reply_markup=settings_menu_keyboard()
    )

# Обработчики проектов - УПРОЩЕННАЯ ВЕРСИЯ
async def add_project_handler(query, context):
    context.user_data['awaiting_input'] = 'project_name'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🏗️ *РЕГИСТРАЦИЯ НОВОГО ОБЪЕКТА*\n\n"
        "📝 Введите *наименование* строительного объекта:\n\n"
        "*ПРИМЕР:* `Жилой дом по ул. Ленина, 25`",
        parse_mode='Markdown',
        reply_markup=back_button('main_menu')
    )

async def edit_project_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ В системе нет объектов для редактирования!",
            reply_markup=back_button('settings_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "✏️ *РЕДАКТИРОВАНИЕ ОБЪЕКТА*\n\n"
        "Выберите объект для редактирования:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('edit')
    )

async def delete_project_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ В системе нет объектов для удаления!",
            reply_markup=back_button('settings_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🗑️ *УДАЛЕНИЕ ОБЪЕКТА*\n\n"
        "Выберите объект для удаления:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('delete')
    )

async def list_projects_handler(query):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("""
        SELECT p.id, p.name, p.address, p.created_date,
               COALESCE(SUM(m.total_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        GROUP BY p.id
        ORDER BY p.created_date DESC
    """).fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            "📋 *РЕЕСТР СТРОИТЕЛЬНЫХ ОБЪЕКТОВ*\n\n"
            "На текущий момент объекты не зарегистрированы.",
            parse_mode='Markdown',
            reply_markup=back_button('settings_menu')
        )
        return
    
    projects_text = "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n📋 *РЕЕСТР СТРОИТЕЛЬНЫХ ОБЪЕКТОВ*\n\n"
    for i, project in enumerate(projects, 1):
        total_cost = project[4] + project[5]
        projects_text += f"*{i}. {project[1]}*\n"
        projects_text += f"   📍 Адрес: {project[2] or 'Не указан'}\n"
        projects_text += f"   📅 Дата регистрации: {project[3][:10]}\n"
        projects_text += f"   💰 Общая стоимость: {total_cost:,.2f} руб.\n"
        projects_text += f"   📦 Материалы: {project[4]:,.2f} руб.\n"
        projects_text += f"   👷 ФОТ: {project[5]:,.2f} руб.\n\n"
    
    await query.edit_message_text(
        projects_text,
        parse_mode='Markdown',
        reply_markup=back_button('settings_menu')
    )

# Обработчики материалов
async def add_material_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Для внесения материалов необходимо сначала зарегистрировать строительный объект!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📦 *ПРИХОД МАТЕРИАЛОВ НА ОБЪЕКТ*\n\n"
        "Выберите объект строительства:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('material')
    )

async def edit_material_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.id, m.name, m.quantity, m.unit, m.total_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "❌ В системе нет материалов для редактирования!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    context.user_data['materials_list'] = materials
    keyboard = []
    for material in materials:
        keyboard.append([InlineKeyboardButton(
            f"{material[1]} - {material[5]}", 
            callback_data=f'edit_material_{material[0]}'
        )])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "✏️ *РЕДАКТИРОВАНИЕ МАТЕРИАЛА*\n\n"
        "Выберите материал для редактирования:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_material_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.id, m.name, m.quantity, m.unit, m.total_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "❌ В системе нет материалов для удаления!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    context.user_data['materials_list'] = materials
    keyboard = []
    for material in materials:
        keyboard.append([InlineKeyboardButton(
            f"{material[1]} - {material[5]}", 
            callback_data=f'delete_material_{material[0]}'
        )])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🗑️ *УДАЛЕНИЕ МАТЕРИАЛА*\n\n"
        "Выберите материал для удаления:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def list_materials_handler(query):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.name, m.quantity, m.unit, m.total_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            "📦 *ОПЕРАТИВНЫЙ ОТЧЕТ ПО МАТЕРИАЛАМ*\n\n"
            "За последний период приход материалов не зафиксирован.",
            parse_mode='Markdown',
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n📦 *ОПЕРАТИВНЫЙ ОТЧЕТ ПО МАТЕРИАЛАМ*\n\n"
    for i, material in enumerate(materials, 1):
        materials_text += f"*{i}. {material[0]}*\n"
        materials_text += f"   🏗️ Объект: {material[4]}\n"
        materials_text += f"   📊 Количество: {material[1]} {material[2]}\n"
        materials_text += f"   💰 Сумма: {material[3]:,.2f} руб.\n"
        materials_text += f"   📅 Дата оприходования: {material[5][:10]}\n\n"
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )

async def search_materials_handler(query, context):
    context.user_data['awaiting_input'] = 'search_materials'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🔍 *ПОИСК ПО МАТЕРИАЛЬНЫМ РЕСУРСАМ*\n\n"
        "Введите наименование материала для поиска:",
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )

# Обработчики зарплат
async def add_salary_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Для начисления заработной платы необходимо сначала зарегистрировать строительный объект!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "💰 *НАЧИСЛЕНИЕ ЗАРАБОТНОЙ ПЛАТЫ*\n\n"
        "Выберите объект строительства:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('salary')
    )

async def edit_salary_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.id, s.work_type, s.description, s.amount, p.name, s.work_date
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.work_date DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "❌ В системе нет зарплат для редактирования!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    context.user_data['salaries_list'] = salaries
    keyboard = []
    for salary in salaries:
        keyboard.append([InlineKeyboardButton(
            f"{salary[1]} - {salary[4]}", 
            callback_data=f'edit_salary_{salary[0]}'
        )])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "✏️ *РЕДАКТИРОВАНИЕ ЗАРПЛАТЫ*\n\n"
        "Выберите зарплату для редактирования:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_salary_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.id, s.work_type, s.description, s.amount, p.name, s.work_date
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.work_date DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "❌ В системе нет зарплат для удаления!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    context.user_data['salaries_list'] = salaries
    keyboard = []
    for salary in salaries:
        keyboard.append([InlineKeyboardButton(
            f"{salary[1]} - {salary[4]}", 
            callback_data=f'delete_salary_{salary[0]}'
        )])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🗑️ *УДАЛЕНИЕ ЗАРПЛАТЫ*\n\n"
        "Выберите зарплату для удаления:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def list_salaries_handler(query):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.work_type, s.description, s.amount, p.name, s.work_date
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.work_date DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            "💰 *ОТЧЕТ ПО ФОНДУ ОПЛАТЫ ТРУДА*\n\n"
            "За последний период начисления заработной платы не производились.",
            parse_mode='Markdown',
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n💰 *ОТЧЕТ ПО ФОНДУ ОПЛАТЫ ТРУДА*\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"*{i}. {salary[0]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[3]}\n"
        salaries_text += f"   📝 Описание: {salary[1]}\n"
        salaries_text += f"   💰 Сумма: {salary[2]:,.2f} руб.\n"
        salaries_text += f"   📅 Дата работ: {salary[4]}\n\n"
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

async def search_salaries_handler(query, context):
    context.user_data['awaiting_input'] = 'search_salaries'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🔍 *ПОИСК ПО НАЧИСЛЕНИЯМ ЗП*\n\n"
        "Введите описание работ для поиска:",
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

# Обработчики отчетов
async def overall_stats_handler(query):
    conn = sqlite3.connect(DB_PATH)
    
    # Общая статистика
    total_stats = conn.execute("""
        SELECT COUNT(*) as project_count,
               COALESCE(SUM(m.total_price), 0) as total_materials,
               COALESCE(SUM(s.amount), 0) as total_salaries
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
    """).fetchone()
    
    # Статистика по проектам
    projects_stats = conn.execute("""
        SELECT p.name, p.address,
               COALESCE(SUM(m.total_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        GROUP BY p.id
    """).fetchall()
    
    conn.close()
    
    total_cost = total_stats[1] + total_stats[2]
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    stats_text = f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n📅 {current_date}\n\n📈 *СВОДНЫЙ ФИНАНСОВЫЙ ОТЧЕТ*\n\n"
    stats_text += f"🏗️ Количество объектов: *{total_stats[0]}*\n"
    stats_text += f"📦 Затраты на материалы: *{total_stats[1]:,.2f} руб.*\n"
    stats_text += f"👷 Фонд оплаты труда: *{total_stats[2]:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    stats_text += "📊 *РАСПРЕДЕЛЕНИЕ ПО ОБЪЕКТАМ:*\n"
    for project in projects_stats:
        project_total = project[2] + project[3]
        stats_text += f"\n🏗️ *{project[0]}*\n"
        stats_text += f"   📍 Адрес: {project[1] or 'Не указан'}\n"
        stats_text += f"   📦 Материалы: {project[2]:,.2f} руб.\n"
        stats_text += f"   👷 ФОТ: {project[3]:,.2f} руб.\n"
        stats_text += f"   💰 Всего: {project_total:,.2f} руб.\n"
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=back_button('reports_menu')
    )

async def project_stats_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ В системе не зарегистрировано объектов для формирования статистики!",
            reply_markup=back_button('reports_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📊 *ФИНАНСОВАЯ СТАТИСТИКА ПО ОБЪЕКТУ*\n\n"
        "Выберите объект для анализа:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('stats')
    )

async def detailed_report_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ В системе не зарегистрировано объектов для формирования отчета!",
            reply_markup=back_button('reports_menu')
        )
        return
    
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📋 *ДЕТАЛИЗИРОВАННЫЙ ОТЧЕТ ПО ОБЪЕКТУ*\n\n"
        "Выберите объект для формирования отчета:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('report')
    )

async def export_excel_handler(query):
    try:
        conn = sqlite3.connect(DB_PATH)
        current_date = datetime.now().strftime("%d.%m.%Y")
        
        with pd.ExcelWriter('construction_report.xlsx', engine='openpyxl') as writer:
            # Проекты
            projects_df = pd.read_sql("SELECT name, address, created_date FROM projects", conn)
            projects_df.to_excel(writer, sheet_name='Объекты', index=False)
            
            # Материалы
            materials_df = pd.read_sql("""
                SELECT p.name as project_name, m.name, m.quantity, m.unit, m.unit_price, m.total_price, m.date_added
                FROM materials m
                JOIN projects p ON m.project_id = p.id
            """, conn)
            materials_df.to_excel(writer, sheet_name='Материалы', index=False)
            
            # Зарплаты
            salaries_df = pd.read_sql("""
                SELECT p.name as project_name, s.work_type, s.description, s.amount, s.work_date, s.date_added
                FROM salaries s
                JOIN projects p ON s.project_id = p.id
            """, conn)
            salaries_df.to_excel(writer, sheet_name='Зарплаты', index=False)
        
        conn.close()
        
        await query.message.reply_document(
            document=open('construction_report.xlsx', 'rb'),
            filename=f'Отчет_ООО_ИСК_ГЕОСТРОЙ_{current_date}.xlsx',
            caption="🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                   "📤 *ФИНАНСОВЫЙ ОТЧЕТ ЭКСПОРТИРОВАН*\n\n"
                   "Файл отчета готов к передаче в бухгалтерию и руководству.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            "✅ Отчет успешно сформирован и отправлен в чат!",
            reply_markup=back_button('reports_menu')
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.edit_message_text(
            "❌ Ошибка при формировании отчета! Обратитесь к системному администратору.",
            reply_markup=back_button('reports_menu')
        )

async def sync_gs_handler(query):
    try:
        gc = gspread.service_account(filename=GC_CREDENTIALS)
        sh = gc.open(GSHEET_NAME)
        
        conn = sqlite3.connect(DB_PATH)
        
        # Синхронизация проектов
        projects_ws = sh.worksheet('Projects')
        projects_data = conn.execute("SELECT name, address, created_date FROM projects").fetchall()
        projects_ws.clear()
        if projects_data:
            headers = ['Название', 'Адрес', 'Дата создания']
            projects_ws.update([headers] + projects_data)
        
        # Синхронизация материалов
        materials_ws = sh.worksheet('Materials')
        materials_data = conn.execute("""
            SELECT p.name as project_name, m.name, m.quantity, m.unit, m.unit_price, m.total_price, m.date_added
            FROM materials m 
            JOIN projects p ON m.project_id = p.id
        """).fetchall()
        materials_ws.clear()
        if materials_data:
            headers = ['Объект', 'Материал', 'Количество', 'Единица', 'Цена за ед.', 'Общая стоимость', 'Дата добавления']
            materials_ws.update([headers] + materials_data)
        
        conn.close()
        
        await query.edit_message_text(
            "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            "✅ *СИНХРОНИЗАЦИЯ С GOOGLE SHEETS ВЫПОЛНЕНА*\n\n"
            "Данные успешно обновлены в корпоративной системе учета.",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )
        
    except Exception as e:
        logger.error(f"GSync error: {e}")
        await query.edit_message_text(
            "❌ *ОШИБКА СИНХРОНИЗАЦИИ!*\n\n"
            "Проверьте настройки подключения к Google Sheets.",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )

# Обработчики настроек
async def clear_data_handler(query, context):
    keyboard = [
        [InlineKeyboardButton("🗑️ Подтвердить очистку", callback_data='confirm_clear_all')],
        [InlineKeyboardButton("❌ Отмена", callback_data='settings_menu')]
    ]
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "⚠️ *ОЧИСТКА БАЗЫ ДАННЫХ*\n\n"
        "ВНИМАНИЕ: Вы собираетесь удалить ВСЕ данные системы.\n"
        "Это действие необратимо и требует подтверждения руководства.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработка выбора проекта
async def handle_project_selection(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # material, salary, stats, report, edit, delete
    project_id = data_parts[2]
    
    conn = sqlite3.connect(DB_PATH)
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    context.user_data['selected_project'] = project_id
    context.user_data['selected_project_name'] = project[0]
    
    if action_type == 'material':
        context.user_data['awaiting_input'] = 'material_name'
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"📦 *ПРИХОД МАТЕРИАЛОВ*\nОбъект: *{project[0]}*\n\n"
            "📝 Введите *наименование* материала:\n\n"
            "*ПРИМЕР:* `Кирпич красный полнотелый М-150`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
    
    elif action_type == 'salary':
        context.user_data['awaiting_input'] = 'salary_work_type'
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"💰 *НАЧИСЛЕНИЕ ЗАРПЛАТЫ*\nОбъект: *{project[0]}*\n\n"
            "🔧 Введите *вид работ*:\n\n"
            "*ПРИМЕР:* `Кладка кирпича` или `Зарплата прораба`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    
    elif action_type == 'stats':
        await show_project_stats(query, project_id, project[0])
    
    elif action_type == 'report':
        await show_detailed_report(query, project_id, project[0])
    
    elif action_type == 'edit':
        context.user_data['awaiting_input'] = 'edit_project_name'
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✏️ *РЕДАКТИРОВАНИЕ ОБЪЕКТА*\n\n"
            f"Текущее название: *{project[0]}*\n\n"
            f"Введите новое название объекта:",
            parse_mode='Markdown',
            reply_markup=back_button('edit_project')
        )
    
    elif action_type == 'delete':
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"🗑️ *УДАЛЕНИЕ ОБЪЕКТА*\n\n"
            f"Вы действительно хотите удалить объект:\n"
            f"*{project[0]}*\n\n"
            f"⚠️ *ВНИМАНИЕ:* Будут также удалены все связанные материалы и зарплаты!",
            parse_mode='Markdown',
            reply_markup=confirmation_keyboard('delete_project', project_id)
        )

# Обработка выбора материала/зарплаты для редактирования/удаления
async def handle_item_selection(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # edit, delete
    item_type = data_parts[1]    # material, salary
    item_id = data_parts[2]
    
    conn = sqlite3.connect(DB_PATH)
    
    if item_type == 'material':
        item = conn.execute("""
            SELECT m.name, m.quantity, m.unit, m.total_price, p.name 
            FROM materials m 
            JOIN projects p ON m.project_id = p.id 
            WHERE m.id = ?
        """, (item_id,)).fetchone()
    else:  # salary
        item = conn.execute("""
            SELECT s.work_type, s.description, s.amount, p.name 
            FROM salaries s 
            JOIN projects p ON s.project_id = p.id 
            WHERE s.id = ?
        """, (item_id,)).fetchone()
    
    conn.close()
    
    context.user_data['selected_item_id'] = item_id
    context.user_data['selected_item_type'] = item_type
    
    if action_type == 'edit':
        context.user_data['awaiting_input'] = f'edit_{item_type}_data'
        
        if item_type == 'material':
            await query.edit_message_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"✏️ *РЕДАКТИРОВАНИЕ МАТЕРИАЛА*\n\n"
                f"Объект: *{item[4]}*\n"
                f"Текущие данные:\n"
                f"• Название: {item[0]}\n"
                f"• Количество: {item[1]} {item[2]}\n"
                f"• Сумма: {item[3]:,.2f} руб.\n\n"
                f"Введите новые данные в формате:\n"
                f"`Новое название количество единица_измерения общая_стоимость`\n\n"
                f"*ПРИМЕР:* `Кирпич белый 1500 шт 42750`",
                parse_mode='Markdown',
                reply_markup=back_button(f'edit_{item_type}')
            )
        else:  # salary
            await query.edit_message_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"✏️ *РЕДАКТИРОВАНИЕ ЗАРПЛАТЫ*\n\n"
                f"Объект: *{item[3]}*\n"
                f"Текущие данные:\n"
                f"• Вид работ: {item[0]}\n"
                f"• Описание: {item[1]}\n"
                f"• Сумма: {item[2]:,.2f} руб.\n\n"
                f"Введите новые данные в формате:\n"
                f"`Вид_работ описание сумма`\n\n"
                f"*ПРИМЕР:* `Кладка кирпича декабрь 28000`",
                parse_mode='Markdown',
                reply_markup=back_button(f'edit_{item_type}')
            )
    
    elif action_type == 'delete':
        if item_type == 'material':
            await query.edit_message_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"🗑️ *УДАЛЕНИЕ МАТЕРИАЛА*\n\n"
                f"Вы действительно хотите удалить материал:\n"
                f"*{item[0]}*\n"
                f"Объект: *{item[4]}*\n"
                f"Количество: {item[1]} {item[2]}\n"
                f"Сумма: {item[3]:,.2f} руб.",
                parse_mode='Markdown',
                reply_markup=confirmation_keyboard(f'delete_{item_type}', item_id)
            )
        else:  # salary
            await query.edit_message_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"🗑️ *УДАЛЕНИЕ ЗАРПЛАТЫ*\n\n"
                f"Вы действительно хотите удалить начисление:\n"
                f"*{item[0]}*\n"
                f"Объект: *{item[3]}*\n"
                f"Описание: {item[1]}\n"
                f"Сумма: {item[2]:,.2f} руб.",
                parse_mode='Markdown',
                reply_markup=confirmation_keyboard(f'delete_{item_type}', item_id)
            )

# Обработка подтверждения действий
async def handle_confirmation(query, context):
    data_parts = query.data.split('_')
    action = data_parts[0]  # confirm, cancel
    item_type = data_parts[1] if len(data_parts) > 2 else None
    item_id = data_parts[2] if len(data_parts) > 2 else None
    
    if action == 'cancel':
        await show_main_menu(query)
        return
    
    # Подтверждение удаления проекта
    if item_type == 'delete_project':
        conn = sqlite3.connect(DB_PATH)
        
        # Получаем название проекта перед удалением
        project_name = conn.execute("SELECT name FROM projects WHERE id = ?", (item_id,)).fetchone()[0]
        
        # Удаляем связанные материалы и зарплаты
        conn.execute("DELETE FROM materials WHERE project_id = ?", (item_id,))
        conn.execute("DELETE FROM salaries WHERE project_id = ?", (item_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ОБЪЕКТ УДАЛЕН*\n\n"
            f"Объект *{project_name}* и все связанные данные успешно удалены из системы.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    
    # Подтверждение удаления материала
    elif item_type == 'delete_material':
        conn = sqlite3.connect(DB_PATH)
        
        # Получаем данные материала перед удалением
        material = conn.execute("""
            SELECT m.name, p.name 
            FROM materials m 
            JOIN projects p ON m.project_id = p.id 
            WHERE m.id = ?
        """, (item_id,)).fetchone()
        
        conn.execute("DELETE FROM materials WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *МАТЕРИАЛ УДАЛЕН*\n\n"
            f"Материал *{material[0]}* с объекта *{material[1]}* успешно удален из системы.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    
    # Подтверждение удаления зарплаты
    elif item_type == 'delete_salary':
        conn = sqlite3.connect(DB_PATH)
        
        # Получаем данные зарплаты перед удалением
        salary = conn.execute("""
            SELECT s.work_type, p.name 
            FROM salaries s 
            JOIN projects p ON s.project_id = p.id 
            WHERE s.id = ?
        """, (item_id,)).fetchone()
        
        conn.execute("DELETE FROM salaries WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ЗАРПЛАТА УДАЛЕНА*\n\n"
            f"Начисление *{salary[0]}* с объекта *{salary[1]}* успешно удалено из системы.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    
    # Подтверждение очистки всех данных
    elif item_type == 'clear_all':
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM materials")
        conn.execute("DELETE FROM salaries")
        conn.execute("DELETE FROM projects")
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ВСЕ ДАННЫЕ ОЧИЩЕНЫ*\n\n"
            f"База данных полностью очищена. Система готова к новой работе.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )

# Обработка кнопки "Назад"
async def handle_back_button(query, context):
    data_parts = query.data.split('_')
    target = '_'.join(data_parts[2:]) if len(data_parts) > 2 else query.data.replace('back_to_', '')
    
    if target == 'main_menu':
        await show_main_menu(query)
    elif target == 'materials_menu':
        await show_materials_menu(query)
    elif target == 'salaries_menu':
        await show_salaries_menu(query)
    elif target == 'reports_menu':
        await show_reports_menu(query)
    elif target == 'settings_menu':
        await show_settings_menu(query)
    elif target == 'add_material':
        await add_material_handler(query, context)
    elif target == 'add_salary':
        await add_salary_handler(query, context)
    elif target == 'project_stats':
        await project_stats_handler(query, context)
    elif target == 'detailed_report':
        await detailed_report_handler(query, context)
    elif target == 'material_menu':
        await show_materials_menu(query)
    elif target == 'salary_menu':
        await show_salaries_menu(query)
    elif target == 'stats_menu':
        await show_reports_menu(query)
    elif target == 'edit_project':
        await edit_project_handler(query, context)
    elif target == 'edit_material':
        await edit_material_handler(query, context)
    elif target == 'edit_salary':
        await edit_salary_handler(query, context)
    else:
        await show_main_menu(query)

# Обработка единиц измерения материалов
async def handle_material_unit(query, context, unit_data):
    unit_map = {
        'unit_sh': 'шт', 'unit_kg': 'кг', 'unit_t': 'т', 
        'unit_m3': 'м³', 'unit_m2': 'м²', 'unit_m': 'м',
        'unit_l': 'л', 'unit_pack': 'упак'
    }
    
    if unit_data in unit_map:
        context.user_data['material_unit'] = unit_map[unit_data]
        context.user_data['awaiting_input'] = 'material_total_price'
        
        selected_unit = unit_map[unit_data]
        
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"📦 *ПРИХОД МАТЕРИАЛОВ*\n\n"
            f"📦 Материал: *{context.user_data['material_name']}*\n"
            f"🔢 Количество: *{context.user_data['material_quantity']} {selected_unit}*\n\n"
            f"💰 Введите *общую стоимость* материала (руб.):\n\n"
            f"*ПРИМЕР:* `25500.50`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
    else:
        await handle_back_button(query, context)

# ОСНОВНОЙ ОБРАБОТЧИК КНОПОК
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # Главное меню и навигация
        if data == 'main_menu':
            await show_main_menu(query)
        elif data == 'materials_menu':
            await show_materials_menu(query)
        elif data == 'salaries_menu':
            await show_salaries_menu(query)
        elif data == 'reports_menu':
            await show_reports_menu(query)
        elif data == 'settings_menu':
            await show_settings_menu(query)
        
        # Проекты
        elif data == 'add_project':
            await add_project_handler(query, context)
        elif data == 'list_projects':
            await list_projects_handler(query)
        elif data == 'edit_project':
            await edit_project_handler(query, context)
        elif data == 'delete_project':
            await delete_project_handler(query, context)
        
        # Материалы
        elif data == 'add_material':
            await add_material_handler(query, context)
        elif data == 'list_materials':
            await list_materials_handler(query)
        elif data == 'search_materials':
            await search_materials_handler(query, context)
        elif data == 'edit_material':
            await edit_material_handler(query, context)
        elif data == 'delete_material':
            await delete_material_handler(query, context)
        
        # Зарплаты
        elif data == 'add_salary':
            await add_salary_handler(query, context)
        elif data == 'list_salaries':
            await list_salaries_handler(query)
        elif data == 'search_salaries':
            await search_salaries_handler(query, context)
        elif data == 'edit_salary':
            await edit_salary_handler(query, context)
        elif data == 'delete_salary':
            await delete_salary_handler(query, context)
        
        # Отчеты
        elif data == 'overall_stats':
            await overall_stats_handler(query)
        elif data == 'project_stats':
            await project_stats_handler(query, context)
        elif data == 'detailed_report':
            await detailed_report_handler(query, context)
        elif data == 'export_excel':
            await export_excel_handler(query)
        elif data == 'sync_gs':
            await sync_gs_handler(query)
        
        # Настройки
        elif data == 'clear_data':
            await clear_data_handler(query, context)
        
        # Обработка выбора проекта
        elif data.startswith(('material_project_', 'salary_project_', 'stats_project_', 'report_project_', 'edit_project_', 'delete_project_')):
            await handle_project_selection(query, context)
        
        # Обработка единиц измерения материалов
        elif data.startswith('unit_'):
            await handle_material_unit(query, context, data)
        
        # Обработка выбора материала/зарплаты для редактирования/удаления
        elif data.startswith(('edit_material_', 'delete_material_', 'edit_salary_', 'delete_salary_')):
            await handle_item_selection(query, context)
        
        # Подтверждение действий
        elif data.startswith(('confirm_', 'cancel_')):
            await handle_confirmation(query, context)
        
        # Назад
        elif data.startswith('back_to_'):
            await handle_back_button(query, context)
        
        else:
            logger.warning(f"Неизвестный callback_data: {data}")
            await query.edit_message_text(
                "❌ Неизвестная команда. Возврат в главное меню.",
                reply_markup=main_menu_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка. Возврат в главное меню.",
            reply_markup=main_menu_keyboard()
        )

# ФУНКЦИИ ОБРАБОТКИ ТЕКСТОВЫХ СООБЩЕНИЙ - УПРОЩЕННАЯ ВЕРСИЯ
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = update.message.text
    
    if 'awaiting_input' not in user_data:
        await update.message.reply_text(
            "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            "Используйте меню для навигации по системе:",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        return
    
    state = user_data['awaiting_input']
    
    # Обработка проектов - ПРОСТАЯ ВЕРСИЯ
    if state == 'project_name':
        await handle_simple_project_registration(update, context, text)
    
    # Обработка материалов
    elif state == 'material_name':
        await handle_material_name(update, context, text)
    elif state == 'material_quantity':
        await handle_material_quantity(update, context, text)
    elif state == 'material_total_price':
        await handle_material_total_price(update, context, text)
    
    # Обработка зарплат
    elif state == 'salary_work_type':
        await handle_salary_work_type(update, context, text)
    elif state == 'salary_description':
        await handle_salary_description(update, context, text)
    elif state == 'salary_amount':
        await handle_salary_amount(update, context, text)
    elif state == 'salary_work_date':
        await handle_salary_work_date(update, context, text)
    
    # Поиск
    elif state == 'search_materials':
        await handle_search_materials(update, context, text)
    elif state == 'search_salaries':
        await handle_search_salaries(update, context, text)
    
    # Редактирование
    elif state == 'edit_project_name':
        await handle_edit_project_name(update, context, text)
    elif state == 'edit_material_data':
        await handle_edit_material_data(update, context, text)
    elif state == 'edit_salary_data':
        await handle_edit_salary_data(update, context, text)

# ПРОСТАЯ ФУНКЦИЯ РЕГИСТРАЦИИ ПРОЕКТА
async def handle_simple_project_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    project_name = text
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO projects (name, address) VALUES (?, ?)", (project_name, "Адрес не указан"))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ОБЪЕКТ ЗАРЕГИСТРИРОВАН*\n\n"
            f"🏗️ Наименование: *{project_name}*\n\n"
            f"Объект успешно внесен в корпоративную систему учета.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Объект с таким наименованием уже зарегистрирован в системе!",
            reply_markup=back_button('add_project')
        )
    except Exception as e:
        logger.error(f"Project registration error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при регистрации объекта! Обратитесь к системному администратору.",
            reply_markup=back_button('add_project')
        )
    
    context.user_data.clear()

# Обработчики материалов
async def handle_material_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['material_name'] = text
    context.user_data['awaiting_input'] = 'material_quantity'
    
    await update.message.reply_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"📦 *ПРИХОД МАТЕРИАЛОВ*\n\n"
        f"📦 Материал: *{text}*\n\n"
        f"🔢 Введите *количество*:",
        parse_mode='Markdown',
        reply_markup=back_button('add_material')
    )

async def handle_material_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        quantity = float(text.replace(',', '.'))
        context.user_data['material_quantity'] = quantity
        context.user_data['awaiting_input'] = 'material_unit'
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"📦 *ПРИХОД МАТЕРИАЛОВ*\n\n"
            f"📦 Материал: *{context.user_data['material_name']}*\n"
            f"🔢 Количество: *{quantity}*\n\n"
            f"📏 Выберите *единицу измерения*:",
            parse_mode='Markdown',
            reply_markup=unit_selection_keyboard()
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат числа! Введите количество цифрами:",
            reply_markup=back_button('add_material')
        )

async def handle_material_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        total_price = float(text.replace(',', '.'))
        quantity = context.user_data['material_quantity']
        unit_price = total_price / quantity if quantity > 0 else 0
        
        material_data = {
            'name': context.user_data['material_name'],
            'quantity': quantity,
            'unit': context.user_data['material_unit'],
            'unit_price': unit_price,
            'total_price': total_price
        }
        
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO materials (project_id, name, quantity, unit, unit_price, total_price) VALUES (?, ?, ?, ?, ?, ?)",
                (context.user_data['selected_project'], material_data['name'], material_data['quantity'], 
                 material_data['unit'], material_data['unit_price'], material_data['total_price'])
            )
            conn.commit()
            conn.close()
            
            project_name = context.user_data['selected_project_name']
            
            await update.message.reply_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"✅ *МАТЕРИАЛ ОПРИХОДОВАН*\n\n"
                f"🏗️ Объект: *{project_name}*\n"
                f"📦 Материал: *{material_data['name']}*\n"
                f"📊 Количество: *{material_data['quantity']} {material_data['unit']}*\n"
                f"💰 Цена за единицу: *{material_data['unit_price']:,.2f} руб.*\n"
                f"🧮 Общая стоимость: *{material_data['total_price']:,.2f} руб.*\n\n"
                f"Материал успешно внесен в систему учета.",
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Material error: {e}")
            await update.message.reply_text(
                "❌ Ошибка при оприходовании материала! Обратитесь к системному администратору.",
                reply_markup=back_button('add_material')
            )
        
        context.user_data.clear()
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы! Введите число:",
            reply_markup=back_button('add_material')
        )

# Обработчики зарплат
async def handle_salary_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_work_type'] = text
    context.user_data['awaiting_input'] = 'salary_description'
    
    await update.message.reply_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"💰 *НАЧИСЛЕНИЕ ЗАРПЛАТЫ*\n\n"
        f"🔧 Вид работ: *{text}*\n\n"
        f"📝 Введите *подробное описание* работ:\n\n"
        f"*ПРИМЕР:* `Кладка кирпича 3 этажа` или `Зарплата за ноябрь 2024`",
        parse_mode='Markdown',
        reply_markup=back_button('add_salary')
    )

async def handle_salary_description(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_description'] = text
    context.user_data['awaiting_input'] = 'salary_amount'
    
    await update.message.reply_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"💰 *НАЧИСЛЕНИЕ ЗАРПЛАТЫ*\n\n"
        f"🔧 Вид работ: *{context.user_data['salary_work_type']}*\n"
        f"📝 Описание: *{text}*\n\n"
        f"💵 Введите *сумму* начисления (руб.):\n\n"
        f"*ПРИМЕР:* `25000` или `35500.75`",
        parse_mode='Markdown',
        reply_markup=back_button('add_salary')
    )

async def handle_salary_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        amount = float(text.replace(',', '.'))
        context.user_data['salary_amount'] = amount
        context.user_data['awaiting_input'] = 'salary_work_date'
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"💰 *НАЧИСЛЕНИЕ ЗАРПЛАТЫ*\n\n"
            f"🔧 Вид работ: *{context.user_data['salary_work_type']}*\n"
            f"📝 Описание: *{context.user_data['salary_description']}*\n"
            f"💵 Сумма: *{amount:,.2f} руб.*\n\n"
            f"📅 Введите *дату выполнения работ* (ДД.ММ.ГГГГ):\n\n"
            f"*ПРИМЕР:* `15.11.2024` или сегодняшняя дата: `{datetime.now().strftime('%d.%m.%Y')}`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы! Введите число:",
            reply_markup=back_button('add_salary')
        )

async def handle_salary_work_date(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        work_date = datetime.strptime(text, '%d.%m.%Y').date()
        
        salary_data = {
            'work_type': context.user_data['salary_work_type'],
            'description': context.user_data['salary_description'],
            'amount': context.user_data['salary_amount'],
            'work_date': work_date
        }
        
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO salaries (project_id, work_type, description, amount, work_date) VALUES (?, ?, ?, ?, ?)",
                (context.user_data['selected_project'], salary_data['work_type'], salary_data['description'], 
                 salary_data['amount'], salary_data['work_date'])
            )
            conn.commit()
            conn.close()
            
            project_name = context.user_data['selected_project_name']
            
            await update.message.reply_text(
                f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                f"✅ *ЗАРПЛАТА НАЧИСЛЕНА*\n\n"
                f"🏗️ Объект: *{project_name}*\n"
                f"🔧 Вид работ: *{salary_data['work_type']}*\n"
                f"📝 Описание: *{salary_data['description']}*\n"
                f"💵 Сумма: *{salary_data['amount']:,.2f} руб.*\n"
                f"📅 Дата работ: *{salary_data['work_date'].strftime('%d.%m.%Y')}*\n\n"
                f"Начисление успешно внесено в систему учета.",
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Salary error: {e}")
            await update.message.reply_text(
                "❌ Ошибка при начислении заработной платы! Обратитесь к системному администратору.",
                reply_markup=back_button('add_salary')
            )
        
        context.user_data.clear()
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты! Введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=back_button('add_salary')
        )

# Обработчики поиска
async def handle_search_materials(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.name, m.quantity, m.unit, m.total_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        WHERE m.name LIKE ?
        ORDER BY m.date_added DESC
        LIMIT 20
    """, (f'%{text}%',)).fetchall()
    conn.close()
    
    if not materials:
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"🔍 *РЕЗУЛЬТАТЫ ПОИСКА МАТЕРИАЛОВ*\n\n"
            f"По запросу: '*{text}*'\n\n"
            f"Материалы не найдены.",
            parse_mode='Markdown',
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n🔍 *РЕЗУЛЬТАТЫ ПОИСКА МАТЕРИАЛОВ*\n\nПо запросу: '*{text}*'\n\n"
    for i, material in enumerate(materials, 1):
        materials_text += f"*{i}. {material[0]}*\n"
        materials_text += f"   🏗️ Объект: {material[4]}\n"
        materials_text += f"   📊 Количество: {material[1]} {material[2]}\n"
        materials_text += f"   💰 Стоимость: {material[3]:,.2f} руб.\n"
        materials_text += f"   📅 Дата: {material[5][:10]}\n\n"
    
    await update.message.reply_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )
    
    context.user_data.clear()

async def handle_search_salaries(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.work_type, s.description, s.amount, p.name, s.work_date
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        WHERE s.description LIKE ? OR s.work_type LIKE ?
        ORDER BY s.work_date DESC
        LIMIT 20
    """, (f'%{text}%', f'%{text}%')).fetchall()
    conn.close()
    
    if not salaries:
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"🔍 *РЕЗУЛЬТАТЫ ПОИСКА НАЧИСЛЕНИЙ*\n\n"
            f"По запросу: '*{text}*'\n\n"
            f"Начисления не найдены.",
            parse_mode='Markdown',
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n🔍 *РЕЗУЛЬТАТЫ ПОИСКА НАЧИСЛЕНИЙ*\n\nПо запросу: '*{text}*'\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"*{i}. {salary[0]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[3]}\n"
        salaries_text += f"   📝 Описание: {salary[1]}\n"
        salaries_text += f"   💰 Сумма: {salary[2]:,.2f} руб.\n"
        salaries_text += f"   📅 Дата: {salary[4]}\n\n"
    
    await update.message.reply_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )
    
    context.user_data.clear()

# Обработчики редактирования
async def handle_edit_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    project_id = context.user_data['selected_project']
    
    try:
        conn = sqlite3.connect(DB_PATH)
        old_name = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (text, project_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ОБЪЕКТ ОБНОВЛЕН*\n\n"
            f"Старое название: *{old_name}*\n"
            f"Новое название: *{text}*\n\n"
            f"Данные объекта успешно обновлены.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Объект с таким наименованием уже существует в системе!",
            reply_markup=back_button('edit_project')
        )
    except Exception as e:
        logger.error(f"Edit project error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при обновлении объекта!",
            reply_markup=back_button('edit_project')
        )
    
    context.user_data.clear()

async def handle_edit_material_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    material_id = context.user_data['selected_item_id']
    
    try:
        parts = text.split()
        if len(parts) < 4:
            raise ValueError("Недостаточно данных")
        
        name = ' '.join(parts[:-3])
        quantity = float(parts[-3])
        unit = parts[-2]
        total_price = float(parts[-1])
        unit_price = total_price / quantity if quantity > 0 else 0
        
        conn = sqlite3.connect(DB_PATH)
        
        old_data = conn.execute("SELECT name, quantity, unit, total_price FROM materials WHERE id = ?", (material_id,)).fetchone()
        
        conn.execute(
            "UPDATE materials SET name = ?, quantity = ?, unit = ?, unit_price = ?, total_price = ? WHERE id = ?",
            (name, quantity, unit, unit_price, total_price, material_id)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *МАТЕРИАЛ ОБНОВЛЕН*\n\n"
            f"*Старые данные:*\n"
            f"• Название: {old_data[0]}\n"
            f"• Количество: {old_data[1]} {old_data[2]}\n"
            f"• Сумма: {old_data[3]:,.2f} руб.\n\n"
            f"*Новые данные:*\n"
            f"• Название: {name}\n"
            f"• Количество: {quantity} {unit}\n"
            f"• Сумма: {total_price:,.2f} руб.\n\n"
            f"Материал успешно обновлен в системе.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Edit material error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при обновлении материала! Проверьте формат данных.",
            reply_markup=back_button('edit_material')
        )
    
    context.user_data.clear()

async def handle_edit_salary_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    salary_id = context.user_data['selected_item_id']
    
    try:
        parts = text.split()
        if len(parts) < 3:
            raise ValueError("Недостаточно данных")
        
        work_type = parts[0]
        description = ' '.join(parts[1:-1])
        amount = float(parts[-1])
        
        conn = sqlite3.connect(DB_PATH)
        
        old_data = conn.execute("SELECT work_type, description, amount FROM salaries WHERE id = ?", (salary_id,)).fetchone()
        
        conn.execute(
            "UPDATE salaries SET work_type = ?, description = ?, amount = ? WHERE id = ?",
            (work_type, description, amount, salary_id)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ЗАРПЛАТА ОБНОВЛЕНА*\n\n"
            f"*Старые данные:*\n"
            f"• Вид работ: {old_data[0]}\n"
            f"• Описание: {old_data[1]}\n"
            f"• Сумма: {old_data[2]:,.2f} руб.\n\n"
            f"*Новые данные:*\n"
            f"• Вид работ: {work_type}\n"
            f"• Описание: {description}\n"
            f"• Сумма: {amount:,.2f} руб.\n\n"
            f"Начисление успешно обновлено в системе.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Edit salary error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при обновлении зарплаты! Проверьте формат данных.",
            reply_markup=back_button('edit_salary')
        )
    
    context.user_data.clear()

# Функции для отчетов
async def show_project_stats(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    
    project_info = conn.execute("SELECT address FROM projects WHERE id = ?", (project_id,)).fetchone()
    address = project_info[0] if project_info else "Адрес не указан"
    
    project_stats = conn.execute("""
        SELECT COALESCE(SUM(m.total_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    
    materials = conn.execute("""
        SELECT name, quantity, unit, total_price
        FROM materials 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    salaries = conn.execute("""
        SELECT work_type, description, amount, work_date
        FROM salaries 
        WHERE project_id = ?
        ORDER BY work_date DESC
    """, (project_id,)).fetchall()
    
    conn.close()
    
    total_cost = project_stats[0] + project_stats[1]
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    stats_text = f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n📅 {current_date}\n\n📊 *ФИНАНСОВАЯ СТАТИСТИКА*\n\n"
    stats_text += f"🏗️ Объект: *{project_name}*\n"
    stats_text += f"📍 Адрес: {address}\n\n"
    stats_text += f"📦 Затраты на материалы: *{project_stats[0]:,.2f} руб.*\n"
    stats_text += f"👷 Фонд оплаты труда: *{project_stats[1]:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    if materials:
        stats_text += "📦 *МАТЕРИАЛЬНЫЕ РЕСУРСЫ:*\n"
        for material in materials:
            stats_text += f"• {material[0]}: {material[1]} {material[2]} = {material[3]:,.2f} руб.\n"
        stats_text += "\n"
    
    if salaries:
        stats_text += "💰 *ФОНД ОПЛАТЫ ТРУДА:*\n"
        for salary in salaries:
            stats_text += f"• {salary[0]} ({salary[1]}): {salary[2]:,.2f} руб. ({salary[3]})\n"
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=back_button('project_stats')
    )

async def show_detailed_report(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    
    project_info = conn.execute("SELECT address FROM projects WHERE id = ?", (project_id,)).fetchone()
    address = project_info[0] if project_info else "Адрес не указан"
    
    project_stats = conn.execute("""
        SELECT COALESCE(SUM(m.total_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost,
               COUNT(DISTINCT m.id) as materials_count,
               COUNT(DISTINCT s.id) as salaries_count
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    
    materials = conn.execute("""
        SELECT name, quantity, unit, total_price, date_added
        FROM materials 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    salaries = conn.execute("""
        SELECT work_type, description, amount, work_date
        FROM salaries 
        WHERE project_id = ?
        ORDER BY work_date DESC
    """, (project_id,)).fetchall()
    
    conn.close()
    
    total_cost = project_stats[0] + project_stats[1]
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    report_text = f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n📅 {current_date}\n\n📋 *ДЕТАЛИЗИРОВАННЫЙ ОТЧЕТ*\n\n"
    report_text += f"🏗️ Объект: *{project_name}*\n"
    report_text += f"📍 Адрес: {address}\n\n"
    report_text += f"📦 Материальные затраты: {project_stats[0]:,.2f} руб. ({project_stats[2]} позиций)\n"
    report_text += f"👷 Фонд оплаты труда: {project_stats[1]:,.2f} руб. ({project_stats[3]} начислений)\n"
    report_text += f"💰 Всего затрат: {total_cost:,.2f} руб.\n\n"
    
    report_text += "📦 *ДЕТАЛИЗАЦИЯ МАТЕРИАЛОВ:*\n"
    if materials:
        for i, material in enumerate(materials, 1):
            report_text += f"\n{i}. *{material[0]}*\n"
            report_text += f"   Количество: {material[1]} {material[2]}\n"
            report_text += f"   Стоимость: {material[3]:,.2f} руб.\n"
            report_text += f"   Дата оприходования: {material[4][:10]}\n"
    else:
        report_text += "\n   Материалы не зарегистрированы\n"
    
    report_text += "\n💰 *ДЕТАЛИЗАЦИЯ НАЧИСЛЕНИЙ:*\n"
    if salaries:
        for i, salary in enumerate(salaries, 1):
            report_text += f"\n{i}. *{salary[0]}*\n"
            report_text += f"   Описание: {salary[1]}\n"
            report_text += f"   Сумма: {salary[2]:,.2f} руб.\n"
            report_text += f"   Дата работ: {salary[3]}\n"
    else:
        report_text += "\n   Начисления не производились\n"
    
    await query.edit_message_text(
        report_text,
        parse_mode='Markdown',
        reply_markup=back_button('detailed_report')
    )

# Основная функция
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Завершение работы.")
        return
    
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("Бот ООО «ИСК ГЕОСТРОЙ» запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
