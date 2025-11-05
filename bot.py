import sqlite3
import pandas as pd
import gspread
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, JobQueue
import logging
from dotenv import load_dotenv
import re
from datetime import datetime, time, timedelta
import shutil
import asyncio

# Загрузка переменных окружения из .env файла
load_dotenv()

# КОНСТАНТЫ И КОНФИГУРАЦИЯ
UNIT_MAP = {
    'unit_sh': 'шт', 'unit_kg': 'кг', 'unit_t': 'т', 
    'unit_m3': 'м³', 'unit_m2': 'м²', 'unit_m': 'м',
    'unit_l': 'л', 'unit_pack': 'упак', 'unit_roll': 'рулон',
    'unit_bag': 'мешок', 'unit_kit': 'комплект', 'unit_can': 'банка'
}

WORK_TYPE_TEMPLATES = {
    'template_brickwork': 'Кладка кирпича',
    'template_installation': 'Монтаж конструкций',
    'template_finishing': 'Отделочные работы',
    'template_foreman': 'Зарплата прораба',
    'template_unloading': 'Разгрузка материалов'
}

CALCULATION_TEMPLATES = {
    'calc_8_hours': ('8 часов', 8),
    'calc_10_hours': ('10 часов', 10),
    'calc_12_hours': ('12 часов', 12),
    'calc_24_hours': ('Смена (24ч)', 24),
    'calc_40_hours': ('Неделя (40ч)', 40),
    'calc_168_hours': ('Месяц (168ч)', 168)
}

# Определение шагов для разных процессов
PROJECT_STEPS = [
    {'key': 'name', 'title': 'Название объекта', 'type': 'text', 'required': True,
     'examples': ["Строительство ЖК 'Северный Парк'", "Реконструкция бизнес-центра"]},
    {'key': 'address', 'title': 'Адрес объекта', 'type': 'text', 'required': True,
     'examples': ["ул. Строителей, 15", "пр. Мира, 28"]}
]

MATERIAL_STEPS = [
    {'key': 'name', 'title': 'Название материала', 'type': 'text', 'required': True,
     'examples': ["Кирпич красный М-150", "Цемент М500 Д0 мешок 50кг"]},
    {'key': 'quantity', 'title': 'Количество', 'type': 'number', 'required': True,
     'examples': ["1000", "2.5", "50"]},
    {'key': 'unit', 'title': 'Единица измерения', 'type': 'select', 'required': True,
     'options': UNIT_MAP},
    {'key': 'price_type', 'title': 'Тип ввода цены', 'type': 'select', 'required': True,
     'options': {'unit': 'Цена за единицу', 'total': 'Общая стоимость'}},
    {'key': 'price_value', 'title': 'Стоимость', 'type': 'number', 'required': True,
     'examples': ["28.50", "42750"]}
]

SALARY_STEPS = [
    {'key': 'work_type', 'title': 'Вид работ', 'type': 'select_text', 'required': True,
     'options': WORK_TYPE_TEMPLATES, 'custom_option': True},
    {'key': 'description', 'title': 'Описание работ', 'type': 'text', 'required': False,
     'examples': ["Кладка кирпича 3 этаж, 150м²", "Зарплата за ноябрь 2024"]},
    {'key': 'amount_type', 'title': 'Способ расчета', 'type': 'select', 'required': True,
     'options': {'manual': 'Ввести сумму', 'calculate': 'Рассчитать от часов'}},
    {'key': 'amount', 'title': 'Сумма', 'type': 'number', 'required': True,
     'examples': ["25000", "35500.75"]},
    {'key': 'work_date', 'title': 'Дата работ', 'type': 'date', 'required': True,
     'examples': [datetime.now().strftime('%d.%m.%Y')]}
]

class BotConfig:
    def __init__(self):
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')
        self.DB_PATH = 'construction.db'
        self.ALLOWED_USERS = [int(x) for x in os.getenv('ALLOWED_USERS', '').split(',') if x]
        self.ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]
        self.HOURLY_RATE = float(os.getenv('HOURLY_RATE', '350'))
        self.GC_CREDENTIALS = 'credentials.json'
        self.GSHEET_NAME = 'Construction Tracker'
        
    def validate(self):
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не найден!")
        return True

