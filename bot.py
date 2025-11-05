import sqlite3
import pandas as pd
import gspread
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен из переменных окружения
DB_PATH = 'construction.db'
GC_CREDENTIALS = 'credentials.json'
GSHEET_NAME = 'Construction Tracker'
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

# Проверка наличия токена
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS projects
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT UNIQUE,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS materials
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    project_id INTEGER,
                    name TEXT,
                    quantity REAL,
                    unit TEXT,
                    unit_price REAL,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id))''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS salaries
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    project_id INTEGER,
                    description TEXT,
                    amount REAL,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id))''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS admins
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Добавляем первого админа если нет
    if ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
    
    conn.commit()
    conn.close()

# Проверка прав администратора
def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    admin = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return admin is not None

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
        [InlineKeyboardButton("✏️ Редактировать материалы", callback_data='edit_materials')],
        [InlineKeyboardButton("🗑️ Удалить материал", callback_data='delete_materials')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def salaries_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💵 Добавить зарплату", callback_data='add_salary')],
        [InlineKeyboardButton("📋 Список зарплат", callback_data='list_salaries')],
        [InlineKeyboardButton("✏️ Редактировать зарплаты", callback_data='edit_salaries')],
        [InlineKeyboardButton("🗑️ Удалить зарплату", callback_data='delete_salaries')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def reports_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📈 Общая статистика", callback_data='overall_stats')],
        [InlineKeyboardButton("🏗️ Статистика по объекту", callback_data='project_stats')],
        [InlineKeyboardButton("📊 Детальный отчет", callback_data='detailed_report')],
        [InlineKeyboardButton("📤 Экспорт в Excel", callback_data='export_excel')],
        [InlineKeyboardButton("☁️ Синхронизация с Google Sheets", callback_data='sync_gs')],
        [InlineKeyboardButton("🔗 ID Google Sheets", callback_data='gsheet_id')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("🔄 Очистить данные", callback_data='clear_data')],
        [InlineKeyboardButton("📋 Список объектов", callback_data='list_projects')],
        [InlineKeyboardButton("✏️ Редактировать объекты", callback_data='edit_projects')],
        [InlineKeyboardButton("🗑️ Удалить объект", callback_data='delete_projects')],
    ]
    
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Управление админами", callback_data='admin_management')])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

def admin_management_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить админа", callback_data='add_admin')],
        [InlineKeyboardButton("📋 Список админов", callback_data='list_admins')],
        [InlineKeyboardButton("🗑️ Удалить админа", callback_data='delete_admin')],
        [InlineKeyboardButton("↩️ Назад", callback_data='settings_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def units_keyboard():
    keyboard = [
        [InlineKeyboardButton("🪨 Штуки", callback_data='unit_шт')],
        [InlineKeyboardButton("📦 Кубы (м³)", callback_data='unit_м³')],
        [InlineKeyboardButton("📐 Квадраты (м²)", callback_data='unit_м²')],
        [InlineKeyboardButton("🎒 Мешки", callback_data='unit_меш')],
        [InlineKeyboardButton("⚖️ Килограммы", callback_data='unit_кг')],
        [InlineKeyboardButton("📏 Метры", callback_data='unit_м')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_materials')]
    ]
    return InlineKeyboardMarkup(keyboard)

def projects_keyboard(action):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects ORDER BY created_date DESC").fetchall()
    conn.close()
    
    keyboard = []
    for project in projects:
        keyboard.append([InlineKeyboardButton(f"🏗️ {project[1]}", callback_data=f'{action}_project_{project[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data=f'back_to_{action.split("_")[0]}')])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

def confirmation_keyboard(action, item_id):
    keyboard = [
        [InlineKeyboardButton("✅ Да, подтверждаю", callback_data=f'confirm_{action}_{item_id}')],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f'cancel_{action}_{item_id}')]
    ]
    return InlineKeyboardMarkup(keyboard)

def edit_options_keyboard(item_type, item_id):
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f'edit_{item_type}_{item_id}')],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f'delete_{item_type}_{item_id}')],
        [InlineKeyboardButton("↩️ Назад", callback_data=f'back_to_list_{item_type}')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button(target_menu):
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data=target_menu)]]
    return InlineKeyboardMarkup(keyboard)

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_text = f"""
🏢 *ООО ИКС "ГЕОСТРОЙ"*

👋 Добро пожаловать, {user.first_name}!

🏗️ *Construction Manager Bot* поможет вам:
• 📝 Вести учет строительных объектов
• 📦 Управлять материалами и расходами
• 💰 Контролировать зарплаты сотрудников
• 📊 Анализировать статистику и создавать отчеты

Выберите действие из меню ниже:
    """
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Главное меню и навигация
    if query.data == 'main_menu':
        await show_main_menu(query)
    elif query.data == 'materials_menu':
        await show_materials_menu(query)
    elif query.data == 'salaries_menu':
        await show_salaries_menu(query)
    elif query.data == 'reports_menu':
        await show_reports_menu(query)
    elif query.data == 'settings_menu':
        await show_settings_menu(query, user_id)
    
    # Админ-меню
    elif query.data == 'admin_management':
        if is_admin(user_id):
            await show_admin_management(query)
        else:
            await query.edit_message_text("❌ У вас нет прав доступа!")
    elif query.data == 'add_admin':
        await add_admin_handler(query, context)
    elif query.data == 'list_admins':
        await list_admins_handler(query)
    
    # Проекты
    elif query.data == 'add_project':
        await add_project_handler(query, context)
    elif query.data == 'list_projects':
        await list_projects_handler(query)
    elif query.data == 'edit_projects':
        await edit_projects_handler(query, context)
    elif query.data == 'delete_projects':
        await delete_projects_handler(query, context)
    
    # Материалы
    elif query.data == 'add_material':
        await add_material_handler(query, context)
    elif query.data == 'list_materials':
        await list_materials_handler(query)
    elif query.data == 'edit_materials':
        await edit_materials_handler(query, context)
    elif query.data == 'delete_materials':
        await delete_materials_handler(query, context)
    
    # Зарплаты
    elif query.data == 'add_salary':
        await add_salary_handler(query, context)
    elif query.data == 'list_salaries':
        await list_salaries_handler(query)
    elif query.data == 'edit_salaries':
        await edit_salaries_handler(query, context)
    elif query.data == 'delete_salaries':
        await delete_salaries_handler(query, context)
    
    # Отчеты
    elif query.data == 'overall_stats':
        await overall_stats_handler(query)
    elif query.data == 'project_stats':
        await project_stats_handler(query, context)
    elif query.data == 'detailed_report':
        await detailed_report_handler(query)
    elif query.data == 'export_excel':
        await export_excel_handler(query)
    elif query.data == 'sync_gs':
        await sync_gs_handler(query)
    elif query.data == 'gsheet_id':
        await gsheet_id_handler(query)
    
    # Обработка выбора проекта
    elif query.data.startswith(('material_project_', 'salary_project_', 'stats_project_', 'edit_project_', 'delete_project_')):
        await handle_project_selection(query, context)
    
    # Обработка выбора единиц измерения
    elif query.data.startswith('unit_'):
        await handle_unit_selection(query, context)
    
    # Обработка редактирования и удаления
    elif query.data.startswith(('edit_', 'delete_')):
        await handle_edit_delete(query, context)
    
    # Обработка подтверждений
    elif query.data.startswith(('confirm_', 'cancel_')):
        await handle_confirmation(query, context)
    
    # Назад
    elif query.data.startswith('back_to_'):
        await handle_back_button(query, context, user_id)

