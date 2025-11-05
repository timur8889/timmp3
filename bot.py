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

# Клавиатуры (остаются без изменений)
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
        [InlineKeyboardButton("упак", callback_data='unit_pack')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команды бота (start остается без изменений)
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

# Обработчики проектов - ИЗМЕНЕНЫ
async def add_project_handler(query, context):
    context.user_data['awaiting_input'] = 'project_name'
    context.user_data['project_stage'] = 'name'
    context.user_data['last_menu'] = 'main_menu'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "🏗️ *РЕГИСТРАЦИЯ НОВОГО ОБЪЕКТА*\n\n"
        "📝 Введите *наименование* строительного объекта:\n\n"
        "*ПРИМЕР:* `Жилой дом по ул. Ленина, 25`",
        parse_mode='Markdown',
        reply_markup=back_button('main_menu')
    )

# Обработчики материалов - ИЗМЕНЕНЫ
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
    
    context.user_data['last_menu'] = 'materials_menu'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "📦 *ПРИХОД МАТЕРИАЛОВ НА ОБЪЕКТ*\n\n"
        "Выберите объект строительства:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('material')
    )

# Обработчики зарплат - ИЗМЕНЕНЫ
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
    
    context.user_data['last_menu'] = 'salaries_menu'
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "💰 *НАЧИСЛЕНИЕ ЗАРАБОТНОЙ ПЛАТЫ*\n\n"
        "Выберите объект строительства:",
        parse_mode='Markdown',
        reply_markup=projects_keyboard('salary')
    )

# Обработка выбора проекта - ДОБАВЛЕНЫ НОВЫЕ ЭТАПЫ
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
        context.user_data['material_stage'] = 'name'
        context.user_data['last_menu'] = 'add_material'
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
        context.user_data['salary_stage'] = 'work_type'
        context.user_data['last_menu'] = 'add_salary'
        await query.edit_message_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"💰 *НАЧИСЛЕНИЕ ЗАРПЛАТЫ*\nОбъект: *{project[0]}*\n\n"
            "🔧 Введите *вид работ*:\n\n"
            "*ПРИМЕР:* `Кладка кирпича` или `Зарплата прораба`",
            parse_mode='Markdown',
            reply_markup=back_button('add_salary')
        )
    
    # остальные обработчики остаются без изменений
    elif action_type == 'stats':
        await show_project_stats(query, project_id, project[0])
    elif action_type == 'report':
        await show_detailed_report(query, project_id, project[0])
    elif action_type == 'edit':
        context.user_data['awaiting_input'] = 'edit_project_name'
        context.user_data['last_menu'] = 'edit_project'
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

# НОВЫЕ ФУНКЦИИ ДЛЯ ПОШАГОВОГО ВВОДА

async def handle_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if 'project_stage' in context.user_data:
        stage = context.user_data['project_stage']
        
        if stage == 'name':
            context.user_data['project_name'] = text
            context.user_data['project_stage'] = 'address'
            context.user_data['awaiting_input'] = 'project_address'
            
            await update.message.reply_text(
                "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                "🏗️ *РЕГИСТРАЦИЯ НОВОГО ОБЪЕКТА*\n\n"
                "📍 Введите *адрес* строительного объекта:\n\n"
                "*ПРИМЕР:* `г. Москва, ул. Ленина, д. 25`",
                parse_mode='Markdown',
                reply_markup=back_button('add_project')
            )
        
        elif stage == 'address':
            project_name = context.user_data['project_name']
            address = text
            
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT INTO projects (name, address) VALUES (?, ?)", (project_name, address))
                conn.commit()
                conn.close()
                
                await update.message.reply_text(
                    f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
                    f"✅ *ОБЪЕКТ ЗАРЕГИСТРИРОВАН*\n\n"
                    f"🏗️ Наименование: *{project_name}*\n"
                    f"📍 Адрес: *{address}*\n\n"
                    f"Объект успешно внесен в корпоративную систему учета.",
                    parse_mode='Markdown',
                    reply_markup=main_menu_keyboard()
                )
                
            except sqlite3.IntegrityError:
                await update.message.reply_text(
                    "❌ Объект с таким наименованием уже зарегистрирован в системе!",
                    reply_markup=back_button('add_project')
                )
            
            context.user_data.clear()

async def handle_material_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['material_name'] = text
    context.user_data['material_stage'] = 'quantity'
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
        context.user_data['material_stage'] = 'unit'
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

