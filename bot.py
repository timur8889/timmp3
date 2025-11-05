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

# Инициализация БД
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

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
def projects_keyboard(action_type):
    """Клавиатура для выбора проекта"""
    conn = sqlite3.connect(DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    keyboard = []
    for project_id, project_name in projects:
        keyboard.append([InlineKeyboardButton(project_name, callback_data=f'select_project_{action_type}_{project_id}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def back_button(target_menu):
    """Кнопка назад"""
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data=target_menu)]]
    return InlineKeyboardMarkup(keyboard)

# УЛУЧШЕННЫЕ КЛАВИАТУРЫ ДЛЯ ВВОДА ДАННЫХ
def material_input_keyboard(step, can_skip=False):
    keyboard = []
    if step == "name":
        keyboard.append([InlineKeyboardButton("📝 Ввести название", callback_data='input_material_name')])
    elif step == "quantity":
        keyboard.append([InlineKeyboardButton("🔢 Ввести количество", callback_data='input_material_quantity')])
        keyboard.append([InlineKeyboardButton("📏 Выбрать единицу измерения", callback_data='select_material_unit')])
    elif step == "price":
        keyboard.append([InlineKeyboardButton("💰 Ввести цену за единицу", callback_data='input_unit_price')])
        keyboard.append([InlineKeyboardButton("🧮 Ввести общую стоимость", callback_data='input_total_price')])
    
    if can_skip:
        keyboard.append([InlineKeyboardButton("⏭️ Пропустить", callback_data='skip_step')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    return InlineKeyboardMarkup(keyboard)

def salary_input_keyboard(step, can_skip=False):
    keyboard = []
    if step == "work_type":
        keyboard.append([InlineKeyboardButton("🔧 Ввести вид работ", callback_data='input_work_type')])
        keyboard.append([InlineKeyboardButton("🏗️ Выбрать из шаблонов", callback_data='select_work_template')])
    elif step == "description":
        keyboard.append([InlineKeyboardButton("📝 Ввести описание", callback_data='input_description')])
        keyboard.append([InlineKeyboardButton("📋 Использовать шаблон", callback_data='use_description_template')])
    elif step == "amount":
        keyboard.append([InlineKeyboardButton("💵 Ввести сумму", callback_data='input_amount')])
        keyboard.append([InlineKeyboardButton("💳 Рассчитать от часов", callback_data='calculate_from_hours')])
    elif step == "date":
        keyboard.append([InlineKeyboardButton("📅 Ввести дату", callback_data='input_date')])
        keyboard.append([InlineKeyboardButton("🕐 Сегодня", callback_data='use_today')])
        keyboard.append([InlineKeyboardButton("📅 Выбрать из календаря", callback_data='select_date_calendar')])
    
    if can_skip:
        keyboard.append([InlineKeyboardButton("⏭️ Пропустить", callback_data='skip_step')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    return InlineKeyboardMarkup(keyboard)

def work_type_templates_keyboard():
    keyboard = [
        [InlineKeyboardButton("🧱 Кладка кирпича", callback_data='template_brickwork')],
        [InlineKeyboardButton("🏗️ Монтаж конструкций", callback_data='template_installation')],
        [InlineKeyboardButton("🔨 Отделочные работы", callback_data='template_finishing')],
        [InlineKeyboardButton("👷 Зарплата прораба", callback_data='template_foreman')],
        [InlineKeyboardButton("🚛 Разгрузка материалов", callback_data='template_unloading')],
        [InlineKeyboardButton("📝 Свой вариант", callback_data='template_custom')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_salary_input')]
    ]
    return InlineKeyboardMarkup(keyboard)

def unit_selection_keyboard():
    keyboard = [
        [InlineKeyboardButton("шт", callback_data='unit_sh'), InlineKeyboardButton("кг", callback_data='unit_kg')],
        [InlineKeyboardButton("т", callback_data='unit_t'), InlineKeyboardButton("м³", callback_data='unit_m3')],
        [InlineKeyboardButton("м²", callback_data='unit_m2'), InlineKeyboardButton("м", callback_data='unit_m')],
        [InlineKeyboardButton("л", callback_data='unit_l'), InlineKeyboardButton("упак", callback_data='unit_pack')],
        [InlineKeyboardButton("рулон", callback_data='unit_roll'), InlineKeyboardButton("мешок", callback_data='unit_bag')],
        [InlineKeyboardButton("комплект", callback_data='unit_kit'), InlineKeyboardButton("банка", callback_data='unit_can')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_material_input')]
    ]
    return InlineKeyboardMarkup(keyboard)

def quick_calculator_keyboard():
    keyboard = [
        [InlineKeyboardButton("8 часов × ставка", callback_data='calc_8_hours')],
        [InlineKeyboardButton("10 часов × ставка", callback_data='calc_10_hours')],
        [InlineKeyboardButton("12 часов × ставка", callback_data='calc_12_hours')],
        [InlineKeyboardButton("Смена (24 часа)", callback_data='calc_24_hours')],
        [InlineKeyboardButton("Неделя (40 часов)", callback_data='calc_40_hours')],
        [InlineKeyboardButton("Месяц (168 часов)", callback_data='calc_168_hours')],
        [InlineKeyboardButton("📝 Ввести вручную", callback_data='calc_manual')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_salary_input')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ОСНОВНЫЕ КЛАВИАТУРЫ МЕНЮ
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

# ОБРАБОТЧИКИ КОМАНД
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "Добро пожаловать в систему учета строительных объектов!\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

# ОБРАБОТЧИКИ ПРОЕКТОВ
async def add_project_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление нового проекта"""
    context.user_data['awaiting_input'] = 'project_name'
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(
            "🏗️ *ДОБАВЛЕНИЕ НОВОГО ОБЪЕКТА*\n\nВведите название строительного объекта:",
            parse_mode='Markdown',
            reply_markup=back_button('main_menu')
        )
    else:
        await update.message.reply_text(
            "🏗️ *ДОБАВЛЕНИЕ НОВОГО ОБЪЕКТА*\n\nВведите название строительного объекта:",
            parse_mode='Markdown',
            reply_markup=back_button('main_menu')
        )

async def handle_project_selection(query, context, data):
    """Обработчик выбора проекта"""
    parts = data.split('_')
    action_type = parts[2]  # 'material' или 'salary'
    project_id = parts[3]
    
    conn = sqlite3.connect(DB_PATH)
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    if project:
        context.user_data['selected_project'] = project_id
        context.user_data['selected_project_name'] = project[0]
        
        if action_type == 'material':
            await start_material_input(query, context)
        elif action_type == 'salary':
            await start_salary_input(query, context)

# УЛУЧШЕННЫЕ ОБРАБОТЧИКИ МАТЕРИАЛОВ
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

async def start_material_input(query, context):
    project_id = context.user_data['selected_project']
    project_name = context.user_data['selected_project_name']
    
    # Инициализация данных материала
    context.user_data['material_data'] = {
        'project_id': project_id,
        'project_name': project_name,
        'step': 'name'
    }
    
    await query.edit_message_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"📦 *ДОБАВЛЕНИЕ МАТЕРИАЛА*\n\n"
        f"🏗️ Объект: *{project_name}*\n\n"
        "📝 *ШАГ 1 из 4: НАЗВАНИЕ МАТЕРИАЛА*\n\n"
        "Введите название материала или используйте кнопки ниже:",
        parse_mode='Markdown',
        reply_markup=material_input_keyboard('name')
    )

async def handle_material_name_input(query, context):
    context.user_data['awaiting_input'] = 'material_name'
    await query.edit_message_text(
        "📝 *ВВОД НАЗВАНИЯ МАТЕРИАЛА*\n\n"
        "Введите полное наименование материала:\n\n"
        "*ПРИМЕРЫ:*\n"
        "• `Кирпич красный полнотелый М-150`\n"
        "• `Цемент М500 Д0 мешок 50кг`\n"
        "• `Арматура А500С Ø12мм`\n"
        "• `Песок строительный мытый`",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_material_input')
    )

async def handle_material_quantity_input(query, context):
    context.user_data['awaiting_input'] = 'material_quantity'
    material_name = context.user_data['material_data'].get('name', 'материал')
    
    await query.edit_message_text(
        f"🔢 *ВВОД КОЛИЧЕСТВА*\n\n"
        f"Материал: *{material_name}*\n\n"
        "Введите количество цифрами:\n\n"
        "*ПРИМЕРЫ:*\n"
        "• `1000` (для штук)\n"
        "• `2.5` (для тонн, кубометров)\n"
        "• `50` (для мешков)\n"
        "• `150.75` (с десятичными)",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_material_input')
    )

async def handle_unit_selection(query, context):
    material_name = context.user_data['material_data'].get('name', 'материал')
    quantity = context.user_data['material_data'].get('quantity', 0)
    
    await query.edit_message_text(
        f"📏 *ВЫБОР ЕДИНИЦЫ ИЗМЕРЕНИЯ*\n\n"
        f"Материал: *{material_name}*\n"
        f"Количество: *{quantity}*\n\n"
        "Выберите единицу измерения:",
        parse_mode='Markdown',
        reply_markup=unit_selection_keyboard()
    )

async def handle_material_unit_selection(query, context, unit_data):
    unit_map = {
        'unit_sh': 'шт', 'unit_kg': 'кг', 'unit_t': 'т', 
        'unit_m3': 'м³', 'unit_m2': 'м²', 'unit_m': 'м',
        'unit_l': 'л', 'unit_pack': 'упак', 'unit_roll': 'рулон',
        'unit_bag': 'мешок', 'unit_kit': 'комплект', 'unit_can': 'банка'
    }
    
    if unit_data in unit_map:
        context.user_data['material_data']['unit'] = unit_map[unit_data]
        context.user_data['material_data']['step'] = 'price'
        
        await show_material_price_step(query, context)

async def show_material_price_step(query, context):
    material_data = context.user_data['material_data']
    
    text = (
        f"💰 *ШАГ 3 из 4: СТОИМОСТЬ*\n\n"
        f"📦 Материал: *{material_data['name']}*\n"
        f"🔢 Количество: *{material_data['quantity']} {material_data['unit']}*\n\n"
        f"Вы можете ввести:\n"
        f"• 💰 *Цену за единицу* - система рассчитает общую стоимость\n"
        f"• 🧮 *Общую стоимость* - система рассчитает цену за единицу\n\n"
        f"*ПРИМЕРЫ:*\n"
        f"• Цена за единицу: `28.50` (28.50 руб. за 1 {material_data['unit']})\n"
        f"• Общая стоимость: `42750` (42,750 руб. за всю партию)"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=material_input_keyboard('price')
    )

async def handle_unit_price_input(query, context):
    context.user_data['awaiting_input'] = 'material_unit_price'
    material_data = context.user_data['material_data']
    
    await query.edit_message_text(
        f"💰 *ВВОД ЦЕНЫ ЗА ЕДИНИЦУ*\n\n"
        f"Материал: *{material_data['name']}*\n"
        f"Количество: *{material_data['quantity']} {material_data['unit']}*\n\n"
        f"Введите цену за 1 {material_data['unit']}:\n\n"
        f"*ПРИМЕР:* `28.50` (28 рублей 50 копеек)",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_material_input')
    )

async def handle_total_price_input(query, context):
    context.user_data['awaiting_input'] = 'material_total_price'
    material_data = context.user_data['material_data']
    
    await query.edit_message_text(
        f"🧮 *ВВОД ОБЩЕЙ СТОИМОСТИ*\n\n"
        f"Материал: *{material_data['name']}*\n"
        f"Количество: *{material_data['quantity']} {material_data['unit']}*\n\n"
        f"Введите общую стоимость партии:\n\n"
        f"*ПРИМЕР:* `42750` (42,750 рублей)",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_material_input')
    )

async def save_material_data(update, context):
    material_data = context.user_data['material_data']
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO materials (project_id, name, quantity, unit, unit_price, total_price) VALUES (?, ?, ?, ?, ?, ?)",
            (material_data['project_id'], material_data['name'], material_data['quantity'], 
             material_data['unit'], material_data['unit_price'], material_data['total_price'])
        )
        conn.commit()
        conn.close()
        
        # Форматирование чисел с разделителями тысяч
        quantity_str = f"{material_data['quantity']:,.0f}".replace(',', ' ') if material_data['quantity'].is_integer() else f"{material_data['quantity']:,.2f}".replace(',', ' ')
        unit_price_str = f"{material_data['unit_price']:,.2f}".replace(',', ' ')
        total_price_str = f"{material_data['total_price']:,.2f}".replace(',', ' ')
        
        success_text = (
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *МАТЕРИАЛ УСПЕШНО ДОБАВЛЕН*\n\n"
            f"🏗️ *Объект:* {material_data['project_name']}\n"
            f"📦 *Материал:* {material_data['name']}\n"
            f"📊 *Количество:* {quantity_str} {material_data['unit']}\n"
            f"💰 *Цена за единицу:* {unit_price_str} руб.\n"
            f"🧮 *Общая стоимость:* {total_price_str} руб.\n\n"
            f"*📅 Дата оприходования:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        # Используем query для ответа в callback handler
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Material save error: {e}")
        error_text = "❌ Ошибка при сохранении материала! Обратитесь к системному администратору."
        
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                error_text,
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                error_text,
                reply_markup=main_menu_keyboard()
            )
    
    context.user_data.clear()

# УЛУЧШЕННЫЕ ОБРАБОТЧИКИ ЗАРПЛАТ
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

async def start_salary_input(query, context):
    project_id = context.user_data['selected_project']
    project_name = context.user_data['selected_project_name']
    
    # Инициализация данных зарплаты
    context.user_data['salary_data'] = {
        'project_id': project_id,
        'project_name': project_name,
        'step': 'work_type'
    }
    
    await query.edit_message_text(
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"💰 *ДОБАВЛЕНИЕ ЗАРПЛАТЫ*\n\n"
        f"🏗️ Объект: *{project_name}*\n\n"
        "🔧 *ШАГ 1 из 4: ВИД РАБОТ*\n\n"
        "Выберите вид работ или введите свой вариант:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('work_type')
    )

async def handle_work_type_input(query, context):
    context.user_data['awaiting_input'] = 'salary_work_type'
    await query.edit_message_text(
        "📝 *ВВОД ВИДА РАБОТ*\n\n"
        "Введите вид работ:\n\n"
        "*ПРИМЕРЫ:*\n"
        "• `Кладка кирпича 3 этаж`\n"
        "• `Зарплата прораба за ноябрь`\n"
        "• `Монтаж металлоконструкций`\n"
        "• `Штукатурные работы`",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_salary_input')
    )

async def handle_work_type_templates(query, context):
    await query.edit_message_text(
        "🏗️ *ШАБЛОНЫ ВИДОВ РАБОТ*\n\n"
        "Выберите подходящий вид работ или создайте свой:",
        parse_mode='Markdown',
        reply_markup=work_type_templates_keyboard()
    )

async def handle_work_type_template(query, context, template_data):
    template_map = {
        'template_brickwork': 'Кладка кирпича',
        'template_installation': 'Монтаж конструкций',
        'template_finishing': 'Отделочные работы',
        'template_foreman': 'Зарплата прораба',
        'template_unloading': 'Разгрузка материалов'
    }
    
    if template_data in template_map:
        context.user_data['salary_data']['work_type'] = template_map[template_data]
        context.user_data['salary_data']['step'] = 'description'
        await show_salary_description_step(query, context)
    elif template_data == 'template_custom':
        context.user_data['awaiting_input'] = 'salary_work_type'
        await query.edit_message_text(
            "📝 *ВВОД ВИДА РАБОТ*\n\n"
            "Введите вид работ:\n\n"
            "*ПРИМЕРЫ:*\n"
            "• `Кладка кирпича 3 этаж`\n"
            "• `Зарплата прораба за ноябрь`\n"
            "• `Монтаж металлоконструкций`\n"
            "• `Штукатурные работы`",
            parse_mode='Markdown',
            reply_markup=back_button('back_to_salary_input')
        )

async def show_salary_description_step(query, context):
    salary_data = context.user_data['salary_data']
    
    await query.edit_message_text(
        f"📝 *ШАГ 2 из 4: ОПИСАНИЕ РАБОТ*\n\n"
        f"🔧 Вид работ: *{salary_data['work_type']}*\n\n"
        "Введите подробное описание работ:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('description')
    )

async def handle_description_input(query, context):
    context.user_data['awaiting_input'] = 'salary_description'
    salary_data = context.user_data['salary_data']
    
    await query.edit_message_text(
        f"📝 *ВВОД ОПИСАНИЯ РАБОТ*\n\n"
        f"Вид работ: *{salary_data['work_type']}*\n\n"
        "Введите подробное описание:\n\n"
        "*ПРИМЕРЫ:*\n"
        "• `Кладка кирпича 3 этаж, 150м²`\n"
        "• `Зарплата за ноябрь 2024 года`\n"
        "• `Монтаж металлоконструкций каркаса`\n"
        "• `Штукатурные работы коридор 2 этаж`",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_salary_input')
    )

async def handle_amount_input(query, context):
    context.user_data['awaiting_input'] = 'salary_amount'
    await query.edit_message_text(
        "💵 *ВВОД СУММЫ*\n\n"
        "Введите сумму начисления в рублях:\n\n"
        "*ПРИМЕРЫ:*\n"
        "• `25000` (двадцать пять тысяч)\n"
        "• `35500.75` (с копейками)\n"
        "• `150000` (сто пятьдесят тысяч)",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_salary_input')
    )

async def show_salary_amount_step(query, context):
    salary_data = context.user_data['salary_data']
    
    await query.edit_message_text(
        f"💵 *ШАГ 3 из 4: СУММА*\n\n"
        f"🔧 Вид работ: *{salary_data['work_type']}*\n"
        f"📝 Описание: *{salary_data['description']}*\n\n"
        "Введите сумму начисления:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('amount')
    )

async def handle_amount_calculator(query, context):
    await query.edit_message_text(
        "🧮 *КАЛЬКУЛЯТОР ЗАРПЛАТЫ*\n\n"
        "Выберите шаблон для расчета или введите сумму вручную:",
        parse_mode='Markdown',
        reply_markup=quick_calculator_keyboard()
    )

async def handle_calculator_template(query, context, calc_data):
    # Базовая ставка (можно вынести в настройки)
    hourly_rate = 350  # руб/час
    
    calc_map = {
        'calc_8_hours': ('8 часов', 8 * hourly_rate),
        'calc_10_hours': ('10 часов', 10 * hourly_rate),
        'calc_12_hours': ('12 часов', 12 * hourly_rate),
        'calc_24_hours': ('Смена (24ч)', 24 * hourly_rate),
        'calc_40_hours': ('Неделя (40ч)', 40 * hourly_rate),
        'calc_168_hours': ('Месяц (168ч)', 168 * hourly_rate)
    }
    
    if calc_data in calc_map:
        template_name, amount = calc_map[calc_data]
        context.user_data['salary_data']['amount'] = amount
        context.user_data['salary_data']['step'] = 'date'
        
        # Добавляем информацию о расчете в описание
        if 'description' in context.user_data['salary_data']:
            context.user_data['salary_data']['description'] += f" ({template_name})"
        
        await show_salary_date_step(query, context)
    elif calc_data == 'calc_manual':
        context.user_data['awaiting_input'] = 'salary_amount'
        await query.edit_message_text(
            "💵 *ВВОД СУММЫ*\n\n"
            "Введите сумму начисления в рублях:\n\n"
            "*ПРИМЕРЫ:*\n"
            "• `25000` (двадцать пять тысяч)\n"
            "• `35500.75` (с копейками)\n"
            "• `150000` (сто пятьдесят тысяч)",
            parse_mode='Markdown',
            reply_markup=back_button('back_to_salary_input')
        )

async def show_salary_date_step(query, context):
    salary_data = context.user_data['salary_data']
    amount_str = f"{salary_data['amount']:,.2f}".replace(',', ' ')
    
    await query.edit_message_text(
        f"📅 *ШАГ 4 из 4: ДАТА РАБОТ*\n\n"
        f"🔧 Вид работ: *{salary_data['work_type']}*\n"
        f"📝 Описание: *{salary_data['description']}*\n"
        f"💵 Сумма: *{amount_str} руб.*\n\n"
        "Введите дату выполнения работ:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('date')
    )

async def handle_date_input(query, context):
    context.user_data['awaiting_input'] = 'salary_work_date'
    
    await query.edit_message_text(
        "📅 *ВВОД ДАТЫ РАБОТ*\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ:\n\n"
        "*ПРИМЕРЫ:*\n"
        f"• `{datetime.now().strftime('%d.%m.%Y')}` (сегодня)\n"
        "• `15.11.2024` (конкретная дата)\n"
        "• `01.12.2024` (первое декабря)",
        parse_mode='Markdown',
        reply_markup=back_button('back_to_salary_input')
    )

async def handle_use_today(query, context):
    today = datetime.now().date()
    context.user_data['salary_data']['work_date'] = today
    await show_salary_confirmation(query, context)

async def save_salary_data(update, context):
    salary_data = context.user_data['salary_data']
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO salaries (project_id, work_type, description, amount, work_date) VALUES (?, ?, ?, ?, ?)",
            (salary_data['project_id'], salary_data['work_type'], salary_data['description'], 
             salary_data['amount'], salary_data['work_date'])
        )
        conn.commit()
        conn.close()
        
        amount_str = f"{salary_data['amount']:,.2f}".replace(',', ' ')
        
        success_text = (
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ЗАРПЛАТА УСПЕШНО НАЧИСЛЕНА*\n\n"
            f"🏗️ *Объект:* {salary_data['project_name']}\n"
            f"🔧 *Вид работ:* {salary_data['work_type']}\n"
            f"📝 *Описание:* {salary_data['description']}\n"
            f"💵 *Сумма:* {amount_str} руб.\n"
            f"📅 *Дата работ:* {salary_data['work_date']}\n\n"
            f"*⏰ Внесено:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                success_text,
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Salary save error: {e}")
        error_text = "❌ Ошибка при начислении заработной платы! Обратитесь к системному администратору."
        
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(
                error_text,
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                error_text,
                reply_markup=main_menu_keyboard()
            )
    
    context.user_data.clear()

# ОБНОВЛЕННЫЙ ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
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
    
    # Обработка проектов
    if state == 'project_name':
        await handle_project_name_text(update, context, text)
    
    # Обработка материалов
    elif state == 'material_name':
        await handle_material_name_text(update, context, text)
    elif state == 'material_quantity':
        await handle_material_quantity_text(update, context, text)
    elif state == 'material_unit_price':
        await handle_material_unit_price_text(update, context, text)
    elif state == 'material_total_price':
        await handle_material_total_price_text(update, context, text)
    
    # Обработка зарплат
    elif state == 'salary_work_type':
        await handle_salary_work_type_text(update, context, text)
    elif state == 'salary_description':
        await handle_salary_description_text(update, context, text)
    elif state == 'salary_amount':
        await handle_salary_amount_text(update, context, text)
    elif state == 'salary_work_date':
        await handle_salary_work_date_text(update, context, text)

# ОБРАБОТЧИКИ ТЕКСТА ДЛЯ ПРОЕКТОВ
async def handle_project_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO projects (name) VALUES (?)", (text,))
        conn.commit()
        conn.close()
        
        context.user_data['awaiting_input'] = None
        
        await update.message.reply_text(
            f"✅ *Объект успешно создан:* {text}\n\n"
            "Теперь вы можете добавлять материалы и зарплаты для этого объекта.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Объект с таким названием уже существует! Введите другое название:",
            reply_markup=back_button('main_menu')
        )
    except Exception as e:
        logger.error(f"Project creation error: {e}")
        await update.message.reply_text(
            "❌ Ошибка при создании объекта! Обратитесь к системному администратору.",
            reply_markup=main_menu_keyboard()
        )

# ОБРАБОТЧИКИ ТЕКСТА ДЛЯ МАТЕРИАЛОВ
async def handle_material_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['material_data']['name'] = text
    context.user_data['material_data']['step'] = 'quantity'
    context.user_data['awaiting_input'] = None
    
    await update.message.reply_text(
        f"✅ *Название сохранено:* {text}\n\n"
        f"📦 *ШАГ 2 из 4: КОЛИЧЕСТВО*\n\n"
        f"Введите количество материала:",
        parse_mode='Markdown',
        reply_markup=material_input_keyboard('quantity')
    )

async def handle_material_quantity_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        quantity = float(text.replace(',', '.'))
        context.user_data['material_data']['quantity'] = quantity
        context.user_data['awaiting_input'] = None
        
        await update.message.reply_text(
            f"✅ *Количество сохранено:* {quantity}\n\n"
            f"📏 *ШАГ 3 из 4: ЕДИНИЦА ИЗМЕРЕНИЯ*\n\n"
            f"Выберите единицу измерения:",
            parse_mode='Markdown',
            reply_markup=unit_selection_keyboard()
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат числа! Введите количество цифрами:",
            reply_markup=material_input_keyboard('quantity')
        )

async def handle_material_unit_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        unit_price = float(text.replace(',', '.'))
        material_data = context.user_data['material_data']
        quantity = material_data['quantity']
        total_price = unit_price * quantity
        
        material_data['unit_price'] = unit_price
        material_data['total_price'] = total_price
        context.user_data['awaiting_input'] = None
        
        await show_material_confirmation(update, context)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат цены! Введите число:",
            reply_markup=material_input_keyboard('price')
        )

async def handle_material_total_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        total_price = float(text.replace(',', '.'))
        material_data = context.user_data['material_data']
        quantity = material_data['quantity']
        unit_price = total_price / quantity if quantity > 0 else 0
        
        material_data['unit_price'] = unit_price
        material_data['total_price'] = total_price
        context.user_data['awaiting_input'] = None
        
        await show_material_confirmation(update, context)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы! Введите число:",
            reply_markup=material_input_keyboard('price')
        )

async def show_material_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    material_data = context.user_data['material_data']
    
    # Форматирование чисел
    quantity_str = f"{material_data['quantity']:,.0f}".replace(',', ' ') if material_data['quantity'].is_integer() else f"{material_data['quantity']:,.2f}".replace(',', ' ')
    unit_price_str = f"{material_data['unit_price']:,.2f}".replace(',', ' ')
    total_price_str = f"{material_data['total_price']:,.2f}".replace(',', ' ')
    
    confirmation_text = (
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"📦 *ПОДТВЕРЖДЕНИЕ ДАННЫХ МАТЕРИАЛА*\n\n"
        f"🏗️ *Объект:* {material_data['project_name']}\n"
        f"📦 *Материал:* {material_data['name']}\n"
        f"📊 *Количество:* {quantity_str} {material_data['unit']}\n"
        f"💰 *Цена за единицу:* {unit_price_str} руб.\n"
        f"🧮 *Общая стоимость:* {total_price_str} руб.\n\n"
        f"Всё верно?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, сохранить", callback_data='confirm_material_save')],
        [InlineKeyboardButton("✏️ Нет, исправить", callback_data='edit_material_data')]
    ]
    
    await update.message.reply_text(
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ОБРАБОТЧИКИ ТЕКСТА ДЛЯ ЗАРПЛАТ
async def handle_salary_work_type_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_data']['work_type'] = text
    context.user_data['salary_data']['step'] = 'description'
    context.user_data['awaiting_input'] = None
    
    await update.message.reply_text(
        f"✅ *Вид работ сохранен:* {text}\n\n"
        f"📝 *ШАГ 2 из 4: ОПИСАНИЕ*\n\n"
        f"Введите описание работ:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('description')
    )

async def handle_salary_description_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_data']['description'] = text
    context.user_data['salary_data']['step'] = 'amount'
    context.user_data['awaiting_input'] = None
    
    await update.message.reply_text(
        f"✅ *Описание сохранено:* {text}\n\n"
        f"💵 *ШАГ 3 из 4: СУММА*\n\n"
        f"Введите сумму начисления:",
        parse_mode='Markdown',
        reply_markup=salary_input_keyboard('amount')
    )

async def handle_salary_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        amount = float(text.replace(',', '.'))
        context.user_data['salary_data']['amount'] = amount
        context.user_data['salary_data']['step'] = 'date'
        context.user_data['awaiting_input'] = None
        
        await update.message.reply_text(
            f"✅ *Сумма сохранена:* {amount:,.2f} руб.\n\n"
            f"📅 *ШАГ 4 из 4: ДАТА*\n\n"
            f"Введите дату работ:",
            parse_mode='Markdown',
            reply_markup=salary_input_keyboard('date')
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы! Введите число:",
            reply_markup=salary_input_keyboard('amount')
        )

async def handle_salary_work_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        work_date = datetime.strptime(text, '%d.%m.%Y').date()
        context.user_data['salary_data']['work_date'] = work_date
        context.user_data['awaiting_input'] = None
        
        await show_salary_confirmation(update, context)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты! Введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=salary_input_keyboard('date')
        )

async def show_salary_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salary_data = context.user_data['salary_data']
    amount_str = f"{salary_data['amount']:,.2f}".replace(',', ' ')
    
    confirmation_text = (
        f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        f"💰 *ПОДТВЕРЖДЕНИЕ ДАННЫХ ЗАРПЛАТЫ*\n\n"
        f"🏗️ *Объект:* {salary_data['project_name']}\n"
        f"🔧 *Вид работ:* {salary_data['work_type']}\n"
        f"📝 *Описание:* {salary_data['description']}\n"
        f"💵 *Сумма:* {amount_str} руб.\n"
        f"📅 *Дата работ:* {salary_data['work_date']}\n\n"
        f"Всё верно?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, сохранить", callback_data='confirm_salary_save')],
        [InlineKeyboardButton("✏️ Нет, исправить", callback_data='edit_salary_data')]
    ]
    
    await update.message.reply_text(
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ОБНОВЛЕННЫЙ ОБРАБОТЧИК КНОПОК
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # ГЛАВНОЕ МЕНЮ
        if data == 'main_menu':
            await query.edit_message_text(
                "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\nВыберите действие:",
                parse_mode='Markdown',
                reply_markup=main_menu_keyboard()
            )
        
        # МЕНЮ МАТЕРИАЛОВ
        elif data == 'materials_menu':
            await query.edit_message_text(
                "📦 *УПРАВЛЕНИЕ МАТЕРИАЛАМИ*\n\nВыберите действие:",
                parse_mode='Markdown',
                reply_markup=materials_menu_keyboard()
            )
        
        # МЕНЮ ЗАРПЛАТ
        elif data == 'salaries_menu':
            await query.edit_message_text(
                "💰 *УПРАВЛЕНИЕ ЗАРПЛАТАМИ*\n\nВыберите действие:",
                parse_mode='Markdown',
                reply_markup=salaries_menu_keyboard()
            )
        
        # ДОБАВЛЕНИЕ ПРОЕКТА
        elif data == 'add_project':
            await add_project_handler(update, context)
        
        # ДОБАВЛЕНИЕ МАТЕРИАЛОВ
        elif data == 'add_material':
            await add_material_handler(query, context)
        
        # ДОБАВЛЕНИЕ ЗАРПЛАТ
        elif data == 'add_salary':
            await add_salary_handler(query, context)
        
        # ВЫБОР ПРОЕКТА
        elif data.startswith('select_project_'):
            await handle_project_selection(query, context, data)
        
        # ОБРАБОТЧИКИ МАТЕРИАЛОВ
        elif data == 'input_material_name':
            await handle_material_name_input(query, context)
        elif data == 'input_material_quantity':
            await handle_material_quantity_input(query, context)
        elif data == 'select_material_unit':
            await handle_unit_selection(query, context)
        elif data == 'input_unit_price':
            await handle_unit_price_input(query, context)
        elif data == 'input_total_price':
            await handle_total_price_input(query, context)
        elif data.startswith('unit_'):
            await handle_material_unit_selection(query, context, data)
        elif data == 'confirm_material_save':
            await save_material_data(update, context)
        elif data == 'back_to_material_input':
            await start_material_input(query, context)
        
        # ОБРАБОТЧИКИ ЗАРПЛАТ
        elif data == 'input_work_type':
            await handle_work_type_input(query, context)
        elif data == 'select_work_template':
            await handle_work_type_templates(query, context)
        elif data == 'input_description':
            await handle_description_input(query, context)
        elif data == 'input_amount':
            await handle_amount_input(query, context)
        elif data == 'calculate_from_hours':
            await handle_amount_calculator(query, context)
        elif data == 'input_date':
            await handle_date_input(query, context)
        elif data == 'use_today':
            await handle_use_today(query, context)
        elif data.startswith('template_'):
            await handle_work_type_template(query, context, data)
        elif data.startswith('calc_'):
            await handle_calculator_template(query, context, data)
        elif data == 'confirm_salary_save':
            await save_salary_data(update, context)
        elif data == 'back_to_salary_input':
            await start_salary_input(query, context)
        
        # СТАТИСТИКА И НАСТРОЙКИ (заглушки)
        elif data == 'reports_menu':
            await query.edit_message_text(
                "📊 *СТАТИСТИКА И ОТЧЕТЫ*\n\n"
                "Раздел в разработке...",
                parse_mode='Markdown',
                reply_markup=back_button('main_menu')
            )
        elif data == 'settings_menu':
            await query.edit_message_text(
                "⚙️ *НАСТРОЙКИ*\n\n"
                "Раздел в разработке...",
                parse_mode='Markdown',
                reply_markup=back_button('main_menu')
            )
        
        # СПИСКИ И ПОИСК (заглушки)
        elif data in ['list_materials', 'search_materials', 'edit_material', 'delete_material',
                     'list_salaries', 'search_salaries', 'edit_salary', 'delete_salary']:
            await query.edit_message_text(
                "🛠️ *ФУНКЦИЯ В РАЗРАБОТКЕ*\n\n"
                "Данный функционал будет доступен в ближайшем обновлении.",
                parse_mode='Markdown',
                reply_markup=back_button('main_menu')
            )
        
        else:
            await query.edit_message_text(
                "❌ Функция в разработке. Возврат в главное меню.",
                reply_markup=main_menu_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка. Возврат в главное меню.",
            reply_markup=main_menu_keyboard()
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
