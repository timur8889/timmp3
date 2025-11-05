import sqlite3
import pandas as pd
import gspread
import os
import re
import logging
import shutil
import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен из переменных окружения
DB_PATH = 'construction.db'
GC_CREDENTIALS = 'credentials.json'
GSHEET_NAME = 'Construction Tracker'
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]

# Проверка наличия токена
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Загрузка конфигурации
def load_config():
    """Загрузка конфигурации из YAML файла"""
    config_path = 'config.yaml'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    else:
        # Конфигурация по умолчанию
        default_config = {
            'bot': {
                'admin_ids': ADMIN_IDS,
                'backup': {
                    'enabled': True,
                    'keep_count': 10,
                    'directory': 'backups'
                },
                'features': {
                    'google_sheets': True,
                    'excel_export': True,
                    'pagination': True
                },
                'pagination': {
                    'materials_page_size': 10,
                    'salaries_page_size': 10,
                    'projects_page_size': 5
                }
            }
        }
        # Создаем файл конфигурации по умолчанию
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
        return default_config

CONFIG = load_config()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Контекстный менеджер для безопасной работы с БД
@contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасной работы с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise e
    finally:
        conn.close()

# Класс для управления состоянием пользователя
class UserState:
    """Класс для управления состоянием пользователя"""
    def __init__(self):
        self.states = {}
    
    def set_state(self, user_id, state, data=None):
        if user_id not in self.states:
            self.states[user_id] = {}
        self.states[user_id]['current_state'] = state
        if data:
            self.states[user_id]['data'] = data
    
    def get_state(self, user_id):
        return self.states.get(user_id, {}).get('current_state')
    
    def get_data(self, user_id):
        return self.states.get(user_id, {}).get('data', {})
    
    def clear_state(self, user_id):
        if user_id in self.states:
            del self.states[user_id]

# Класс для пагинации
class Paginator:
    """Класс для управления пагинацией"""
    def __init__(self, data, page_size=10):
        self.data = data
        self.page_size = page_size
        self.total_pages = (len(data) + page_size - 1) // page_size
    
    def get_page(self, page):
        if page < 1 or page > self.total_pages:
            return []
        start = (page - 1) * self.page_size
        end = start + self.page_size
        return self.data[start:end]

# Глобальный экземпляр состояния пользователя
user_state = UserState()

# Функции безопасности и прав доступа
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in CONFIG['bot']['admin_ids']

def backup_database():
    """Создание резервной копии БД"""
    if not CONFIG['bot']['backup']['enabled']:
        return None
    
    backup_dir = CONFIG['bot']['backup']['directory']
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/construction_backup_{timestamp}.db"
    
    try:
        shutil.copy2(DB_PATH, backup_file)
        logger.info(f"Backup created: {backup_file}")
        
        # Удаление старых backup'ов
        keep_count = CONFIG['bot']['backup']['keep_count']
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        for old_backup in backups[:-keep_count]:
            os.remove(os.path.join(backup_dir, old_backup))
            logger.info(f"Old backup deleted: {old_backup}")
        
        return backup_file
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return None