class StepByStepInput:
    def __init__(self, process_type, steps):
        self.process_type = process_type
        self.steps = steps
        self.current_step = 0
        self.data = {}
    
    def next_step(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            return True
        return False
    
    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            return True
        return False
    
    def get_current_step(self):
        return self.steps[self.current_step]
    
    def is_complete(self):
        return self.current_step >= len(self.steps) - 1

# Инициализация конфигурации
config = BotConfig()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# УТИЛИТЫ
def validate_number(text):
    """Валидация числового ввода"""
    try:
        value = float(text.replace(',', '.'))
        return value > 0, value
    except ValueError:
        return False, 0

def validate_date(text):
    """Валидация даты в различных форматах"""
    try:
        for fmt in ('%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
    except:
        return None

def format_currency(value):
    """Форматирование денежных значений с разделителями тысяч"""
    return f"{value:,.2f}".replace(',', ' ').replace('.', ',')

def format_quantity(value):
    """Форматирование количеств"""
    if value.is_integer():
        return f"{value:,.0f}".replace(',', ' ')
    return f"{value:,.2f}".replace(',', ' ').replace('.', ',')

async def backup_database():
    """Создание резервной копии базы данных"""
    try:
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f'construction_backup_{timestamp}.db')
        
        shutil.copy2(config.DB_PATH, backup_file)
        logger.info(f"Создана резервная копия: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")
        return None

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневный отчет"""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        
        # Статистика за день
        today = datetime.now().date()
        daily_materials = conn.execute(
            "SELECT SUM(total_price) FROM materials WHERE DATE(date_added) = ?", 
            (today,)
        ).fetchone()[0] or 0
        
        daily_salaries = conn.execute(
            "SELECT SUM(amount) FROM salaries WHERE DATE(date_added) = ?", 
            (today,)
        ).fetchone()[0] or 0
        
        conn.close()
        
        report_text = (
            f"📊 *ЕЖЕДНЕВНЫЙ ОТЧЕТ*\n"
            f"Дата: {today.strftime('%d.%m.%Y')}\n\n"
            f"📦 Материалы: {format_currency(daily_materials)} руб.\n"
            f"💰 Зарплаты: {format_currency(daily_salaries)} руб.\n"
            f"🧮 Итого: {format_currency(daily_materials + daily_salaries)} руб."
        )
        
        # Отправка админам
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=report_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Не удалось отправить отчет {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при формировании ежедневного отчета: {e}")

# Инициализация БД
def init_db():
    conn = sqlite3.connect(config.DB_PATH)
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
    
    # Добавляем тестовый проект если нет проектов
    projects = cur.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    if projects == 0:
        cur.execute("INSERT INTO projects (name, address) VALUES (?, ?)", 
                   ("Строительство ЖК 'Северный'", "ул. Строителей, 15"))
        cur.execute("INSERT INTO projects (name, address) VALUES (?, ?)", 
                   ("Реконструкция бизнес-центра", "пр. Мира, 28"))
    
    conn.commit()
    conn.close()

# Функция проверки доступа пользователя
def check_user_access(user_id):
    if not config.ALLOWED_USERS:
        return True  # Если не настроены ограничения, доступ для всех
    return user_id in config.ALLOWED_USERS

# УЛУЧШЕННАЯ СИСТЕМА ШАГОВОГО ВВОДА

async def start_step_process(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           process_type: str, steps_config: list, project_data=None):
    """Запуск улучшенного шагового процесса"""
    
    process = StepByStepInput(process_type, steps_config)
    context.user_data[process_type] = process
    if project_data:
        context.user_data[f'{process_type}_project'] = project_data
    
    await show_current_step(update, context, process_type)

async def show_current_step(update: Update, context: ContextTypes.DEFAULT_TYPE, process_type: str):
    """Показать текущий шаг процесса"""
    
    process = context.user_data[process_type]
    step_data = process.get_current_step()
    
    # Формируем текст сообщения с прогрессом и сводкой
    message_text = await format_step_message(context, process_type, step_data)
    
    # Создаем клавиатуру для текущего шага
    reply_markup = create_step_keyboard(step_data, context, process_type)
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def format_step_message(context: ContextTypes.DEFAULT_TYPE, process_type: str, step_data: dict):
    """Форматирование сообщения для шага с прогрессом и сводкой"""
    
    process = context.user_data[process_type]
    project_data = context.user_data.get(f'{process_type}_project', {})
    
    # Заголовок процесса
    process_titles = {
        'project': '🏗️ ДОБАВЛЕНИЕ ОБЪЕКТА',
        'material': '📦 ДОБАВЛЕНИЕ МАТЕРИАЛА',
        'salary': '💰 ДОБАВЛЕНИЕ ЗАРПЛАТЫ'
    }
    
    message = f"*{process_titles.get(process_type, 'ПРОЦЕСС')}*\n\n"
    
    # Прогресс-бар
    total_steps = len(process.steps)
    current_step_num = process.current_step + 1
    progress_bar = "🟢" * current_step_num + "⚪" * (total_steps - current_step_num)
    message += f"*Шаг {current_step_num} из {total_steps}:* {step_data['title']}\n"
    message += f"`{progress_bar}`\n\n"
    
    # Информация о проекте (если есть)
    if project_data and 'name' in project_data:
        project_name = project_data.get('name', 'Неизвестно')
        message += f"🏗️ *Объект:* {project_name}\n\n"
    
    # Сводка уже введенных данных
    filled_data = await get_filled_data_summary(process.data, process_type)
    if filled_data:
        message += "*Уже введено:*\n" + filled_data + "\n\n"
    
    # Текущий шаг
    message += f"*{step_data['title']}:*\n"
    
    if step_data['type'] == 'select':
        message += "Выберите вариант:\n"
    elif step_data['type'] == 'select_text':
        message += "Выберите вариант или введите свой:\n"
    elif step_data['type'] == 'number':
        message += "Введите число:\n"
    elif step_data['type'] == 'text':
        message += "Введите текст:\n"
    elif step_data['type'] == 'date':
        message += "Введите дату или выберите:\n"
    
    # Примеры
    if 'examples' in step_data:
        message += "\n*Примеры:*\n"
        for example in step_data['examples'][:3]:
            message += f"• `{example}`\n"
    
    return message

async def get_filled_data_summary(data: dict, process_type: str) -> str:
    """Получить сводку заполненных данных"""
    
    summaries = []
    
    for key, value in data.items():
        if value:
            if key == 'quantity' and 'unit' in data:
                summaries.append(f"• Количество: {format_quantity(value)} {data['unit']}")
            elif key == 'price_value' and 'price_type' in data:
                if data['price_type'] == 'unit':
                    summaries.append(f"• Цена за единицу: {format_currency(value)} руб.")
                else:
                    summaries.append(f"• Общая стоимость: {format_currency(value)} руб.")
            elif key == 'amount':
                summaries.append(f"• Сумма: {format_currency(value)} руб.")
            elif key == 'work_date':
                summaries.append(f"• Дата: {value}")
            elif key == 'work_type':
                summaries.append(f"• Вид работ: {value}")
            elif key == 'name' and process_type == 'project':
                summaries.append(f"• Название: {value}")
            elif key == 'address':
                summaries.append(f"• Адрес: {value}")
            elif key == 'name' and process_type == 'material':
                summaries.append(f"• Материал: {value}")
    
    return "\n".join(summaries)

def create_step_keyboard(step_data, context, process_type):
    """Создание клавиатуры для шага"""
    keyboard = []
    step = step_data['key']
    
    if step_data['type'] == 'select':
        # Кнопки для выбора из вариантов
        options = step_data['options']
        if isinstance(options, dict):
            for key, value in options.items():
                callback_data = f'step_select_{process_type}_{step}_{key}'
                keyboard.append([InlineKeyboardButton(value, callback_data=callback_data)])
    
    elif step_data['type'] == 'select_text':
        # Шаблонные варианты + свой вариант
        options = step_data['options']
        for key, value in options.items():
            callback_data = f'step_select_{process_type}_{step}_{key}'
            keyboard.append([InlineKeyboardButton(value, callback_data=callback_data)])
        
        if step_data.get('custom_option'):
            keyboard.append([InlineKeyboardButton("✏️ Свой вариант", 
                                               callback_data=f'step_custom_{process_type}_{step}')])
    
    # Быстрые подсказки для числовых полей
    elif step_data['type'] == 'number' and 'examples' in step_data:
        examples = step_data['examples'][:3]  # Первые 3 примера
        row = []
        for example in examples:
            callback_data = f'step_quick_{process_type}_{step}_{example}'
            row.append(InlineKeyboardButton(example, callback_data=callback_data))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
    
    # Быстрые даты
    elif step_data['type'] == 'date':
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        keyboard.extend([
            [InlineKeyboardButton("📅 Сегодня", 
                                callback_data=f'step_quick_{process_type}_{step}_{today.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton("📅 Вчера", 
                                callback_data=f'step_quick_{process_type}_{step}_{yesterday.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton("📅 Выбрать дату", 
                                callback_data=f'step_calendar_{process_type}_{step}')]
        ])
    
    # Калькулятор для зарплаты
    elif step == 'amount' and context.user_data.get('salary_data', {}).get('amount_type') == 'calculate':
        keyboard.extend([
            [InlineKeyboardButton("🧮 8 часов", callback_data=f'step_calc_{process_type}_amount_8')],
            [InlineKeyboardButton("🧮 10 часов", callback_data=f'step_calc_{process_type}_amount_10')],
            [InlineKeyboardButton("🧮 12 часов", callback_data=f'step_calc_{process_type}_amount_12')],
            [InlineKeyboardButton("🧮 Смена (24ч)", callback_data=f'step_calc_{process_type}_amount_24')],
        ])
    
    # Навигация
    nav_buttons = []
    process = context.user_data[process_type]
    
    if process.current_step > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", 
                                              callback_data=f'step_nav_{process_type}_prev'))
    
    if process.is_complete():
        nav_buttons.append(InlineKeyboardButton("✅ Завершить", 
                                              callback_data=f'step_complete_{process_type}'))
    else:
        if not step_data.get('required', True):
            nav_buttons.append(InlineKeyboardButton("⏭️ Пропустить", 
                                                  callback_data=f'step_skip_{process_type}'))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", 
                                        callback_data=f'step_cancel_{process_type}')])
    
    return InlineKeyboardMarkup(keyboard)

async def handle_step_selection(query, context, process_type, step, value):
    """Обработчик выбора варианта в шаге"""
    
    process = context.user_data[process_type]
    step_data = process.get_current_step()
    
    # Обработка специальных случаев
    if step == 'price_type':
        if value == 'unit':
            process.data['price_type'] = 'unit'
            # Обновляем заголовок следующего шага
            for s in process.steps:
                if s['key'] == 'price_value':
                    s['title'] = 'Цена за единицу'
                    s['examples'] = ["28.50", "150.75"]
        else:
            process.data['price_type'] = 'total'
            for s in process.steps:
                if s['key'] == 'price_value':
                    s['title'] = 'Общая стоимость'
                    s['examples'] = ["42750", "150000"]
    
    elif step == 'amount_type':
        process.data['amount_type'] = value
        if value == 'calculate':
            # Обновляем следующий шаг для калькулятора
            for s in process.steps:
                if s['key'] == 'amount':
                    s['title'] = 'Расчет суммы'
                    s['examples'] = []
    
    elif step == 'unit':
        process.data[step] = UNIT_MAP.get(value, value)
    
    elif step == 'work_type':
        process.data[step] = WORK_TYPE_TEMPLATES.get(value, value)
    
    else:
        process.data[step] = value
    
    # Переход к следующему шагу
    if process.next_step():
        await show_current_step(query, context, process_type)
    else:
        await complete_step_process(query, context, process_type)

async def handle_quick_input(query, context, process_type, step, value):
    """Обработчик быстрого ввода"""
    
    process = context.user_data[process_type]
    
    # Валидация и преобразование значений
    if process.get_current_step()['type'] == 'number':
        is_valid, num_value = validate_number(value)
        if is_valid:
            process.data[step] = num_value
    elif process.get_current_step()['type'] == 'date':
        date_value = validate_date(value)
        if date_value:
            process.data[step] = date_value
    else:
        process.data[step] = value
    
    # Переход к следующему шагу
    if process.next_step():
        await show_current_step(query, context, process_type)
    else:
        await complete_step_process(query, context, process_type)

async def handle_calculation(query, context, process_type, step, hours):
    """Обработчик расчета зарплаты"""
    
    process = context.user_data[process_type]
    amount = float(hours) * config.HOURLY_RATE
    process.data[step] = amount
    
    # Добавляем информацию о расчете в описание
    if 'description' in process.data:
        process.data['description'] += f" ({hours} часов)"
    
    # Переход к следующему шагу
    if process.next_step():
        await show_current_step(query, context, process_type)
    else:
        await complete_step_process(query, context, process_type)

async def handle_step_navigation(query, context, process_type, direction):
    """Обработчик навигации по шагам"""
    
    process = context.user_data[process_type]
    
    if direction == 'prev':
        process.prev_step()
    elif direction == 'skip':
        current_step = process.get_current_step()
        if not current_step.get('required', False):
            process.data[current_step['key']] = None
            process.next_step()
    
    await show_current_step(query, context, process_type)

async def complete_step_process(query, context, process_type):
    """Завершение процесса и сохранение данных"""
    
    process = context.user_data[process_type]
    data = process.data
    project_data = context.user_data.get(f'{process_type}_project', {})
    
    try:
        if process_type == 'project':
            await save_project_data(query, context, data)
        elif process_type == 'material':
            # Обработка цены материала
            if 'price_type' in data and 'price_value' in data:
                if data['price_type'] == 'unit':
                    data['unit_price'] = data['price_value']
                    data['total_price'] = data['price_value'] * data['quantity']
                else:
                    data['total_price'] = data['price_value']
                    data['unit_price'] = data['price_value'] / data['quantity'] if data['quantity'] > 0 else 0
            
            data['project_id'] = project_data.get('id')
            data['project_name'] = project_data.get('name')
            await save_material_data(query, context, data)
        elif process_type == 'salary':
            data['project_id'] = project_data.get('id')
            data['project_name'] = project_data.get('name')
            await save_salary_data(query, context, data)
        
        # Очистка данных процесса
        del context.user_data[process_type]
        if f'{process_type}_project' in context.user_data:
            del context.user_data[f'{process_type}_project']
            
    except Exception as e:
        logger.error(f"Error completing {process_type} process: {e}")
        await query.edit_message_text(
            "❌ Ошибка при сохранении данных!",
            reply_markup=main_menu_keyboard()
        )

# КЛАВИАТУРЫ
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
        [InlineKeyboardButton("📈 Общая статистика", callback_data='general_stats')],
        [InlineKeyboardButton("🏗️ По объектам", callback_data='project_stats')],
        [InlineKeyboardButton("📅 За период", callback_data='period_stats')],
        [InlineKeyboardButton("📊 Экспорт в Google Sheets", callback_data='export_gsheets')],
        [InlineKeyboardButton("📄 Экспорт в Excel", callback_data='export_excel')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("👥 Управление пользователями", callback_data='user_management')],
        [InlineKeyboardButton("💳 Настройка ставок", callback_data='rate_settings')],
        [InlineKeyboardButton("🔔 Уведомления", callback_data='notifications')],
        [InlineKeyboardButton("🗂️ Резервное копирование", callback_data='backup')],
        [InlineKeyboardButton("↩️ Назад", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def projects_keyboard(action_type):
    conn = sqlite3.connect(config.DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    keyboard = []
    for project_id, project_name in projects:
        keyboard.append([InlineKeyboardButton(project_name, callback_data=f'select_project_{action_type}_{project_id}')])
    
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def back_button(target_menu):
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data=target_menu)]])

# ОСНОВНЫЕ ОБРАБОТЧИКИ КОМАНД
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_access(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещен. Обратитесь к администратору.")
        return
        
    await update.message.reply_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "Система учета строительных материалов и заработной платы\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=main_menu_keyboard()
    )

# ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ
async def handle_main_menu(query, context):
    await query.edit_message_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
        "Главное меню системы учета:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

async def handle_materials_menu(query, context):
    await query.edit_message_text(
        "📦 *УПРАВЛЕНИЕ МАТЕРИАЛАМИ*\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=materials_menu_keyboard()
    )

async def handle_salaries_menu(query, context):
    await query.edit_message_text(
        "💰 *УПРАВЛЕНИЕ ЗАРПЛАТАМИ*\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=salaries_menu_keyboard()
    )

async def handle_reports_menu(query, context):
    await query.edit_message_text(
        "📊 *СТАТИСТИКА И ОТЧЕТЫ*\n\n"
        "Выберите тип отчета:",
        parse_mode='Markdown',
        reply_markup=reports_menu_keyboard()
    )

async def handle_settings_menu(query, context):
    await query.edit_message_text(
        "⚙️ *НАСТРОЙКИ СИСТЕМЫ*\n\n"
        "Выберите раздел настроек:",
        parse_mode='Markdown',
        reply_markup=settings_menu_keyboard()
    )

# ОБРАБОТЧИКИ ПРОЕКТОВ
async def add_project_handler(query, context):
    await start_step_process(query, context, 'project', PROJECT_STEPS)

async def handle_project_selection_material(query, context, project_id):
    """Обработчик выбора проекта для материала"""
    
    conn = sqlite3.connect(config.DB_PATH)
    project = conn.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    project_data = {'id': project[0], 'name': project[1]}
    await start_step_process(query, context, 'material', MATERIAL_STEPS, project_data)

async def handle_project_selection_salary(query, context, project_id):
    """Обработчик выбора проекта для зарплаты"""
    
    conn = sqlite3.connect(config.DB_PATH)
    project = conn.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    project_data = {'id': project[0], 'name': project[1]}
    await start_step_process(query, context, 'salary', SALARY_STEPS, project_data)

async def save_project_data(update, context, data):
    """Сохранение данных проекта"""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO projects (name, address) VALUES (?, ?)",
            (data['name'], data['address'])
        )
        conn.commit()
        conn.close()
        
        success_text = (
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ОБЪЕКТ УСПЕШНО ДОБАВЛЕН*\n\n"
            f"🏗️ *Название:* {data['name']}\n"
            f"🏢 *Адрес:* {data['address']}\n\n"
            f"*📅 Дата создания:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
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
        
    except sqlite3.IntegrityError:
        error_msg = "❌ Объект с таким названием уже существует!"
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(error_msg, reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text(error_msg, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.error(f"Project save error: {e}")
        error_msg = "❌ Ошибка при сохранении объекта!"
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(error_msg, reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text(error_msg, reply_markup=main_menu_keyboard())

# ОБРАБОТЧИКИ МАТЕРИАЛОВ
async def add_material_handler(query, context):
    conn = sqlite3.connect(config.DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Для внесения материалов необходимо сначала зарегистрировать строительный объект!",
            reply_markup=back_button('materials_menu')
        )
        return
    
    # Показываем выбор проекта как первый шаг
    keyboard = []
    for project_id, project_name in projects:
        keyboard.append([InlineKeyboardButton(project_name, 
                                           callback_data=f'select_project_material_{project_id}')])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='materials_menu')])
    
    await query.edit_message_text(
        "📦 *ДОБАВЛЕНИЕ МАТЕРИАЛА*\n\n"
        "Выберите строительный объект:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def save_material_data(update, context, data):
    """Сохранение данных материала"""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO materials (project_id, name, quantity, unit, unit_price, total_price) VALUES (?, ?, ?, ?, ?, ?)",
            (data['project_id'], data['name'], data['quantity'], 
             data['unit'], data['unit_price'], data['total_price'])
        )
        conn.commit()
        conn.close()
        
        # Форматирование чисел с разделителями тысяч
        quantity_str = format_quantity(data['quantity'])
        unit_price_str = format_currency(data['unit_price'])
        total_price_str = format_currency(data['total_price'])
        
        success_text = (
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *МАТЕРИАЛ УСПЕШНО ДОБАВЛЕН*\n\n"
            f"🏗️ *Объект:* {data['project_name']}\n"
            f"📦 *Материал:* {data['name']}\n"
            f"📊 *Количество:* {quantity_str} {data['unit']}\n"
            f"💰 *Цена за единицу:* {unit_price_str} руб.\n"
            f"🧮 *Общая стоимость:* {total_price_str} руб.\n\n"
            f"*📅 Дата оприходования:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
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
        logger.error(f"Material save error: {e}")
        error_msg = "❌ Ошибка при сохранении материала! Обратитесь к системному администратору."
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(error_msg, reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text(error_msg, reply_markup=main_menu_keyboard())

# ОБРАБОТЧИКИ ЗАРПЛАТ
async def add_salary_handler(query, context):
    conn = sqlite3.connect(config.DB_PATH)
    projects = conn.execute("SELECT id, name FROM projects").fetchall()
    conn.close()
    
    if not projects:
        await query.edit_message_text(
            "❌ Для начисления заработной платы необходимо сначала зарегистрировать строительный объект!",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    # Показываем выбор проекта как первый шаг
    keyboard = []
    for project_id, project_name in projects:
        keyboard.append([InlineKeyboardButton(project_name, 
                                           callback_data=f'select_project_salary_{project_id}')])
    keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data='salaries_menu')])
    
    await query.edit_message_text(
        "💰 *ДОБАВЛЕНИЕ ЗАРПЛАТЫ*\n\n"
        "Выберите строительный объект:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def save_salary_data(update, context, data):
    """Сохранение данных зарплаты"""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO salaries (project_id, work_type, description, amount, work_date) VALUES (?, ?, ?, ?, ?)",
            (data['project_id'], data['work_type'], data.get('description', ''), 
             data['amount'], data['work_date'])
        )
        conn.commit()
        conn.close()
        
        amount_str = format_currency(data['amount'])
        
        success_text = (
            f"🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\n"
            f"✅ *ЗАРПЛАТА УСПЕШНО НАЧИСЛЕНА*\n\n"
            f"🏗️ *Объект:* {data['project_name']}\n"
            f"🔧 *Вид работ:* {data['work_type']}\n"
            f"📝 *Описание:* {data.get('description', 'Не указано')}\n"
            f"💵 *Сумма:* {amount_str} руб.\n"
            f"📅 *Дата работ:* {data['work_date']}\n\n"
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
        error_msg = "❌ Ошибка при начислении заработной платы! Обратитесь к системному администратору."
        if hasattr(update, 'callback_query'):
            await update.callback_query.edit_message_text(error_msg, reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text(error_msg, reply_markup=main_menu_keyboard())

# ФУНКЦИИ ПРОСМОТРА МАТЕРИАЛОВ
async def list_materials_handler(query, context):
    project_id = context.user_data.get('selected_project')
    if not project_id:
        # Если проект не выбран, показываем список проектов
        await query.edit_message_text(
            "📋 *СПИСОК МАТЕРИАЛОВ*\n\n"
            "Выберите проект для просмотра материалов:",
            parse_mode='Markdown',
            reply_markup=projects_keyboard('list_materials')
        )
        return
        
    conn = sqlite3.connect(config.DB_PATH)
    materials = conn.execute(
        """SELECT name, quantity, unit, unit_price, total_price, date_added 
           FROM materials WHERE project_id = ? ORDER BY date_added DESC""",
        (project_id,)
    ).fetchall()
    conn.close()
    
    if not materials:
        await query.edit_message_text(
            "📦 Материалы не найдены для выбранного проекта",
            reply_markup=back_button('materials_menu')
        )
        return
    
    project_name = context.user_data.get('selected_project_name', 'Проект')
    materials_text = f"📦 *СПИСОК МАТЕРИАЛОВ*\n\n*Проект:* {project_name}\n\n"
    
    total_cost = 0
    for i, (name, qty, unit, unit_price, total_price, date_added) in enumerate(materials, 1):
        materials_text += f"*{i}. {name}*\n"
        materials_text += f"   Количество: {format_quantity(qty)} {unit}\n"
        materials_text += f"   Цена: {format_currency(unit_price)} руб. × {format_quantity(qty)} = {format_currency(total_price)} руб.\n"
        materials_text += f"   Дата: {datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')}\n\n"
        total_cost += total_price
    
    materials_text += f"*💰 ОБЩАЯ СТОИМОСТЬ: {format_currency(total_cost)} руб.*"
    
    await query.edit_message_text(
        materials_text,
        parse_mode='Markdown',
        reply_markup=back_button('materials_menu')
    )

# ФУНКЦИИ ПРОСМОТРА ЗАРПЛАТ
async def list_salaries_handler(query, context):
    project_id = context.user_data.get('selected_project')
    if not project_id:
        # Если проект не выбран, показываем список проектов
        await query.edit_message_text(
            "📋 *СПИСОК ЗАРПЛАТ*\n\n"
            "Выберите проект для просмотра зарплат:",
            parse_mode='Markdown',
            reply_markup=projects_keyboard('list_salaries')
        )
        return
        
    conn = sqlite3.connect(config.DB_PATH)
    salaries = conn.execute(
        """SELECT work_type, description, amount, work_date, date_added 
           FROM salaries WHERE project_id = ? ORDER BY work_date DESC""",
        (project_id,)
    ).fetchall()
    conn.close()
    
    if not salaries:
        await query.edit_message_text(
            "💰 Зарплаты не найдены для выбранного проекта",
            reply_markup=back_button('salaries_menu')
        )
        return
    
    project_name = context.user_data.get('selected_project_name', 'Проект')
    salaries_text = f"💰 *СПИСОК ЗАРПЛАТ*\n\n*Проект:* {project_name}\n\n"
    
    total_amount = 0
    for i, (work_type, description, amount, work_date, date_added) in enumerate(salaries, 1):
        salaries_text += f"*{i}. {work_type}*\n"
        salaries_text += f"   Описание: {description}\n"
        salaries_text += f"   Сумма: {format_currency(amount)} руб.\n"
        salaries_text += f"   Дата работ: {work_date}\n"
        salaries_text += f"   Внесено: {datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')}\n\n"
        total_amount += amount
    
    salaries_text += f"*💰 ОБЩАЯ СУММА: {format_currency(total_amount)} руб.*"
    
    await query.edit_message_text(
        salaries_text,
        parse_mode='Markdown',
        reply_markup=back_button('salaries_menu')
    )

# ОБРАБОТЧИК ВЫБОРА ПРОЕКТА (для старых функций)
async def handle_project_selection(query, context, data):
    parts = data.split('_')
    action_type = parts[2]
    project_id = parts[3]
    
    conn = sqlite3.connect(config.DB_PATH)
    project = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    
    context.user_data['selected_project'] = project_id
    context.user_data['selected_project_name'] = project[0]
    
    if action_type == 'list_materials':
        await list_materials_handler(query, context)
    elif action_type == 'list_salaries':
        await list_salaries_handler(query, context)

# ОБНОВЛЕННЫЙ ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_access(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещен. Обратитесь к администратору.")
        return
        
    user_data = context.user_data
    text = update.message.text
    
    # Проверяем активные процессы шагового ввода
    for process_type in ['project', 'material', 'salary']:
        if process_type in context.user_data:
            process = context.user_data[process_type]
            step_data = process.get_current_step()
            
            # Обработка пользовательского ввода для select_text
            if step_data['type'] == 'select_text' and 'awaiting_custom_input' in context.user_data:
                process.data[step_data['key']] = text
                context.user_data.pop('awaiting_custom_input', None)
                
                if process.next_step():
                    await show_current_step(update, context, process_type)
                else:
                    await complete_step_process(update, context, process_type)
                return
            
            # Валидация в зависимости от типа поля
            if step_data['type'] == 'number':
                is_valid, value = validate_number(text)
                if not is_valid:
                    await update.message.reply_text(
                        "❌ Неверный формат числа! Введите положительное число:",
                        reply_markup=create_step_keyboard(step_data, context, process_type)
                    )
                    return
                process.data[step_data['key']] = value
                
            elif step_data['type'] == 'date':
                date_value = validate_date(text)
                if not date_value:
                    await update.message.reply_text(
                        "❌ Неверный формат даты! Введите ДД.ММ.ГГГГ:",
                        reply_markup=create_step_keyboard(step_data, context, process_type)
                    )
                    return
                process.data[step_data['key']] = date_value
                
            else:  # text
                process.data[step_data['key']] = text
            
            # Переход к следующему шагу или завершение
            if process.next_step():
                await show_current_step(update, context, process_type)
            else:
                await complete_step_process(update, context, process_type)
            return
    
    # Если нет активных процессов
    await update.message.reply_text(
        "🏢 *ООО «ИСК ГЕОСТРОЙ»*\n\nИспользуйте меню для навигации:",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

# ОБРАБОТЧИК РЕЗЕРВНОГО КОПИРОВАНИЯ
async def handle_backup(query, context):
    backup_file = await backup_database()
    if backup_file:
        await query.edit_message_text(
            f"✅ *Резервная копия создана успешно!*\n\n"
            f"Файл: `{backup_file}`\n\n"
            f"Резервная копия базы данных сохранена в папке backups.",
            parse_mode='Markdown',
            reply_markup=back_button('settings_menu')
        )
    else:
        await query.edit_message_text(
            "❌ *Ошибка при создании резервной копии!*\n\n"
            "Проверьте права доступа к файловой системе.",
            parse_mode='Markdown',
            reply_markup=back_button('settings_menu')
        )

# ОСНОВНОЙ ОБРАБОТЧИК КНОПОК
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update.effective_user.id):
        await query.edit_message_text("❌ Доступ запрещен. Обратитесь к администратору.")
        return
    
    data = query.data
    
    try:
        # Обработка шагового ввода
        if data.startswith('step_'):
            parts = data.split('_')
            action = parts[1]
            process_type = parts[2]
            
            if action == 'select':
                step = parts[3]
                value = parts[4]
                await handle_step_selection(query, context, process_type, step, value)
            
            elif action == 'quick':
                step = parts[3]
                value = parts[4]
                await handle_quick_input(query, context, process_type, step, value)
            
            elif action == 'calc':
                step = parts[3]
                hours = parts[4]
                await handle_calculation(query, context, process_type, step, hours)
            
            elif action == 'nav':
                direction = parts[3]
                await handle_step_navigation(query, context, process_type, direction)
            
            elif action == 'complete':
                await complete_step_process(query, context, process_type)
            
            elif action == 'skip':
                process = context.user_data[process_type]
                process.data[process.get_current_step()['key']] = None
                if process.next_step():
                    await show_current_step(query, context, process_type)
                else:
                    await complete_step_process(query, context, process_type)
            
            elif action == 'cancel':
                # Очистка данных процесса
                if process_type in context.user_data:
                    del context.user_data[process_type]
                if f'{process_type}_project' in context.user_data:
                    del context.user_data[f'{process_type}_project']
                
                await handle_main_menu(query, context)
            
            elif action == 'custom':
                step = parts[3]
                context.user_data['awaiting_custom_input'] = True
                await query.edit_message_text(
                    f"✏️ *Введите свой вариант для '{step}':*",
                    parse_mode='Markdown',
                    reply_markup=back_button(f'step_cancel_{process_type}')
                )
            
            elif action == 'calendar':
                # Здесь можно добавить календарь, но пока просто запросим ввод
                step = parts[3]
                context.user_data['awaiting_custom_input'] = True
                await query.edit_message_text(
                    f"📅 *Введите дату в формате ДД.ММ.ГГГГ:*",
                    parse_mode='Markdown',
                    reply_markup=back_button(f'step_cancel_{process_type}')
                )
        
        # Обработка выбора проекта для материалов/зарплат
        elif data.startswith('select_project_'):
            parts = data.split('_')
            target = parts[2]
            project_id = parts[3]
            
            if target == 'material':
                await handle_project_selection_material(query, context, project_id)
            elif target == 'salary':
                await handle_project_selection_salary(query, context, project_id)
            else:
                await handle_project_selection(query, context, data)
        
        # ГЛАВНОЕ МЕНЮ
        elif data == 'main_menu':
            await handle_main_menu(query, context)
        elif data == 'materials_menu':
            await handle_materials_menu(query, context)
        elif data == 'salaries_menu':
            await handle_salaries_menu(query, context)
        elif data == 'reports_menu':
            await handle_reports_menu(query, context)
        elif data == 'settings_menu':
            await handle_settings_menu(query, context)
        
        # ПРОЕКТЫ
        elif data == 'add_project':
            await add_project_handler(query, context)
        
        # МАТЕРИАЛЫ
        elif data == 'add_material':
            await add_material_handler(query, context)
        elif data == 'list_materials':
            await list_materials_handler(query, context)
        
        # ЗАРПЛАТЫ
        elif data == 'add_salary':
            await add_salary_handler(query, context)
        elif data == 'list_salaries':
            await list_salaries_handler(query, context)
        
        # НАСТРОЙКИ
        elif data == 'backup':
            await handle_backup(query, context)
        
        # СТАТИСТИКА (заглушки)
        elif data in ['general_stats', 'project_stats', 'period_stats', 'export_gsheets', 'export_excel']:
            await query.edit_message_text(
                f"📊 *Функция в разработке*\n\n"
                f"Раздел '{data}' находится в стадии разработки и будет доступен в ближайшее время.",
                parse_mode='Markdown',
                reply_markup=back_button('reports_menu')
            )
        
        # НАСТРОЙКИ (заглушки)
        elif data in ['user_management', 'rate_settings', 'notifications']:
            await query.edit_message_text(
                f"⚙️ *Функция в разработке*\n\n"
                f"Раздел '{data}' находится в стадии разработки и будет доступен в ближайшее время.",
                parse_mode='Markdown',
                reply_markup=back_button('settings_menu')
            )
        
        # ПОИСК И РЕДАКТИРОВАНИЕ (заглушки)
        elif data in ['search_materials', 'edit_material', 'delete_material',
                     'search_salaries', 'edit_salary', 'delete_salary']:
            await query.edit_message_text(
                f"🔧 *Функция в разработке*\n\n"
                f"Раздел '{data}' находится в стадии разработки и будет доступен в ближайшее время.",
                parse_mode='Markdown',
                reply_markup=back_button('main_menu')
            )
        
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка. Возврат в главное меню.",
            reply_markup=main_menu_keyboard()
        )

# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    error_text = (
        "❌ Произошла непредвиденная ошибка.\n"
        "Попробуйте еще раз или обратитесь к администратору."
    )
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(error_text)
    except:
        pass

# Основная функция
def main():
    if not config.validate():
        logger.error("Конфигурация не прошла валидацию! Завершение работы.")
        return
    
    init_db()
    
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_operation))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Добавление обработчика ошибок
    application.add_error_handler(error_handler)
    
    # Настройка периодических задач
    if config.ADMIN_IDS:
        job_queue = application.job_queue
        job_queue.run_daily(daily_report, time=time(hour=18, minute=0))  # 18:00 каждый день
        logger.info("Ежедневные отчеты активированы")
    
    logger.info("Бот ООО «ИСК ГЕОСТРОЙ» запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
