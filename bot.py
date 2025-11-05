import sqlite3
import pandas as pd
import gspread
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv
import re

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен из переменных окружения
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
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def salaries_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💵 Добавить зарплату", callback_data='add_salary')],
        [InlineKeyboardButton("📋 Список зарплат", callback_data='list_salaries')],
        [InlineKeyboardButton("🔍 Поиск по зарплатам", callback_data='search_salaries')],
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
        [InlineKeyboardButton("🔄 Очистить данные", callback_data='clear_data')],
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

def back_button(target_menu):
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data=target_menu)]]
    return InlineKeyboardMarkup(keyboard)

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
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
        await show_settings_menu(query)
    
    # Проекты
    elif query.data == 'add_project':
        await add_project_handler(query, context)
    elif query.data == 'list_projects':
        await list_projects_handler(query)
    
    # Материалы
    elif query.data == 'add_material':
        await add_material_handler(query, context)
    elif query.data == 'list_materials':
        await list_materials_handler(query)
    elif query.data == 'search_materials':
        await search_materials_handler(query, context)
    
    # Зарплаты
    elif query.data == 'add_salary':
        await add_salary_handler(query, context)
    elif query.data == 'list_salaries':
        await list_salaries_handler(query)
    elif query.data == 'search_salaries':
        await search_salaries_handler(query, context)
    
    # Отчеты
    elif query.data == 'overall_stats':
        await overall_stats_handler(query)
    elif query.data == 'project_stats':
        await project_stats_handler(query, context)
    elif query.data == 'detailed_report':
        await detailed_report_handler(query, context)
    elif query.data == 'export_excel':
        await export_excel_handler(query)
    elif query.data == 'sync_gs':
        await sync_gs_handler(query)
    
    # Настройки
    elif query.data == 'clear_data':
        await clear_data_handler(query, context)
    
    # Обработка выбора проекта
    elif query.data.startswith(('material_project_', 'salary_project_', 'stats_project_', 'report_project_')):
        await handle_project_selection(query, context)
    
    # Назад
    elif query.data.startswith('back_to_'):
        await handle_back_button(query, context)

# Меню
async def show_main_menu(query):
    await query.edit_message_text(
        "🏠 *Главное меню* - выберите действие:",
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

async def show_settings_menu(query):
    await query.edit_message_text(
        "⚙️ *Настройки* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=settings_menu_keyboard()
    )

# Обработчики проектов
async def add_project_handler(query, context):
    context.user_data['awaiting_input'] = 'project_name'
    context.user_data['last_menu'] = 'main_menu'
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
    
    context.user_data['last_menu'] = 'materials_menu'
    await query.edit_message_text(
        "📦 *Добавление материала*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('material')
    )

async def list_materials_handler(query):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.name, m.quantity, m.unit_price, p.name, m.date_added
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
        total_cost = material[1] * material[2]
        materials_text += f"{i}. *{material[0]}*\n"
        materials_text += f"   🏗️ Объект: {material[3]}\n"
        materials_text += f"   📊 Количество: {material[1]}\n"
        materials_text += f"   💰 Цена: {material[2]:,.2f} руб.\n"
        materials_text += f"   🧮 Стоимость: {total_cost:,.2f} руб.\n"
        materials_text += f"   📅 Дата: {material[4][:10]}\n\n"
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )

async def search_materials_handler(query, context):
    context.user_data['awaiting_input'] = 'search_materials'
    context.user_data['last_menu'] = 'materials_menu'
    await query.edit_message_text(
        "🔍 *Поиск материалов*\n\nВведите название материала для поиска:",
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
            "❌ Сначала добавьте строительный объект!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    context.user_data['last_menu'] = 'salaries_menu'
    await query.edit_message_text(
        "💰 *Добавление зарплаты*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('salary')
    )

async def list_salaries_handler(query):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.description, s.amount, p.name, s.date_added
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
        salaries_text += f"{i}. *{salary[0]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[2]}\n"
        salaries_text += f"   💰 Сумма: {salary[1]:,.2f} руб.\n"
        salaries_text += f"   📅 Дата: {salary[3][:10]}\n\n"
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

async def search_salaries_handler(query, context):
    context.user_data['awaiting_input'] = 'search_salaries'
    context.user_data['last_menu'] = 'salaries_menu'
    await query.edit_message_text(
        "🔍 *Поиск по зарплатам*\n\nВведите описание работы для поиска:",
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

# Обработчики отчетов
async def overall_stats_handler(query):
    conn = sqlite3.connect(DB_PATH)
    
    # Общая статистика
    total_stats = conn.execute("""
        SELECT COUNT(*) as project_count,
               COALESCE(SUM(m.quantity * m.unit_price), 0) as total_materials,
               COALESCE(SUM(s.amount), 0) as total_salaries
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
    """).fetchone()
    
    # Статистика по проектам
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
    
    stats_text = "📈 *Общая статистика*\n\n"
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
    
    context.user_data['last_menu'] = 'reports_menu'
    await query.edit_message_text(
        "📊 *Статистика по объекту*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('stats')
    )

async def detailed_report_handler(query, context):
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Нет объектов для создания отчета!",
            reply_markup=back_button('reports_menu')
        )
        return
    
    context.user_data['last_menu'] = 'reports_menu'
    await query.edit_message_text(
        "📋 *Детальный отчет*\n\nВыберите объект для детального отчета:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('report')
    )

async def export_excel_handler(query):
    try:
        conn = sqlite3.connect(DB_PATH)
        
        with pd.ExcelWriter('construction_report.xlsx', engine='openpyxl') as writer:
            # Проекты
            projects_df = pd.read_sql("SELECT * FROM projects", conn)
            projects_df.to_excel(writer, sheet_name='Проекты', index=False)
            
            # Материалы
            materials_df = pd.read_sql("""
                SELECT p.name as project_name, m.name, m.quantity, m.unit_price, 
                       m.quantity * m.unit_price as total_cost, m.date_added
                FROM materials m
                JOIN projects p ON m.project_id = p.id
            """, conn)
            materials_df.to_excel(writer, sheet_name='Материалы', index=False)
            
            # Зарплаты
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
        
        # Синхронизация проектов
        projects_ws = sh.worksheet('Projects')
        projects_data = conn.execute("SELECT * FROM projects").fetchall()
        projects_ws.clear()
        if projects_data:
            headers = [desc[0] for desc in conn.execute("SELECT * FROM projects").description]
            projects_ws.update([headers] + projects_data)
        
        # Синхронизация материалов
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

# Обработчики настроек
async def clear_data_handler(query, context):
    keyboard = [
        [InlineKeyboardButton("🗑️ Да, очистить все", callback_data='confirm_clear')],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data='settings_menu')]
    ]
    await query.edit_message_text(
        "⚠️ *Очистка всех данных*\n\nВы уверены, что хотите удалить ВСЕ данные? Это действие нельзя отменить!",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработка выбора проекта
async def handle_project_selection(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # material, salary, stats, report
    project_id = data_parts[2]
    
    conn = sqlite3.connect(DB_PATH)
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    context.user_data['selected_project'] = project_id
    context.user_data['selected_project_name'] = project[0]
    
    if action_type == 'material':
        context.user_data['awaiting_input'] = 'material_data'
        context.user_data['last_menu'] = 'add_material'
        await query.edit_message_text(
            f"📦 *Добавление материала для объекта: {project[0]}*\n\n"
            "Введите данные в произвольной форме:\n"
            "• Название материала\n" 
            "• Количество\n"
            "• Цена за единицу\n\n"
            "*Примеры:*\n"
            "`Кирпич красный 1000 25.50`\n"
            "`Цемент 50 мешков по 450`\n"
            "`Песок 5 тонн 1200`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
    
    elif action_type == 'salary':
        context.user_data['awaiting_input'] = 'salary_data'
        context.user_data['last_menu'] = 'add_salary'
        await query.edit_message_text(
            f"💰 *Добавление зарплаты для объекта: {project[0]}*\n\n"
            "Введите данные в произвольной форме:\n"
            "• Описание работы\n"
            "• Сумма\n\n"
            "*Примеры:*\n"
            "`Кладка кирпича 25000`\n"
            "`Зарплата прорабу 50000 рублей`\n"
            "`Отделочные работы 35000.50`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    
    elif action_type == 'stats':
        await show_project_stats(query, project_id, project[0])
    
    elif action_type == 'report':
        await show_detailed_report(query, project_id, project[0])

async def show_project_stats(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    
    # Статистика проекта
    project_stats = conn.execute("""
        SELECT COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    
    # Материалы проекта
    materials = conn.execute("""
        SELECT name, quantity, unit_price, quantity * unit_price as total
        FROM materials 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    # Зарплаты проекта
    salaries = conn.execute("""
        SELECT description, amount, date_added
        FROM salaries 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    conn.close()
    
    total_cost = project_stats[0] + project_stats[1]
    
    stats_text = f"📊 *Статистика объекта: {project_name}*\n\n"
    stats_text += f"📦 Затраты на материалы: *{project_stats[0]:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{project_stats[1]:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    if materials:
        stats_text += "📦 *Материалы:*\n"
        for material in materials:
            stats_text += f"• {material[0]}: {material[1]} × {material[2]:,.2f} = {material[3]:,.2f} руб.\n"
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

async def show_detailed_report(query, project_id, project_name):
    conn = sqlite3.connect(DB_PATH)
    
    # Общая статистика
    project_stats = conn.execute("""
        SELECT COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
               COALESCE(SUM(s.amount), 0) as salaries_cost,
               COUNT(DISTINCT m.id) as materials_count,
               COUNT(DISTINCT s.id) as salaries_count
        FROM projects p
        LEFT JOIN materials m ON p.id = m.project_id
        LEFT JOIN salaries s ON p.id = s.project_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    
    # Детальные материалы
    materials = conn.execute("""
        SELECT name, quantity, unit_price, quantity * unit_price as total, date_added
        FROM materials 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    # Детальные зарплаты
    salaries = conn.execute("""
        SELECT description, amount, date_added
        FROM salaries 
        WHERE project_id = ?
        ORDER BY date_added DESC
    """, (project_id,)).fetchall()
    
    conn.close()
    
    total_cost = project_stats[0] + project_stats[1]
    
    report_text = f"📋 *Детальный отчет: {project_name}*\n\n"
    report_text += f"📦 Материалы: {project_stats[0]:,.2f} руб. ({project_stats[2]} записей)\n"
    report_text += f"👷 Зарплаты: {project_stats[1]:,.2f} руб. ({project_stats[3]} записей)\n"
    report_text += f"💰 Всего затрат: {total_cost:,.2f} руб.\n\n"
    
    report_text += "📦 *Детали по материалам:*\n"
    if materials:
        for i, material in enumerate(materials, 1):
            report_text += f"{i}. {material[0]}\n"
            report_text += f"   Количество: {material[1]}\n"
            report_text += f"   Цена: {material[2]:,.2f} руб.\n"
            report_text += f"   Стоимость: {material[3]:,.2f} руб.\n"
            report_text += f"   Дата: {material[4][:10]}\n\n"
    else:
        report_text += "   Нет данных\n\n"
    
    report_text += "💰 *Детали по зарплатам:*\n"
    if salaries:
        for i, salary in enumerate(salaries, 1):
            report_text += f"{i}. {salary[0]}\n"
            report_text += f"   Сумма: {salary[1]:,.2f} руб.\n"
            report_text += f"   Дата: {salary[2][:10]}\n\n"
    else:
        report_text += "   Нет данных\n"
    
    await query.edit_message_text(
        report_text,
        parse_mode='Markdown',
        reply_markup=back_button('detailed_report')
    )

# Обработка кнопки "Назад"
async def handle_back_button(query, context):
    target = query.data.replace('back_to_', '')
    
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

# Функции для парсинга произвольного ввода
def parse_material_input(text):
    """Парсит произвольный ввод для материалов"""
    # Ищем числа в тексте
    numbers = re.findall(r'\d+[.,]?\d*', text)
    
    if len(numbers) < 2:
        return None, None, None
    
    # Извлекаем количество и цену
    quantity = float(numbers[0].replace(',', '.'))
    unit_price = float(numbers[1].replace(',', '.'))
    
    # Название - все что не числа
    name = re.sub(r'\d+[.,]?\d*', '', text).strip()
    
    return name, quantity, unit_price

def parse_salary_input(text):
    """Парсит произвольный ввод для зарплат"""
    # Ищем число (сумму)
    numbers = re.findall(r'\d+[.,]?\d*', text)
    
    if not numbers:
        return None, None
    
    amount = float(numbers[0].replace(',', '.'))
    
    # Описание - все что не последнее число
    description = text
    if numbers:
        # Убираем последнее число из описания
        last_num = numbers[-1]
        description = re.sub(r'\s*' + re.escape(last_num) + r'[.,]?\d*\s*$', '', text).strip()
    
    return description, amount

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    text = update.message.text
    
    if 'awaiting_input' not in user_data:
        await update.message.reply_text(
            "Используйте меню для навигации:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    state = user_data['awaiting_input']
    
    if state == 'project_name':
        await handle_project_name(update, context, text)
    elif state == 'material_data':
        await handle_material_data(update, context, text)
    elif state == 'salary_data':
        await handle_salary_data(update, context, text)
    elif state == 'search_materials':
        await handle_search_materials(update, context, text)
    elif state == 'search_salaries':
        await handle_search_salaries(update, context, text)

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

async def handle_material_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    name, quantity, price = parse_material_input(text)
    
    if name is None or quantity is None or price is None:
        await update.message.reply_text(
            "❌ Не удалось распознать данные! Убедитесь, что введены название, количество и цена.\n\n"
            "*Пример:* `Кирпич красный 1000 25.50`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO materials (project_id, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (context.user_data['selected_project'], name, quantity, price)
        )
        conn.commit()
        conn.close()
        
        total_cost = quantity * price
        project_name = context.user_data['selected_project_name']
        
        await update.message.reply_text(
            f"✅ Материал добавлен!\n\n"
            f"🏗️ Объект: *{project_name}*\n"
            f"📦 Материал: *{name}*\n"
            f"📊 Количество: *{quantity}*\n"
            f"💰 Цена: *{price:,.2f} руб.*\n"
            f"🧮 Итого: *{total_cost:,.2f} руб.*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Material error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении материала!",
            reply_markup=back_button('add_material')
        )
    
    context.user_data.clear()

async def handle_salary_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    description, amount = parse_salary_input(text)
    
    if description is None or amount is None:
        await update.message.reply_text(
            "❌ Не удалось распознать данные! Убедитесь, что введены описание и сумма.\n\n"
            "*Пример:* `Кладка кирпича 25000`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO salaries (project_id, description, amount) VALUES (?, ?, ?)",
            (context.user_data['selected_project'], description, amount)
        )
        conn.commit()
        conn.close()
        
        project_name = context.user_data['selected_project_name']
        
        await update.message.reply_text(
            f"✅ Зарплата добавлена!\n\n"
            f"🏗️ Объект: *{project_name}*\n"
            f"📝 Описание: *{description}*\n"
            f"💰 Сумма: *{amount:,.2f} руб.*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Salary error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении зарплаты!",
            reply_markup=back_button('add_salary')
        )
    
    context.user_data.clear()

async def handle_search_materials(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = sqlite3.connect(DB_PATH)
    materials = conn.execute("""
        SELECT m.name, m.quantity, m.unit_price, p.name, m.date_added
        FROM materials m
        JOIN projects p ON m.project_id = p.id
        WHERE m.name LIKE ?
        ORDER BY m.date_added DESC
        LIMIT 20
    """, (f'%{text}%',)).fetchall()
    conn.close()
    
    if not materials:
        await update.message.reply_text(
            f"🔍 *Результаты поиска материалов по запросу: '{text}'*\n\nНичего не найдено.",
            parse_mode='Markdown',
            reply_markup=back_button('materials_menu')
        )
        return
    
    materials_text = f"🔍 *Результаты поиска материалов по запросу: '{text}'*\n\n"
    for i, material in enumerate(materials, 1):
        total_cost = material[1] * material[2]
        materials_text += f"{i}. *{material[0]}*\n"
        materials_text += f"   🏗️ Объект: {material[3]}\n"
        materials_text += f"   📊 Количество: {material[1]}\n"
        materials_text += f"   💰 Цена: {material[2]:,.2f} руб.\n"
        materials_text += f"   🧮 Стоимость: {total_cost:,.2f} руб.\n"
        materials_text += f"   📅 Дата: {material[4][:10]}\n\n"
    
    await update.message.reply_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )
    
    context.user_data.clear()

async def handle_search_salaries(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = sqlite3.connect(DB_PATH)
    salaries = conn.execute("""
        SELECT s.description, s.amount, p.name, s.date_added
        FROM salaries s
        JOIN projects p ON s.project_id = p.id
        WHERE s.description LIKE ?
        ORDER BY s.date_added DESC
        LIMIT 20
    """, (f'%{text}%',)).fetchall()
    conn.close()
    
    if not salaries:
        await update.message.reply_text(
            f"🔍 *Результаты поиска зарплат по запросу: '{text}'*\n\nНичего не найдено.",
            parse_mode='Markdown',
            reply_markup=back_button('salaries_menu')
        )
        return
    
    salaries_text = f"🔍 *Результаты поиска зарплат по запросу: '{text}'*\n\n"
    for i, salary in enumerate(salaries, 1):
        salaries_text += f"{i}. *{salary[0]}*\n"
        salaries_text += f"   🏗️ Объект: {salary[2]}\n"
        salaries_text += f"   💰 Сумма: {salary[1]:,.2f} руб.\n"
        salaries_text += f"   📅 Дата: {salary[3][:10]}\n\n"
    
    await update.message.reply_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )
    
    context.user_data.clear()

# Основная функция
def main():
    # Проверяем наличие токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Завершение работы.")
        return
    
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