# Кэширование
@lru_cache(maxsize=128)
def get_project_stats_cached(project_id):
    """Кэшированное получение статистики проекта"""
    with get_db_connection() as conn:
        return conn.execute("""
            SELECT COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
                   COALESCE(SUM(s.amount), 0) as salaries_cost
            FROM projects p
            LEFT JOIN materials m ON p.id = m.project_id
            LEFT JOIN salaries s ON p.id = s.project_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()

def invalidate_project_cache(project_id=None):
    """Очистка кэша проекта"""
    get_project_stats_cached.cache_clear()

# Инициализация БД
def init_db():
    with get_db_connection() as conn:
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

# Функции валидации
def validate_material_input(text: str) -> tuple[bool, str, list]:
    """Валидация ввода материала"""
    try:
        parts = [x.strip() for x in text.split(';')]
        if len(parts) != 3:
            return False, "❌ Неверное количество параметров. Нужно: Название;Количество;Цена", []
        
        name, quantity_str, price_str = parts
        
        if not name:
            return False, "❌ Название материала не может быть пустым", []
        
        # Проверка числовых значений
        if not re.match(r'^\d*\.?\d+$', quantity_str):
            return False, "❌ Количество должно быть числом", []
        
        if not re.match(r'^\d*\.?\d+$', price_str):
            return False, "❌ Цена должна быть числом", []
        
        quantity = float(quantity_str)
        price = float(price_str)
        
        if quantity <= 0:
            return False, "❌ Количество должно быть положительным числом", []
        
        if price < 0:
            return False, "❌ Цена не может быть отрицательной", []
        
        return True, "✅ Данные корректны", [name, quantity, price]
        
    except Exception as e:
        return False, f"❌ Ошибка обработки данных: {str(e)}", []

def validate_salary_input(text: str) -> tuple[bool, str, list]:
    """Валидация ввода зарплаты"""
    try:
        parts = [x.strip() for x in text.split(';')]
        if len(parts) != 2:
            return False, "❌ Неверное количество параметров. Нужно: Описание;Сумма", []
        
        description, amount_str = parts
        
        if not description:
            return False, "❌ Описание работы не может быть пустым", []
        
        # Проверка числового значения
        if not re.match(r'^\d*\.?\d+$', amount_str):
            return False, "❌ Сумма должна быть числом", []
        
        amount = float(amount_str)
        
        if amount <= 0:
            return False, "❌ Сумма должна быть положительным числом", []
        
        return True, "✅ Данные корректны", [description, amount]
        
    except Exception as e:
        return False, f"❌ Ошибка обработки данных: {str(e)}", []

def validate_project_name(text: str) -> tuple[bool, str]:
    """Валидация названия проекта"""
    if not text or len(text.strip()) == 0:
        return False, "❌ Название проекта не может быть пустым"
    
    if len(text) > 100:
        return False, "❌ Название проекта слишком длинное (макс. 100 символов)"
    
    # Проверка на существующий проект
    with get_db_connection() as conn:
        existing = conn.execute("SELECT id FROM projects WHERE name = ?", (text,)).fetchone()
        if existing:
            return False, "❌ Проект с таким названием уже существует"
    
    return True, "✅ Название проекта корректно"

# Безопасное редактирование сообщений
async def safe_edit_message(query, text, **kwargs):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        try:
            await query.message.reply_text(text, **kwargs)
        except Exception as e2:
            logger.error(f"Error sending new message: {e2}")

# Глобальный обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Отправка сообщения пользователю
    if update and update.effective_message:
        error_text = "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=error_text
        )

# Клавиатуры с пагинацией
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
        [InlineKeyboardButton("📋 Список материалов", callback_data='list_materials_1')],
        [InlineKeyboardButton("🔍 Поиск материалов", callback_data='search_materials')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def salaries_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💵 Добавить зарплату", callback_data='add_salary')],
        [InlineKeyboardButton("📋 Список зарплат", callback_data='list_salaries_1')],
        [InlineKeyboardButton("🔍 Поиск по зарплатам", callback_data='search_salaries')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def reports_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📈 Общая статистика", callback_data='overall_stats')],
        [InlineKeyboardButton("📅 Месячный отчет", callback_data='monthly_report')],
        [InlineKeyboardButton("🏗️ Статистика по объекту", callback_data='project_stats')],
        [InlineKeyboardButton("📊 Детальный отчет", callback_data='detailed_report')],
        [InlineKeyboardButton("📤 Экспорт в Excel", callback_data='export_excel')],
        [InlineKeyboardButton("☁️ Синхронизация с Google Sheets", callback_data='sync_gs')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 Очистить данные", callback_data='clear_data')],
        [InlineKeyboardButton("📋 Список объектов", callback_data='list_projects_1')],
        [InlineKeyboardButton("💾 Создать резервную копию", callback_data='create_backup')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def projects_keyboard(action, page=1):
    with get_db_connection() as conn:
        projects = conn.execute("SELECT id, name FROM projects ORDER BY created_date DESC").fetchall()
    
    paginator = Paginator(projects, CONFIG['bot']['pagination']['projects_page_size'])
    page_projects = paginator.get_page(page)
    
    keyboard = []
    for project in page_projects:
        keyboard.append([InlineKeyboardButton(f"🏗️ {project['name']}", callback_data=f'{action}_project_{project["id"]}')])
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'{action}_projects_page_{page-1}'))
    if page < paginator.total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'{action}_projects_page_{page+1}'))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data=f'back_to_{action.split("_")[0]}')])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

def materials_list_keyboard(page=1, total_pages=1):
    """Клавиатура для пагинации материалов"""
    keyboard = []
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'materials_page_{page-1}'))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'materials_page_{page+1}'))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_materials')])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

def salaries_list_keyboard(page=1, total_pages=1):
    """Клавиатура для пагинации зарплат"""
    keyboard = []
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'salaries_page_{page-1}'))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'salaries_page_{page+1}'))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_salaries')])
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по использованию бота"""
    help_text = """
📖 *Справка по Construction Manager Bot*

*Основные команды:*
/start - Запуск бота и главное меню
/help - Эта справка
/stat - Краткая статистика

*Как использовать:*
1. 🏗️ Сначала создайте объект через "Добавить объект"
2. 📦 Добавляйте материалы в формате: `Название;Количество;Цена`
3. 💰 Добавляйте зарплаты в формате: `Описание работы;Сумма`
4. 📊 Просматривайте отчеты и экспортируйте данные

*Примеры ввода:*
Материалы: `Кирпич красный;1000;25.50`
Зарплаты: `Кладка кирпича за июнь;25000.00`

*Поддержка:*
Для вопросов и предложений обращайтесь к разработчику.
    """
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Краткая статистика через команду"""
    with get_db_connection() as conn:
        # Общая статистика
        total_stats = conn.execute("""
            SELECT COUNT(*) as project_count,
                   COALESCE(SUM(m.quantity * m.unit_price), 0) as total_materials,
                   COALESCE(SUM(s.amount), 0) as total_salaries
            FROM projects p
            LEFT JOIN materials m ON p.id = m.project_id
            LEFT JOIN salaries s ON p.id = s.project_id
        """).fetchone()
    
    total_cost = total_stats['total_materials'] + total_stats['total_salaries']
    
    stats_text = "📊 *Краткая статистика*\n\n"
    stats_text += f"🏗️ Всего объектов: *{total_stats['project_count']}*\n"
    stats_text += f"📦 Затраты на материалы: *{total_stats['total_materials']:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{total_stats['total_salaries']:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    stats_text += "Для детальной статистики используйте меню 📊"

    await update.message.reply_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

# Обработчик кнопок
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
    elif query.data.startswith('list_projects_'):
        await list_projects_handler(query)
    
    # Материалы
    elif query.data == 'add_material':
        await add_material_handler(query, context)
    elif query.data.startswith('list_materials_'):
        await list_materials_handler(query)
    elif query.data.startswith('materials_page_'):
        await list_materials_handler(query)
    
    # Зарплаты
    elif query.data == 'add_salary':
        await add_salary_handler(query, context)
    elif query.data.startswith('list_salaries_'):
        await list_salaries_handler(query)
    elif query.data.startswith('salaries_page_'):
        await list_salaries_handler(query)
    
    # Отчеты
    elif query.data == 'overall_stats':
        await overall_stats_handler(query)
    elif query.data == 'monthly_report':
        await monthly_report_handler(query)
    elif query.data == 'project_stats':
        await project_stats_handler(query, context)
    elif query.data == 'detailed_report':
        await detailed_report_handler(query)
    elif query.data == 'export_excel':
        await export_excel_handler(query)
    elif query.data == 'sync_gs':
        await sync_gs_handler(query)
    
    # Настройки
    elif query.data == 'clear_data':
        await clear_data_handler(query)
    elif query.data == 'create_backup':
        await create_backup_handler(query)
    
    # Обработка выбора проекта
    elif query.data.startswith(('material_project_', 'salary_project_', 'stats_project_')):
        await handle_project_selection(query, context)
    
    # Пагинация проектов
    elif query.data.endswith('_projects_page_'):
        await handle_projects_pagination(query, context)
    
    # Назад
    elif query.data.startswith('back_to_'):
        await handle_back_button(query, context)

# Меню
async def show_main_menu(query):
    await safe_edit_message(
        query,
        "🏠 *Главное меню* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def show_materials_menu(query):
    await safe_edit_message(
        query,
        "📦 *Управление материалами* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=materials_menu_keyboard()
    )

async def show_salaries_menu(query):
    await safe_edit_message(
        query,
        "💰 *Управление зарплатами* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=salaries_menu_keyboard()
    )

async def show_reports_menu(query):
    await safe_edit_message(
        query,
        "📊 *Статистика и отчеты* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=reports_menu_keyboard()
    )

async def show_settings_menu(query):
    await safe_edit_message(
        query,
        "⚙️ *Настройки* - выберите действие:",
        parse_mode='Markdown',
        reply_markup=settings_menu_keyboard()
    )

# Обработчики проектов
async def add_project_handler(query, context):
    user_id = query.from_user.id
    user_state.set_state(user_id, 'project_name')
    await safe_edit_message(
        query,
        "🏗️ *Добавление нового объекта*\n\nВведите название строительного объекта:",
        parse_mode='Markdown',
        reply_markup=back_button('main_menu')
    )

async def list_projects_handler(query):
    page = int(query.data.split('_')[-1]) if query.data.startswith('list_projects_') else 1
    
    with get_db_connection() as conn:
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
    
    if not projects:
        await safe_edit_message(
            query,
            "📋 *Список объектов*\n\nПока нет добавленных объектов.",
            parse_mode='Markdown',
            reply_markup=back_button('settings_menu')
        )
        return
    
    paginator = Paginator(projects, CONFIG['bot']['pagination']['projects_page_size'])
    page_projects = paginator.get_page(page)
    
    projects_text = f"📋 *Список объектов* (Страница {page}/{paginator.total_pages})\n\n"
    for i, project in enumerate(page_projects, 1):
        total_cost = project['materials_cost'] + project['salaries_cost']
        projects_text += f"{i}. *{project['name']}*\n"
        projects_text += f"   📅 Создан: {project['created_date'][:10]}\n"
        projects_text += f"   💰 Общая стоимость: {total_cost:,.2f} руб.\n"
        projects_text += f"   📦 Материалы: {project['materials_cost']:,.2f} руб.\n"
        projects_text += f"   👷 Зарплаты: {project['salaries_cost']:,.2f} руб.\n\n"
    
    await safe_edit_message(
        query,
        projects_text,
        parse_mode='Markdown',
        reply_markup=projects_list_keyboard(page, paginator.total_pages)
    )

def projects_list_keyboard(page, total_pages):
    """Клавиатура для пагинации проектов"""
    keyboard = []
    
    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'list_projects_{page-1}'))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'list_projects_{page+1}'))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='back_to_settings')])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    return InlineKeyboardMarkup(keyboard)

# Обработчики материалов
async def add_material_handler(query, context):
    with get_db_connection() as conn:
        projects = conn.execute("SELECT id, name FROM projects").fetchall()
    
    if not projects:
        await safe_edit_message(
            query,
            "❌ Сначала добавьте строительный объект!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    await safe_edit_message(
        query,
        "📦 *Добавление материала*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('material', 1)
    )

async def list_materials_handler(query):
    page = 1
    if query.data.startswith('list_materials_'):
        page = int(query.data.split('_')[-1])
    elif query.data.startswith('materials_page_'):
        page = int(query.data.split('_')[-1])
    
    with get_db_connection() as conn:
        materials = conn.execute("""
            SELECT m.name, m.quantity, m.unit_price, p.name as project_name, m.date_added
            FROM materials m
            JOIN projects p ON m.project_id = p.id
            ORDER BY m.date_added DESC
        """).fetchall()
    
    if not materials:
        await safe_edit_message(
            query,
            "📦 *Список материалов*\n\nПока нет добавленных материалов.",
            parse_mode='Markdown',
            reply_markup=back_button('materials_menu')
        )
        return
    
    paginator = Paginator(materials, CONFIG['bot']['pagination']['materials_page_size'])
    page_materials = paginator.get_page(page)
    
    materials_text = f"📦 *Список материалов* (Страница {page}/{paginator.total_pages})\n\n"
    for i, material in enumerate(page_materials, 1):
        total_cost = material['quantity'] * material['unit_price']
        materials_text += f"{i}. *{material['name']}*\n"
        materials_text += f"   🏗️ Объект: {material['project_name']}\n"
        materials_text += f"   📊 Количество: {material['quantity']}\n"
        materials_text += f"   💰 Цена: {material['unit_price']:,.2f} руб.\n"
        materials_text += f"   🧮 Стоимость: {total_cost:,.2f} руб.\n"
        materials_text += f"   📅 Дата: {material['date_added'][:10]}\n\n"
    
    await safe_edit_message(
        query,
        materials_text,
        parse_mode='Markdown',
        reply_markup=materials_list_keyboard(page, paginator.total_pages)
    )

# Обработчики зарплат
async def add_salary_handler(query, context):
    with get_db_connection() as conn:
        projects = conn.execute("SELECT id, name FROM projects").fetchall()
    
    if not projects:
        await safe_edit_message(
            query,
            "❌ Сначала добавьте строительный объект!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    await safe_edit_message(
        query,
        "💰 *Добавление зарплаты*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('salary', 1)
    )

async def list_salaries_handler(query):
    page = 1
    if query.data.startswith('list_salaries_'):
        page = int(query.data.split('_')[-1])
    elif query.data.startswith('salaries_page_'):
        page = int(query.data.split('_')[-1])
    
    with get_db_connection() as conn:
        salaries = conn.execute("""
            SELECT s.description, s.amount, p.name as project_name, s.date_added
            FROM salaries s
            JOIN projects p ON s.project_id = p.id
            ORDER BY s.date_added DESC
        """).fetchall()
    
    if not salaries:
        await safe_edit_message(
            query,
            "💰 *Список зарплат*\n\nПока нет добавленных зарплат.",
            parse_mode='Markdown',
            reply_markup=back_button('salaries_menu')
        )
        return
    
    paginator = Paginator(salaries, CONFIG['bot']['pagination']['salaries_page_size'])
    page_salaries = paginator.get_page(page)
    
    salaries_text = f"💰 *Список зарплат* (Страница {page}/{paginator.total_pages})\n\n"
    for i, salary in enumerate(page_salaries, 1):
        salaries_text += f"{i}. *{salary['description']}*\n"
        salaries_text += f"   🏗️ Объект: {salary['project_name']}\n"
        salaries_text += f"   💰 Сумма: {salary['amount']:,.2f} руб.\n"
        salaries_text += f"   📅 Дата: {salary['date_added'][:10]}\n\n"
    
    await safe_edit_message(
        query,
        salaries_text,
        parse_mode='Markdown',
        reply_markup=salaries_list_keyboard(page, paginator.total_pages)
    )

# Обработчики отчетов
async def overall_stats_handler(query):
    with get_db_connection() as conn:
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
    
    total_cost = total_stats['total_materials'] + total_stats['total_salaries']
    
    stats_text = "📈 *Общая статистика*\n\n"
    stats_text += f"🏗️ Всего объектов: *{total_stats['project_count']}*\n"
    stats_text += f"📦 Затраты на материалы: *{total_stats['total_materials']:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{total_stats['total_salaries']:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    stats_text += "📊 *Статистика по объектам:*\n"
    for project in projects_stats:
        project_total = project['materials_cost'] + project['salaries_cost']
        stats_text += f"\n🏗️ *{project['name']}*\n"
        stats_text += f"   📦 Материалы: {project['materials_cost']:,.2f} руб.\n"
        stats_text += f"   👷 Зарплаты: {project['salaries_cost']:,.2f} руб.\n"
        stats_text += f"   💰 Всего: {project_total:,.2f} руб.\n"
    
    await safe_edit_message(
        query,
        stats_text,
        parse_mode='Markdown',
        reply_markup=back_button('reports_menu')
    )

async def monthly_report_handler(query):
    """Обработчик месячного отчета"""
    now = datetime.now()
    
    with get_db_connection() as conn:
        monthly_stats = conn.execute("""
            SELECT 
                p.name as project_name,
                COALESCE(SUM(m.quantity * m.unit_price), 0) as materials_cost,
                COALESCE(SUM(s.amount), 0) as salaries_cost,
                COUNT(DISTINCT m.id) as materials_count,
                COUNT(DISTINCT s.id) as salaries_count
            FROM projects p
            LEFT JOIN materials m ON p.id = m.project_id 
                AND strftime('%m', m.date_added) = ? AND strftime('%Y', m.date_added) = ?
            LEFT JOIN salaries s ON p.id = s.project_id 
                AND strftime('%m', s.date_added) = ? AND strftime('%Y', s.date_added) = ?
            GROUP BY p.id
        """, (f"{now.month:02d}", str(now.year), f"{now.month:02d}", str(now.year))).fetchall()
    
    if not monthly_stats or all(stat['materials_cost'] == 0 and stat['salaries_cost'] == 0 for stat in monthly_stats):
        await safe_edit_message(
            query,
            f"❌ Нет данных за {now.month}/{now.year}",
            reply_markup=back_button('reports_menu')
        )
        return
    
    report_text = f"📊 *Отчет за {now.month}/{now.year}*\n\n"
    total_materials = 0
    total_salaries = 0
    
    for stat in monthly_stats:
        project_total = stat['materials_cost'] + stat['salaries_cost']
        total_materials += stat['materials_cost']
        total_salaries += stat['salaries_cost']
        
        report_text += f"🏗️ *{stat['project_name']}*\n"
        report_text += f"   📦 Материалы: {stat['materials_cost']:,.2f} руб. ({stat['materials_count']} записей)\n"
        report_text += f"   👷 Зарплаты: {stat['salaries_cost']:,.2f} руб. ({stat['salaries_count']} записей)\n"
        report_text += f"   💰 Всего: {project_total:,.2f} руб.\n\n"
    
    report_text += f"*Итого за месяц:*\n"
    report_text += f"📦 Материалы: {total_materials:,.2f} руб.\n"
    report_text += f"👷 Зарплаты: {total_salaries:,.2f} руб.\n"
    report_text += f"💰 Общие затраты: {total_materials + total_salaries:,.2f} руб.\n"
    
    await safe_edit_message(
        query,
        report_text,
        parse_mode='Markdown',
        reply_markup=back_button('reports_menu')
    )

async def project_stats_handler(query, context):
    with get_db_connection() as conn:
        projects = conn.execute("SELECT id, name FROM projects").fetchall()
    
    if not projects:
        await safe_edit_message(
            query,
            "❌ Нет объектов для отображения статистики!",
            reply_markup=back_button('reports_menu')
        )
        return
    
    await safe_edit_message(
        query,
        "📊 *Статистика по объекту*\n\nВыберите объект:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('stats', 1)
    )

async def detailed_report_handler(query):
    await safe_edit_message(
        query,
        "📋 *Детальный отчет*\n\nЭта функция в разработке...",
        parse_mode='Markdown',
        reply_markup=back_button('reports_menu')
    )

async def export_excel_handler(query):
    try:
        with get_db_connection() as conn:
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
        
        await query.message.reply_document(
            document=open('construction_report.xlsx', 'rb'),
            filename='construction_report.xlsx',
            caption="📤 *Файл успешно экспортирован!*",
            parse_mode='Markdown'
        )
        
        await safe_edit_message(
            query,
            "✅ Файл отправлен в чат!",
            reply_markup=back_button('reports_menu')
        )
        
        # Удаляем временный файл
        os.remove('construction_report.xlsx')
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        await safe_edit_message(
            query,
            "❌ Ошибка при экспорте!",
            reply_markup=back_button('reports_menu')
        )

async def sync_gs_handler(query):
    try:
        if not os.path.exists(GC_CREDENTIALS):
            await safe_edit_message(
                query,
                "❌ *Файл credentials.json не найден!*\n\n"
                "Для работы с Google Sheets:\n"
                "1. Создайте проект в Google Cloud Console\n"
                "2. Включите Google Sheets API\n"
                "3. Создайте сервисный аккаунт\n"
                "4. Скачайте credentials.json в папку с ботом",
                parse_mode='Markdown',
                reply_markup=back_button('reports_menu')
            )
            return
        
        gc = gspread.service_account(filename=GC_CREDENTIALS)
        
        try:
            sh = gc.open(GSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            # Создать новую таблицу если не существует
            sh = gc.create(GSHEET_NAME)
            
            # Настроить доступ
            sh.share(None, perm_type='anyone', role='writer')
            
            # Создать листы
            sh.add_worksheet(title="Projects", rows=100, cols=10)
            sh.add_worksheet(title="Materials", rows=1000, cols=10)
            sh.add_worksheet(title="Salaries", rows=1000, cols=10)
            
            # Удалить default лист
            try:
                default_sheet = sh.sheet1
                sh.del_worksheet(default_sheet)
            except:
                pass
        
        with get_db_connection() as conn:
            # Синхронизация проектов
            try:
                projects_ws = sh.worksheet('Projects')
            except:
                projects_ws = sh.add_worksheet(title='Projects', rows=100, cols=10)
                
            projects_data = conn.execute("SELECT * FROM projects").fetchall()
            projects_ws.clear()
            if projects_data:
                headers = [desc[0] for desc in conn.execute("SELECT * FROM projects").description]
                projects_ws.update([headers] + [list(row) for row in projects_data])
            
            # Синхронизация материалов
            try:
                materials_ws = sh.worksheet('Materials')
            except:
                materials_ws = sh.add_worksheet(title='Materials', rows=1000, cols=10)
                
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
                materials_ws.update([headers] + [list(row) for row in materials_data])
            
            # Синхронизация зарплат
            try:
                salaries_ws = sh.worksheet('Salaries')
            except:
                salaries_ws = sh.add_worksheet(title='Salaries', rows=1000, cols=10)
                
            salaries_data = conn.execute("""
                SELECT p.name as project_name, s.* 
                FROM salaries s 
                JOIN projects p ON s.project_id = p.id
            """).fetchall()
            salaries_ws.clear()
            if salaries_data:
                headers = [desc[0] for desc in conn.execute("""
                    SELECT p.name as project_name, s.* 
                    FROM salaries s 
                    JOIN projects p ON s.project_id = p.id
                """).description]
                salaries_ws.update([headers] + [list(row) for row in salaries_data])
        
        await safe_edit_message(
            query,
            "✅ *Данные синхронизированы с Google Sheets!*",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )
        
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        await safe_edit_message(
            query,
            "❌ *Ошибка Google Sheets API!*\n\n"
            "Проверьте:\n"
            "• Доступ к интернету\n"
            "• Квоты API\n"
            "• Настройки доступа к таблице",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )
    except Exception as e:
        logger.error(f"GSync error: {e}")
        await safe_edit_message(
            query,
            "❌ *Ошибка синхронизации! Проверьте настройки Google Sheets.*",
            parse_mode='Markdown',
            reply_markup=back_button('reports_menu')
        )

# Обработчики настроек
async def clear_data_handler(query):
    """Обработчик очистки данных"""
    if not is_admin(query.from_user.id):
        await query.answer("❌ Недостаточно прав! Эта функция доступна только администраторам.", show_alert=True)
        return
    
    # Создаем резервную копию перед очисткой
    backup_file = backup_database()
    
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM materials")
            conn.execute("DELETE FROM salaries")
            conn.execute("DELETE FROM projects")
        
        # Очищаем кэш
        invalidate_project_cache()
        
        message = "✅ Все данные успешно очищены!"
        if backup_file:
            message += f"\n📁 Создана резервная копия: {os.path.basename(backup_file)}"
        
        await safe_edit_message(
            query,
            message,
            reply_markup=back_button('settings_menu')
        )
        
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        await safe_edit_message(
            query,
            "❌ Ошибка при очистке данных!",
            reply_markup=back_button('settings_menu')
        )

async def create_backup_handler(query):
    """Обработчик создания резервной копии"""
    if not is_admin(query.from_user.id):
        await query.answer("❌ Недостаточно прав! Эта функция доступна только администраторам.", show_alert=True)
        return
    
    backup_file = backup_database()
    
    if backup_file:
        try:
            await query.message.reply_document(
                document=open(backup_file, 'rb'),
                filename=os.path.basename(backup_file),
                caption="💾 *Резервная копия базы данных*",
                parse_mode='Markdown'
            )
            
            await safe_edit_message(
                query,
                f"✅ Резервная копия создана и отправлена в чат!\n\nФайл: `{os.path.basename(backup_file)}`",
                parse_mode='Markdown',
                reply_markup=back_button('settings_menu')
            )
        except Exception as e:
            logger.error(f"Error sending backup: {e}")
            await safe_edit_message(
                query,
                f"✅ Резервная копия создана, но возникла ошибка при отправке: {e}",
                reply_markup=back_button('settings_menu')
            )
    else:
        await safe_edit_message(
            query,
            "❌ Ошибка при создании резервной копии!",
            reply_markup=back_button('settings_menu')
        )

# Обработка выбора проекта
async def handle_project_selection(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # material, salary, stats
    project_id = data_parts[2]
    
    with get_db_connection() as conn:
        project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    
    user_id = query.from_user.id
    
    if action_type == 'material':
        user_state.set_state(user_id, 'material_data', {'project_id': project_id, 'project_name': project['name']})
        await safe_edit_message(
            query,
            f"📦 *Добавление материала для объекта: {project['name']}*\n\n"
            "Введите данные в формате:\n"
            "`Название материала;Количество;Цена за единицу`\n\n"
            "*Пример:*\n"
            "`Кирпич красный;1000;25.50`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )
    
    elif action_type == 'salary':
        user_state.set_state(user_id, 'salary_data', {'project_id': project_id, 'project_name': project['name']})
        await safe_edit_message(
            query,
            f"💰 *Добавление зарплаты для объекта: {project['name']}*\n\n"
            "Введите данные в формате:\n"
            "`Описание работы;Сумма`\n\n"
            "*Пример:*\n"
            "`Кладка кирпича;25000.00`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    
    elif action_type == 'stats':
        await show_project_stats(query, project_id, project['name'])

async def show_project_stats(query, project_id, project_name):
    # Используем кэшированную функцию
    project_stats = get_project_stats_cached(project_id)
    
    with get_db_connection() as conn:
        # Материалы проекта
        materials = conn.execute("""
            SELECT name, quantity, unit_price, quantity * unit_price as total
            FROM materials 
            WHERE project_id = ?
            ORDER BY date_added DESC
            LIMIT 10
        """, (project_id,)).fetchall()
        
        # Зарплаты проекта
        salaries = conn.execute("""
            SELECT description, amount, date_added
            FROM salaries 
            WHERE project_id = ?
            ORDER BY date_added DESC
            LIMIT 10
        """, (project_id,)).fetchall()
    
    total_cost = project_stats['materials_cost'] + project_stats['salaries_cost']
    
    stats_text = f"📊 *Статистика объекта: {project_name}*\n\n"
    stats_text += f"📦 Затраты на материалы: *{project_stats['materials_cost']:,.2f} руб.*\n"
    stats_text += f"👷 Затраты на зарплаты: *{project_stats['salaries_cost']:,.2f} руб.*\n"
    stats_text += f"💰 Общие затраты: *{total_cost:,.2f} руб.*\n\n"
    
    if materials:
        stats_text += "📦 *Последние материалы:*\n"
        for material in materials:
            stats_text += f"• {material['name']}: {material['quantity']} × {material['unit_price']:,.2f} = {material['total']:,.2f} руб.\n"
        stats_text += "\n"
    
    if salaries:
        stats_text += "💰 *Последние зарплаты:*\n"
        for salary in salaries:
            stats_text += f"• {salary['description']}: {salary['amount']:,.2f} руб. ({salary['date_added'][:10]})\n"
    
    await safe_edit_message(
        query,
        stats_text,
        parse_mode='Markdown',
        reply_markup=back_button('project_stats')
    )

# Обработка пагинации проектов
async def handle_projects_pagination(query, context):
    data_parts = query.data.split('_')
    action_type = data_parts[0]  # material, salary, stats
    page = int(data_parts[-1])
    
    await safe_edit_message(
        query,
        f"📦 *Добавление материала*\n\nВыберите объект (Страница {page}):",
        parse_mode='Markdown',
        reply_markup=projects_keyboard(action_type, page)
    )

# Обработка кнопки "Назад"
async def handle_back_button(query, context):
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
        await show_settings_menu(query)
    elif target == 'add_material':
        await add_material_handler(query, context)
    elif target == 'add_salary':
        await add_salary_handler(query, context)
    elif target == 'project_stats':
        await project_stats_handler(query, context)

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    current_state = user_state.get_state(user_id)
    
    if not current_state:
        await update.message.reply_text(
            "Используйте меню для навигации:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if current_state == 'project_name':
        await handle_project_name(update, context, text, user_id)
    elif current_state == 'material_data':
        await handle_material_data(update, context, text, user_id)
    elif current_state == 'salary_data':
        await handle_salary_data(update, context, text, user_id)

async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int):
    is_valid, message = validate_project_name(text)
    
    if not is_valid:
        await update.message.reply_text(
            message,
            reply_markup=back_button('add_project')
        )
        return
    
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO projects (name) VALUES (?)", (text,))
        
        # Очищаем кэш, так как добавили новый проект
        invalidate_project_cache()
        
        await update.message.reply_text(
            f"✅ Объект *{text}* успешно добавлен!",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error adding project: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении объекта!",
            reply_markup=back_button('add_project')
        )
    
    user_state.clear_state(user_id)

async def handle_material_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int):
    is_valid, message, data = validate_material_input(text)
    user_data = user_state.get_data(user_id)
    
    if not is_valid:
        await update.message.reply_text(
            message,
            reply_markup=back_button('add_material')
        )
        return
    
    try:
        name, quantity, price = data
        project_id = user_data['project_id']
        project_name = user_data['project_name']
        
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO materials (project_id, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (project_id, name, quantity, price)
            )
        
        # Очищаем кэш проекта
        invalidate_project_cache(project_id)
        
        total_cost = quantity * price
        
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
        logger.error(f"Error adding material: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении материала!",
            reply_markup=back_button('add_material')
        )
    
    user_state.clear_state(user_id)

async def handle_salary_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int):
    is_valid, message, data = validate_salary_input(text)
    user_data = user_state.get_data(user_id)
    
    if not is_valid:
        await update.message.reply_text(
            message,
            reply_markup=back_button('add_salary')
        )
        return
    
    try:
        description, amount = data
        project_id = user_data['project_id']
        project_name = user_data['project_name']
        
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO salaries (project_id, description, amount) VALUES (?, ?, ?)",
                (project_id, description, amount)
            )
        
        # Очищаем кэш проекта
        invalidate_project_cache(project_id)
        
        await update.message.reply_text(
            f"✅ Зарплата добавлена!\n\n"
            f"🏗️ Объект: *{project_name}*\n"
            f"📝 Описание: *{description}*\n"
            f"💰 Сумма: *{amount:,.2f} руб.*",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error adding salary: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении зарплаты!",
            reply_markup=back_button('add_salary')
        )
    
    user_state.clear_state(user_id)

# Основная функция
def main():
    """Основная функция с улучшенной обработкой ошибок"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Завершение работы.")
        return
    
    # Проверка существования файла credentials для Google Sheets
    if not os.path.exists(GC_CREDENTIALS):
        logger.warning(f"Файл {GC_CREDENTIALS} не найден. Синхронизация с Google Sheets будет недоступна.")
    
    try:
        # Инициализация базы данных
        init_db()
        
        # Создание приложения
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавление обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stat", stat_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # Добавление обработчика ошибок
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("Бот запущен...")
        application.run_polling(
            poll_interval=1.0,
            timeout=20,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}")
    finally:
        logger.info("Бот остановлен")

if __name__ == '__main__':
    main()