async def handle_material_unit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    # Обработка выбора единицы измерения через кнопки
    unit_map = {
        'unit_sh': 'шт', 'unit_kg': 'кг', 'unit_t': 'т', 
        'unit_m3': 'м³', 'unit_m2': 'м²', 'unit_m': 'м',
        'unit_l': 'л', 'unit_pack': 'упак'
    }
    
    if text in unit_map:
        context.user_data['material_unit'] = unit_map[text]
        context.user_data['material_stage'] = 'total_price'
        context.user_data['awaiting_input'] = 'material_total_price'
        
        await update.message.reply_text(
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"📦 *ПРИХОД МАТЕРИАЛОВ*\n\n"
            f"📦 Материал: *{context.user_data['material_name']}*\n"
            f"🔢 Количество: *{context.user_data['material_quantity']} {unit_map[text]}*\n\n"
            f"💰 Введите *общую стоимость* материала (руб.):\n\n"
            f"*ПРИМЕР:* `25500.50`",
            parse_mode='Markdown',
            reply_markup=back_button('add_material')
        )

async def handle_material_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        total_price = float(text.replace(',', '.'))
        quantity = context.user_data['material_quantity']
        unit_price = total_price / quantity if quantity > 0 else 0
        
        # Сохраняем данные материала
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

async def handle_salary_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data['salary_work_type'] = text
    context.user_data['salary_stage'] = 'description'
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
    context.user_data['salary_stage'] = 'amount'
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
        context.user_data['salary_stage'] = 'work_date'
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
        # Парсим дату
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

# ОБНОВЛЕННАЯ ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
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
        await handle_project_name(update, context, text)
    elif state == 'project_address':
        await handle_project_name(update, context, text)
    
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
    
    # Поиск (остается без изменений)
    elif state == 'search_materials':
        await handle_search_materials(update, context, text)
    elif state == 'search_salaries':
        await handle_search_salaries(update, context, text)
    
    # Редактирование (остается без изменений)
    elif state == 'edit_project_name':
        await handle_edit_project_name(update, context, text)
    elif state == 'edit_material_data':
        await handle_edit_material_data(update, context, text)
    elif state == 'edit_salary_data':
        await handle_edit_salary_data(update, context, text)

# ОБНОВЛЕННЫЕ ФУНКЦИИ ОТЧЕТОВ
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
        SELECT name, quantity, unit, unit_price, total_price
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
            stats_text += f"• {material[0]}: {material[1]} {material[2]} × {material[3]:,.2f} = {material[4]:,.2f} руб.\n"
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

# ОБНОВЛЕННАЯ ФУНКЦИЯ ЭКСПОРТА
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

# ОБНОВЛЕННЫЙ ОБРАБОТЧИК КНОПОК
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
    elif query.data == 'edit_project':
        await edit_project_handler(query, context)
    elif query.data == 'delete_project':
        await delete_project_handler(query, context)
    
    # Материалы
    elif query.data == 'add_material':
        await add_material_handler(query, context)
    elif query.data == 'list_materials':
        await list_materials_handler(query)
    elif query.data == 'search_materials':
        await search_materials_handler(query, context)
    elif query.data == 'edit_material':
        await edit_material_handler(query, context)
    elif query.data == 'delete_material':
        await delete_material_handler(query, context)
    
    # Зарплаты
    elif query.data == 'add_salary':
        await add_salary_handler(query, context)
    elif query.data == 'list_salaries':
        await list_salaries_handler(query)
    elif query.data == 'search_salaries':
        await search_salaries_handler(query, context)
    elif query.data == 'edit_salary':
        await edit_salary_handler(query, context)
    elif query.data == 'delete_salary':
        await delete_salary_handler(query, context)
    
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
    elif query.data.startswith(('material_project_', 'salary_project_', 'stats_project_', 'report_project_', 'edit_project_', 'delete_project_')):
        await handle_project_selection(query, context)
    
    # Обработка единиц измерения материалов
    elif query.data.startswith('unit_'):
        await handle_material_unit(query, context, query.data)
    
    # Обработка выбора материала/зарплаты для редактирования/удаления
    elif query.data.startswith(('edit_material_', 'delete_material_', 'edit_salary_', 'delete_salary_')):
        await handle_item_selection(query, context)
    
    # Подтверждение действий
    elif query.data.startswith(('confirm_', 'cancel_')):
        await handle_confirmation(query, context)
    
    # Назад
    elif query.data.startswith('back_to_'):
        await handle_back_button(query, context)

# ДОБАВЛЕНА ФУНКЦИЯ ОБРАБОТКИ ЕДИНИЦ ИЗМЕРЕНИЯ
async def handle_material_unit(query, context, unit_data):
    context.user_data['material_unit'] = unit_data
    context.user_data['material_stage'] = 'total_price'
    context.user_data['awaiting_input'] = 'material_total_price'
    
    unit_map = {
        'unit_sh': 'шт', 'unit_kg': 'кг', 'unit_t': 'т', 
        'unit_m3': 'м³', 'unit_m2': 'м²', 'unit_m': 'м',
        'unit_l': 'л', 'unit_pack': 'упак'
    }
    
    selected_unit = unit_map.get(unit_data, 'шт')
    
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

# Основная функция (без изменений)
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