# Меню
async def show_main_menu(query):
    await query.edit_message_text(
        "🏢 *ООО ИКС \"ГЕОСТРОЙ\"*\n\n🏠 *Главное меню* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def show_materials_menu(query):
    await query.edit_message_text(
        "📦 *Управление материалами* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=materials_menu_keyboard()
    )

async def show_salaries_menu(query):
    await query.edit_message_text(
        "💰 *Управление зарплатами* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=salaries_menu_keyboard()
    )

async def show_reports_menu(query):
    await query.edit_message_text(
        "📊 *Статистика и отчеты* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=reports_menu_keyboard()
    )

async def show_settings_menu(query, user_id):
    await query.edit_message_text(
        "⚙️ *Настройки* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=settings_menu_keyboard(user_id)
    )

async def show_admin_management(query):
    await query.edit_message_text(
        "👑 *Управление администраторами* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=admin_management_keyboard()
    )

# Обработчики проектов
async def add_project_handler(query, context):
    context.user_data['awaiting_input'] = 'project_name'
    context.user_data.clear()
    await query.edit_message_text(
        "🏗️ *Добавление нового объекта*\n\nВведите название строительного объекта:",
        parse_mode='Markdown',
        reply_markup=back_button('main_menu')
    )

async def list_projects_handler(query):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("""
        SELECT p.id, p.name, p.created_date,
               COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
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
            "📋 *Список объектов*\n\nПока нет добавленных объектов.",
            parse_mode='Markdown',
            reply_markup=back_button('settings_menu')
        )
        return
    
    projects_text = "📋 *Список объектов*\n\n"
    for i, project in enumerate(projects, 1):
        total_cost = project[3] + project[4]
        projects_text += f"{i}. *{project[1]}*\n"
        projects_text += f"   📅 Создан: {project[2][:10]}\n"
        projects_text += f"   💰 Общая стоимость: {total_cost:,.2f} руб.\n"
        projects_text += f"   📦 Материалы: {project[3]:,.2f} руб.\n"
        projects_text += f"   👷 Зарплаты: {project[4]:,.2f} руб.\n\n"
    
    await query.edit_message_text(
        projects_text,
        parse_mode='Markdown',
        reply_markup=back_button('settings_menu')
    )

async def edit_projects_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Нет объектов для редактирования!",
            reply_markup=back_button('settings_menu')
        )
        return
    
    await query.edit_message_text(
        "✏️ *Редактирование объектов*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('edit')
    )

async def delete_projects_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Нет объектов для удаления!",
            reply_markup=back_button('settings_menu')
        )
        return
    
    await query.edit_message_text(
        "🗑️ *Удаление объектов*\n\nВыберите объект для удаления:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('delete')
    )

# Обработчики материалов
async def add_material_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Сначала добавьте строительный объект!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    context.user_data.clear()
    await query.edit_message_text(
        "📦 *Добавление материала*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('material')
    )

async def list_materials_handler(query):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.id, m.name, m.quantity, m.unit, m.unit_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "📦 *Последние материалы*\n\nПока нет добавленных материалов.",
            parse_mode='Markdown',
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = "📦 *Последние материалы*\n\n"
    for i, material in enumerate(materials, 1):
        total_cost = material[3] * material[4]
        materials_text += f"{i}. *{material[1]}*\n"
        materials_text += f"   🏗️ Объект: {material[5]}\n"
        materials_text += f"   📊 Количество: {material[2]} {material[3]}\n"
        materials_text += f"   💰 Цена за единицу: {material[4]:,.2f} руб.\n"
        materials_text += f"   🧮 Стоимость: {total_cost:,.2f} руб.\n"
        materials_text += f"   📅 Дата: {material[6][:10]}\n\n"
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )

async def edit_materials_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.id, m.name, p.name, m.quantity, m.unit
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "❌ Нет материалов для редактирования!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = "✏️ *Редактирование материалов*\n\nВыберите материал:\n\n"
    for i, material in enumerate(materials, 1):
        materials_text += f"{i}. *{material[1]}*\n"
        materials_text += f"   🏗️ Объект: {material[2]}\n"
        materials_text += f"   📊 Количество: {material[3]} {material[4]}\n\n"
    
    keyboard = []
    for material in materials:
        keyboard.append([InlineKeyboardButton(f"📦 {material[1]}", callback_data=f'edit_material_{material[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_materials_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.id, m.name, p.name, m.quantity, m.unit
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        ORDER BY m.date_added DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "❌ Нет материалов для удаления!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = "🗑️ *Удаление материалов*\n\nВыберите материал для удаления:\n\n"
    for i, material in enumerate(materials, 1):
        materials_text += f"{i}. *{material[1]}*\n"
        materials_text += f"   🏗️ Объект: {material[2]}\n"
        materials_text += f"   📊 Количество: {material[3]} {material[4]}\n\n"
    
    keyboard = []
    for material in materials:
        keyboard.append([InlineKeyboardButton(f"📦 {material[1]}", callback_data=f'delete_material_{material[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработчики зарплат
async def add_salary_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Сначала добавьте строительный объект!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    context.user_data.clear()
    await query.edit_message_text(
        "💰 *Добавление зарплаты*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('salary')
    )

async def list_salaries_handler(query):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.id, s.description, s.amount, p.name, s.date_added
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.date_added DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "💰 *Последние зарплаты*\n\nПока нет добавленных зарплат.",
            parse_mode='Markdown',
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = "💰 *Последние зарплаты*\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"{i}. *{salary[1]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[3]}\n"
        salaries_text += f"   💰 Сумма: {salary[2]:,.2f} руб.\n"
        salaries_text += f"   📅 Дата: {salary[4][:10]}\n\n"
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

async def edit_salaries_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.id, s.description, p.name, s.amount
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.date_added DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "❌ Нет зарплат для редактирования!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = "✏️ *Редактирование зарплат*\n\nВыберите запись:\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"{i}. *{salary[1]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[2]}\n"
        salaries_text += f"   💰 Сумма: {salary[3]:,.2f} руб.\n\n"
    
    keyboard = []
    for salary in salaries:
        keyboard.append([InlineKeyboardButton(f"💰 {salary[1][:30]}...", callback_data=f'edit_salary_{salary[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_salaries_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.id, s.description, p.name, s.amount
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        ORDER BY s.date_added DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "❌ Нет зарплат для удаления!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = "🗑️ *Удаление зарплат*\n\nВыберите запись для удаления:\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"{i}. *{salary[1]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[2]}\n"
        salaries_text += f"   💰 Сумма: {salary[3]:,.2f} руб.\n\n"
    
    keyboard = []
    for salary in salaries:
        keyboard.append([InlineKeyboardButton(f"💰 {salary[1][:30]}...", callback_data=f'delete_salary_{salary[0]}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработчики отчетов
async def overall_stats_handler(query):
    conn = sqlite3.connect(DB_PATH)
    
    total_stats = conn.execute("""
        SELECT COUNT(*) as project_count,
               COALESCE(SUM(m.quantity * m.unit_price), 0) as total_materials,
               COALESCE(SUM(s.amount), 0) as total_salaries
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
    """).fetchone()
    
    projects_stats = conn.execute("""
        SELECT p.name,
               COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        GROUP BY p.id
    """).fetchall()
    
    conn.close()
    
    total_cost = total_stats[1] + total_stats[2]
    
    stats_text = "🏢 *ООО ИКС \"ГЕОСТРОЙ\"*\n\n📈 *Общая статистика*\n\n"
    stats_text += f"🏗️ Всего объектов: *{total_stats[0]}*\n"
    stats_text += f"📦 Затраты на материалы: *{total_stats[1]:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{total_stats[2]:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    stats_text += "📊 *Статистика по объектам:*\n"
    for project in projects_stats:
        project_total = project[1] + project[2]
        stats_text += f"\n🏗️ *{project[0]}*\n"
        stats_text += f"   📦 Материалы: {project[1]:,.2f} руб.\n"
        stats_text += f"   👷 Зарплаты: {project[2]:,.2f} руб.\n"
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
            "❌ Нет объектов для отображения статистики!",
            reply_markup=back_button('reports_menu')
        )
        return
    
    await query.edit_message_text(
        "📊 *Статистика по объекту*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('stats')
    )

async def detailed_report_handler(query):
    await query.edit_message_text(
        "📋 *Детальный отчет*\n\nЭта функция в разработке...",
        parse_mode='Markdown',
        reply_markup=back_button('reports_menu')
    )

async def export_excel_handler(query):
    try:
        conn = sqlite3.connect(DB_PATH)
        
        with pd.ExcelWriter('construction_report.xlsx', engine='openpyxl') as writer:
            projects_df = pd.read_sql("SELECT * FROM projects", conn)
            projects_df.to_excel(writer, sheet_name='Проекты', index=False)
            
            materials_df = pd.read_sql("""
                SELECT p.name as project_name, m.name, m.quantity, m.unit, m.unit_price, 
                       m.quantity * m.unit_price as total_cost, m.date_added
                FROM materials m
                JOIN projects p ON m.project_id = p.id
            """, conn)
            materials_df.to_excel(writer, sheet_name='Материалы', index=False)
            
            salaries_df = pd.read_sql("""
                SELECT p.name as project_name, s.description, s.amount, s.date_added
                FROM salaries s
                JOIN projects p ON s.project_id = p.id
            """, conn)
            salaries_df.to_excel(writer, sheet_name='Зарплаты', index=False)
        
        conn.close()
        
        await query.message.reply_document(
            document=open('construction_report.xlsx', 'rb'),
            filename='construction_report.xlsx',
            caption="📤 *Файл успешно экспортирован!*",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            "✅ Файл отправлен в чат!",
            reply_markup=back_button('reports_menu')
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.edit_message_text(
            "❌ Ошибка при экспорте!",
            reply_markup=back_button('reports_menu')
        )

async def sync_gs_handler(query):
    try:
        gc = gspread.service_account(filename=GC_CREDENTIALS)
        sh = gc.open(GSHEET_NAME)
        
        conn = sqlite3.connect(DB_PATH)
        
        projects_ws = sh.worksheet('Projects')
        projects_data = conn.execute("SELECT * FROM projects").fetchall()
        projects_ws.clear()
        if projects_data:
            headers = [desc[0] for desc in conn.execute("SELECT * FROM projects").description]
            projects_ws.update([headers] + projects_data)
        
        materials_ws = sh.worksheet('Materials')
        materials_data = conn.execute("""
            SELECT p.name as project_name, m.* 
            FROM materials m 
            JOIN projects p ON m.project_id = p.id
        """).fetchall()
        materials_ws.clear()
        if materials_data:
            headers = [desc[0] for desc in conn.execute("""
                SELECT p.name as project_name, m.* 
                FROM materials m 
                JOIN projects p ON m.project_id = p.id
            """).description]
            materials_ws.update([headers] + materials_data)
        
        conn.close()
        
        await query.edit_message_text(
            "✅ *Данные синхронизированы с Google Sheets!*",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )
        
    except Exception as e:
        logger.error(f"GSync error: {e}")
        await query.edit_message_text(
            "❌ *Ошибка синхронизации! Проверьте настройки Google Sheets.*",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )

async def gsheet_id_handler(query):
    try:
        gc = gspread.service_account(filename=GC_CREDENTIALS)
        sh = gc.open(GSHEET_NAME)
        
        await query.edit_message_text(
            f"🔗 *Информация о Google Sheets*\n\n"
            f"📊 Название таблицы: *{GSHEET_NAME}*\n"
            f"🆔 ID таблицы: `{sh.id}`\n"
            f"🔗 Ссылка: https://docs.google.com/spreadsheets/d/{sh.id}",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )
        
    except Exception as e:
        logger.error(f"GSheet ID error: {e}")
        await query.edit_message_text(
            "❌ *Ошибка получения информации о таблице!*",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )

# Админ-функции
async def add_admin_handler(query, context):
    context.user_data['awaiting_input'] = 'admin_user_id'
    await query.edit_message_text(
        "👑 *Добавление администратора*\n\nВведите ID пользователя Telegram:",
        parse_mode='Markdown',
        reply_markup=back_button('admin_management')
    )

async def list_admins_handler(query):
    conn = sqlite3.connect(DB_PATH)
    admins = conn.execute("SELECT user_id, username, added_date FROM admins ORDER BY added_date").fetchall()
    conn.close()
    
    if not admins:
        await query.edit_message_text(
            "👑 *Список администраторов*\n\nПока нет добавленных администраторов.",
            parse_mode='Markdown',
            reply_markup=back_button('admin_management')
        )
        return
    
    admins_text = "👑 *Список администраторов*\n\n"
    for i, admin in enumerate(admins, 1):
        admins_text += f"{i}. ID: `{admin[0]}`\n"
        if admin[1]:
            admins_text += f"   👤 Username: @{admin[1]}\n"
        admins_text += f"   📅 Добавлен: {admin[2][:10]}\n\n"
    
    await query.edit_message_text(
        admins_text,
        parse_mode='Markdown',
        reply_markup=back_button('admin_management')
    )

# Обработка выбора проекта
async def handle_project_selection(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # material, salary, stats, edit, delete
    project_id = data_parts[2]
    
    conn = sqlite3.connect(DB_PATH)
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    context.user_data['selected_project'] = project_id
    context.user_data['selected_project_name'] = project[0]
    
    if action_type == 'material':
        context.user_data['awaiting_input'] = 'material_name'
        await query.edit_message_text(
            f"📦 *Добавление материала для объекта: {project[0]}*\n\n"
            "📝 *Шаг 1 из 3:* Введите название материала:",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
    
    elif action_type == 'salary':
        context.user_data['awaiting_input'] = 'salary_description'
        await query.edit_message_text(
            f"💰 *Добавление зарплаты для объекта: {project[0]}*\n\n"
            "📝 *Шаг 1 из 2:* Введите описание выполненной работы:",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    
    elif action_type == 'stats':
        await show_project_stats(query, project_id, project[0])
    
    elif action_type == 'edit':
        await show_project_edit_options(query, project_id, project[0])
    
    elif action_type == 'delete':
        await query.edit_message_text(
            f"🗑️ *Удаление объекта*\n\n"
            f"Вы уверены, что хотите удалить объект:\n"
            f"*{project[0]}*?\n\n"
            f"⚠️ *Внимание:* Это действие удалит все связанные материалы и зарплаты!",
            parse_mode='Markdown',
            reply_markup=confirmation_keyboard('project', project_id)
        )

async def show_project_edit_options(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    project_data = conn.execute("SELECT name, created_date FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    await query.edit_message_text(
        f"✏️ *Редактирование объекта*\n\n"
        f"🏗️ Объект: *{project_name}*\n"
        f"📅 Создан: {project_data[1][:10]}\n\n"
        f"Выберите действие:",
        parse_mode='Markdown',
        reply_markup=edit_options_keyboard('project', project_id)
    )

# Обработка выбора единиц измерения
async def handle_unit_selection(query, context):
    unit = query.data.replace('unit_', '')
    context.user_data['selected_unit'] = unit
    context.user_data['awaiting_input'] = 'material_quantity'
    
    await query.edit_message_text(
        f"📦 *Добавление материала для объекта: {context.user_data['selected_project_name']}*\n\n"
        f"📊 *Шаг 2 из 3:* Введите количество материала (в {unit}):",
        parse_mode='Markdown',
        reply_markup=back_button('material_name')
    )

async def show_project_stats(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    
    project_stats = conn.execute("""
        SELECT COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    
    materials = conn.execute("""
        SELECT name, quantity, unit, unit_price, quantity * unit_price as total
        FROM materials 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    salaries = conn.execute("""
        SELECT description, amount, date_added
        FROM salaries 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    conn.close()
    
    total_cost = project_stats[0] + project_stats[1]
    
    stats_text = f"🏢 *ООО ИКС \"ГЕОСТРОЙ\"*\n\n📊 *Статистика объекта: {project_name}*\n\n"
    stats_text += f"📦 Затраты на материалы: *{project_stats[0]:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{project_stats[1]:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    if materials:
        stats_text += "📦 *Материалы:*\n"
        for material in materials:
            stats_text += f"• {material[0]}: {material[1]} {material[2]} × {material[3]:,.2f} = {material[4]:,.2f} руб.\n"
        stats_text += "\n"
    
    if salaries:
        stats_text += "💰 *Зарплаты:*\n"
        for salary in salaries:
            stats_text += f"• {salary[0]}: {salary[1]:,.2f} руб.\n"
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=back_button('project_stats')
    )

# Обработка редактирования и удаления
async def handle_edit_delete(query, context):
    data_parts = query.data.split('_')
    action = data_parts[0]  # edit, delete
    item_type = data_parts[1]  # project, material, salary
    item_id = data_parts[2]
    
    if action == 'delete':
        if item_type == 'project':
            conn = sqlite3.connect(DB_PATH)
            project = conn.execute("SELECT name FROM projects WHERE id = ?", (item_id,)).fetchone()
            conn.close()
            
            await query.edit_message_text(
                f"🗑️ *Удаление объекта*\n\n"
                f"Вы уверены, что хотите удалить объект:\n"
                f"*{project[0]}*?\n\n"
                f"⚠️ *Внимание:* Это действие удалит все связанные материалы и зарплаты!",
                parse_mode='Markdown',
                reply_markup=confirmation_keyboard('project', item_id)
            )
        elif item_type == 'material':
            conn = sqlite3.connect(DB_PATH)
            material = conn.execute("""
                SELECT m.name, p.name, m.quantity, m.unit, m.unit_price 
                FROM materials m 
                JOIN projects p ON m.project_id = p.id 
                WHERE m.id = ?
            """, (item_id,)).fetchone()
            conn.close()
            
            await query.edit_message_text(
                f"🗑️ *Удаление материала*\n\n"
                f"Вы уверены, что хотите удалить материал:\n"
                f"*{material[0]}*\n"
                f"🏗️ Объект: {material[1]}\n"
                f"📊 Количество: {material[2]} {material[3]}\n"
                f"💰 Цена: {material[4]:,.2f} руб.\n",
                parse_mode='Markdown',
                reply_markup=confirmation_keyboard('material', item_id)
            )
        elif item_type == 'salary':
            conn = sqlite3.connect(DB_PATH)
            salary = conn.execute("""
                SELECT s.description, p.name, s.amount 
                FROM salaries s 
                JOIN projects p ON s.project_id = p.id 
                WHERE s.id = ?
            """, (item_id,)).fetchone()
            conn.close()
            
            await query.edit_message_text(
                f"🗑️ *Удаление зарплаты*\n\n"
                f"Вы уверены, что хотите удалить запись:\n"
                f"*{salary[0]}*\n"
                f"🏗️ Объект: {salary[1]}\n"
                f"💰 Сумма: {salary[2]:,.2f} руб.\n",
                parse_mode='Markdown',
                reply_markup=confirmation_keyboard('salary', item_id)
            )
    
    elif action == 'edit':
        context.user_data[f'editing_{item_type}'] = item_id
        context.user_data['awaiting_input'] = f'edit_{item_type}'
        
        if item_type == 'project':
            conn = sqlite3.connect(DB_PATH)
            project = conn.execute("SELECT name FROM projects WHERE id = ?", (item_id,)).fetchone()
            conn.close()
            
            await query.edit_message_text(
                f"✏️ *Редактирование объекта*\n\n"
                f"Текущее название: *{project[0]}*\n\n"
                f"Введите новое название объекта:",
                parse_mode='Markdown',
                reply_markup=back_button('edit_projects')
            )

# Обработка подтверждений
async def handle_confirmation(query, context):
    data_parts = query.data.split('_')
    action = data_parts[0]  # confirm, cancel
    item_type = data_parts[1]  # project, material, salary
    item_id = data_parts[2]
    
    if action == 'cancel':
        if item_type == 'project':
            await edit_projects_handler(query, context)
        elif item_type == 'material':
            await delete_materials_handler(query, context)
        elif item_type == 'salary':
            await delete_salaries_handler(query, context)
        return
    
    # Подтвержденное удаление
    if action == 'confirm':
        conn = sqlite3.connect(DB_PATH)
        
        if item_type == 'project':
            project_name = conn.execute("SELECT name FROM projects WHERE id = ?", (item_id,)).fetchone()[0]
            conn.execute("DELETE FROM materials WHERE project_id = ?", (item_id,))
            conn.execute("DELETE FROM salaries WHERE project_id = ?", (item_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ Объект *{project_name}* и все связанные данные успешно удалены!",
                parse_mode='Markdown',
                reply_markup=back_button('settings_menu')
            )
        
        elif item_type == 'material':
            material_name = conn.execute("SELECT name FROM materials WHERE id = ?", (item_id,)).fetchone()[0]
            conn.execute("DELETE FROM materials WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ Материал *{material_name}* успешно удален!",
                parse_mode='Markdown',
                reply_markup=back_button('materials_menu')
            )
        
        elif item_type == 'salary':
            salary_desc = conn.execute("SELECT description FROM salaries WHERE id = ?", (item_id,)).fetchone()[0]
            conn.execute("DELETE FROM salaries WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ Запись о зарплате *{salary_desc}* успешно удалена!",
                parse_mode='Markdown',
                reply_markup=back_button('salaries_menu')
            )

# Обработка кнопки "Назад"
async def handle_back_button(query, context, user_id):
    target = query.data.replace('back_to_', '')
    
    if target == 'main':
        await show_main_menu(query)
    elif target == 'materials':
        await show_materials_menu(query)
    elif target == 'salaries':
        await show_salaries_menu(query)
    elif target == 'reports':
        await show_reports_menu(query)
    elif target == 'settings':
        await show_settings_menu(query, user_id)
    elif target == 'add_material':
        await add_material_handler(query, context)
    elif target == 'add_salary':
        await add_salary_handler(query, context)
    elif target == 'project_stats':
        await project_stats_handler(query, context)
    elif target == 'material_name':
        context.user_data.clear()
        await add_material_handler(query, context)
    elif target == 'admin_management':
        await show_admin_management(query)
    elif target == 'list_materials':
        await list_materials_handler(query)
    elif target == 'list_salaries':
        await list_salaries_handler(query)

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = update.message.text
    user_id = update.effective_user.id
    
    if 'awaiting_input' not in user_data:
        await update.message.reply_text(
            "🏢 *ООО ИКС \"ГЕОСТРОЙ\"*\n\nИспользуйте меню для навигации:",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        return
    
    state = user_data['awaiting_input']
    
    if state == 'project_name':
        await handle_project_name(update, context, text)
    elif state == 'material_name':
        await handle_material_name(update, context, text)
    elif state == 'material_quantity':
        await handle_material_quantity(update, context, text)
    elif state == 'material_price':
        await handle_material_price(update, context, text)
    elif state == 'salary_description':
        await handle_salary_description(update, context, text)
    elif state == 'salary_amount':
        await handle_salary_amount(update, context, text)
    elif state == 'admin_user_id':
        await handle_admin_user_id(update, context, text)
    elif state == 'edit_project':
        await handle_edit_project(update, context, text)

async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO projects (name) VALUES (?)", (text,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Объект *{text}* успешно добавлен!",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Объект с таким названием уже существует!",
            reply_markup=back_button('add_project')
        )
    
    context.user_data.clear()

async def handle_edit_project(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    project_id = context.user_data.get('editing_project')
    
    try:
        conn = sqlite3.connect(DB_PATH)
        old_name = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (text, project_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Объект успешно обновлен!\n\n"
            f"📝 Старое название: *{old_name}*\n"
            f"📝 Новое название: *{text}*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Объект с таким названием уже существует!",
            reply_markup=back_button('edit_projects')
        )
    
    context.user_data.clear()

async def handle_admin_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        user_id = int(text)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Пользователь с ID `{user_id}` добавлен как администратор!",
            parse_mode='Markdown',
            reply_markup=back_button('admin_management')
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректный ID пользователя (число):",
            reply_markup=back_button('admin_management')
        )
    
    context.user_data.clear()

# Пошаговый ввод материалов
async def handle_material_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['material_name'] = text
    context.user_data['awaiting_input'] = 'material_unit'
    
    await update.message.reply_text(
        f"📦 *Добавление материала для объекта: {context.user_data['selected_project_name']}*\n\n"
        "📊 *Шаг 2 из 3:* Выберите единицу измерения:",
        parse_mode='Markdown',
        reply_markup=units_keyboard()
    )

async def handle_material_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        quantity = float(text.replace(',', '.'))
        context.user_data['material_quantity'] = quantity
        context.user_data['awaiting_input'] = 'material_price'
        
        await update.message.reply_text(
            f"📦 *Добавление материала для объекта: {context.user_data['selected_project_name']}*\n\n"
            f"💰 *Шаг 3 из 3:* Введите цену за {context.user_data['selected_unit']} (в рублях):",
            parse_mode='Markdown',
            reply_markup=back_button('material_quantity')
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное число для количества:",
            reply_markup=back_button('material_name')
        )

async def handle_material_price(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        price = float(text.replace(',', '.'))
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO materials (project_id, name, quantity, unit, unit_price) VALUES (?, ?, ?, ?, ?)",
            (context.user_data['selected_project'], 
             context.user_data['material_name'],
             context.user_data['material_quantity'],
             context.user_data['selected_unit'],
             price)
        )
        conn.commit()
        conn.close()
        
        total_cost = context.user_data['material_quantity'] * price
        project_name = context.user_data['selected_project_name']
        
        await update.message.reply_text(
            f"✅ Материал успешно добавлен!\n\n"
            f"🏗️ Объект: *{project_name}*\n"
            f"📦 Материал: *{context.user_data['material_name']}*\n"
            f"📊 Количество: *{context.user_data['material_quantity']} {context.user_data['selected_unit']}*\n"
            f"💰 Цена за единицу: *{price:,.2f} руб.*\n"
            f"🧮 Итого: *{total_cost:,.2f} руб.*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректную цену:",
            reply_markup=back_button('material_quantity')
        )
    
    context.user_data.clear()

# Пошаговый ввод зарплат
async def handle_salary_description(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_description'] = text
    context.user_data['awaiting_input'] = 'salary_amount'
    
    await update.message.reply_text(
        f"💰 *Добавление зарплаты для объекта: {context.user_data['selected_project_name']}*\n\n"
        "💵 *Шаг 2 из 2:* Введите сумму в рублях:",
        parse_mode='Markdown',
        reply_markup=back_button('add_salary')
    )

async def handle_salary_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        amount = float(text.replace(',', '.'))
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO salaries (project_id, description, amount) VALUES (?, ?, ?)",
            (context.user_data['selected_project'], context.user_data['salary_description'], amount)
        )
        conn.commit()
        conn.close()
        
        project_name = context.user_data['selected_project_name']
        
        await update.message.reply_text(
            f"✅ Зарплата успешно добавлена!\n\n"
            f"🏗️ Объект: *{project_name}*\n"
            f"📝 Описание работы: *{context.user_data['salary_description']}*\n"
            f"💰 Сумма: *{amount:,.2f} руб.*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректную сумму:",
            reply_markup=back_button('salary_description')
        )
    
    context.user_data.clear()

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
    
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
