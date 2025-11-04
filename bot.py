import telebot
from telebot import types
import sqlite3
import datetime
import os
import logging
import re
import shutil
from typing import List, Tuple, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN', '8313764660:AAEOFtGphxmLLz7JKSa82a179-vTvjBu1lo')

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Утилиты для работы с БД
def db_execute(query: str, params: Tuple = ()) -> List[Tuple]:
    """Выполнить SQL запрос и вернуть результат"""
    try:
        conn = sqlite3.connect('construction_stats.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise

def db_execute_many(query: str, params_list: List[Tuple]) -> None:
    """Выполнить несколько SQL запросов"""
    try:
        conn = sqlite3.connect('construction_stats.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.executemany(query, params_list)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise

# Валидация данных
def is_valid_number(text: str) -> bool:
    """Проверить, является ли текст числом"""
    try:
        float(text)
        return True
    except ValueError:
        return False

def validate_russian_text(text: str) -> bool:
    """Проверить текст на кириллицу"""
    return bool(re.match("^[а-яА-ЯёЁ\s\-]+$", text))

def validate_date(text: str) -> bool:
    """Проверить формат даты YYYY-MM-DD"""
    try:
        datetime.datetime.strptime(text, '%Y-%m-%d')
        return True
    except ValueError:
        return False

# Резервное копирование
def backup_database() -> str:
    """Создать резервную копию базы данных"""
    try:
        if not os.path.exists('backups'):
            os.makedirs('backups')
        
        backup_name = f"backups/backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('construction_stats.db', backup_name)
        logger.info(f"Backup created: {backup_name}")
        return backup_name
    except Exception as e:
        logger.error(f"Backup error: {e}")
        raise

# Создание базы данных
def init_db():
    """Инициализация базы данных"""
    try:
        # Создаем резервную копию при старте
        if os.path.exists('construction_stats.db'):
            backup_database()
        
        # Таблица объектов
        db_execute('''
            CREATE TABLE IF NOT EXISTS objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                start_date TEXT,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Таблица материалов
        db_execute('''
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_id INTEGER,
                material_name TEXT NOT NULL,
                quantity REAL,
                unit TEXT,
                price_per_unit REAL,
                total_cost REAL,
                date TEXT,
                FOREIGN KEY (object_id) REFERENCES objects (id)
            )
        ''')
        
        # Таблица зарплат
        db_execute('''
            CREATE TABLE IF NOT EXISTS salaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_id INTEGER,
                worker_name TEXT NOT NULL,
                position TEXT,
                hours_worked REAL,
                hourly_rate REAL,
                total_salary REAL,
                date TEXT,
                FOREIGN KEY (object_id) REFERENCES objects (id)
            )
        ''')
        
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

# Инициализация БД при запуске
init_db()

# Утилиты для клавиатур
def create_back_button():
    """Создать клавиатуру с кнопкой Назад"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⬅️ Назад'))
    return markup

def main_menu(chat_id):
    """Главное меню"""
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('🏗️ Объекты')
        btn2 = types.KeyboardButton('📦 Материалы')
        btn3 = types.KeyboardButton('💵 Зарплаты')
        btn4 = types.KeyboardButton('📊 Статистика')
        btn5 = types.KeyboardButton('🆘 Помощь')
        markup.add(btn1, btn2, btn3, btn4, btn5)
        bot.send_message(chat_id, "Выберите раздел:", reply_markup=markup)
        logger.info(f"Main menu shown for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in main_menu: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при отображении меню")

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    try:
        welcome_text = """
🏗️ Добро пожаловать в бот для учета строительной статистики!

Возможности:
• Учет объектов строительства
• Ведение расходов на материалы
• Учет зарплат сотрудников
• Полная статистика по проектам

Выберите раздел в меню ниже 👇
        """
        bot.send_message(message.chat.id, welcome_text)
        main_menu(message.chat.id)
        logger.info(f"Start command from user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске бота")

# Обработчик команды /help
@bot.message_handler(commands=['help'])
def help_command(message):
    """Обработчик команды /help"""
    try:
        help_text = """
📋 Доступные команды:

/start - Начало работы
/help - Эта справка
/backup - Создать резервную копию (только для администратора)

Основные разделы:
🏗️ Объекты - управление строительными объектами
📦 Материалы - учет материалов и расходов
💵 Зарплаты - учет выплат сотрудникам
📊 Статистика - общая статистика по проектам

Как пользоваться:
1. Сначала создайте объект в разделе "🏗️ Объекты"
2. Добавляйте материалы и зарплаты для объектов
3. Просматривайте статистику в соответствующих разделах

Для начала работы нажмите /start
        """
        bot.send_message(message.chat.id, help_text)
        logger.info(f"Help command from user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in help_command: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при отображении справки")

# Обработчик команды /backup
@bot.message_handler(commands=['backup'])
def backup_command(message):
    """Создание резервной копии базы данных"""
    try:
        # Здесь можно добавить проверку прав администратора
        backup_path = backup_database()
        bot.send_message(message.chat.id, f"✅ Резервная копия создана: {backup_path}")
        logger.info(f"Backup created by user {message.from_user.id}")
    except Exception as e:
        error_msg = f"❌ Ошибка при создании резервной копии: {str(e)}"
        bot.send_message(message.chat.id, error_msg)
        logger.error(f"Backup error: {e}")

# Обработчик текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    """Обработчик текстовых сообщений"""
    try:
        chat_id = message.chat.id
        text = message.text
        
        if text == '🏗️ Объекты':
            objects_menu(chat_id)
        elif text == '📦 Материалы':
            materials_menu(chat_id)
        elif text == '💵 Зарплаты':
            salaries_menu(chat_id)
        elif text == '📊 Статистика':
            show_statistics(chat_id)
        elif text == '🆘 Помощь':
            help_command(message)
        elif text == '⬅️ Назад':
            main_menu(chat_id)
        else:
            # Обработка динамических кнопок
            handle_dynamic_buttons(message)
            
    except Exception as e:
        logger.error(f"Error in handle_text: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке запроса")

def handle_dynamic_buttons(message):
    """Обработка динамически созданных кнопок"""
    try:
        text = message.text
        
        if text.startswith('DEL_OBJ_'):
            delete_object_confirm(message)
        elif text.startswith('OBJ_'):
            add_material_object(message)
        elif text.startswith('SAL_OBJ_'):
            add_salary_object(message)
        else:
            bot.send_message(message.chat.id, "❌ Неизвестная команда. Используйте меню.")
            
    except Exception as e:
        logger.error(f"Error in handle_dynamic_buttons: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обработке команды")

# Меню объектов
def objects_menu(chat_id):
    """Меню управления объектами"""
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('➕ Добавить объект')
        btn2 = types.KeyboardButton('📋 Список объектов')
        btn3 = types.KeyboardButton('❌ Удалить объект')
        btn4 = types.KeyboardButton('⬅️ Назад')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(chat_id, "Управление объектами:", reply_markup=markup)
        logger.info(f"Objects menu shown for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in objects_menu: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при отображении меню объектов")

# Меню материалов
def materials_menu(chat_id):
    """Меню управления материалами"""
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('📥 Добавить материал')
        btn2 = types.KeyboardButton('📋 Расходы на материалы')
        btn3 = types.KeyboardButton('📊 Статистика материалов')
        btn4 = types.KeyboardButton('⬅️ Назад')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(chat_id, "Управление материалами:", reply_markup=markup)
        logger.info(f"Materials menu shown for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in materials_menu: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при отображении меню материалов")

# Меню зарплат
def salaries_menu(chat_id):
    """Меню управления зарплатами"""
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('👤 Добавить зарплату')
        btn2 = types.KeyboardButton('📋 Выплаты зарплат')
        btn3 = types.KeyboardButton('📊 Статистика зарплат')
        btn4 = types.KeyboardButton('⬅️ Назад')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(chat_id, "Управление зарплатами:", reply_markup=markup)
        logger.info(f"Salaries menu shown for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in salaries_menu: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при отображении меню зарплат")

# Обработчики для объектов
@bot.message_handler(func=lambda message: message.text == '➕ Добавить объект')
def add_object_start(message):
    """Начало добавления объекта"""
    try:
        msg = bot.send_message(message.chat.id, "Введите название объекта:")
        bot.register_next_step_handler(msg, add_object_name)
        logger.info(f"User {message.from_user.id} started adding object")
    except Exception as e:
        logger.error(f"Error in add_object_start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при начале добавления объекта")

def add_object_name(message):
    """Обработка названия объекта"""
    try:
        object_name = message.text.strip()
        if not object_name:
            msg = bot.send_message(message.chat.id, "❌ Название не может быть пустым. Введите название объекта:")
            bot.register_next_step_handler(msg, add_object_name)
            return
            
        msg = bot.send_message(message.chat.id, "Введите адрес объекта:")
        bot.register_next_step_handler(msg, add_object_address, object_name)
    except Exception as e:
        logger.error(f"Error in add_object_name: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке названия объекта")

def add_object_address(message, object_name):
    """Обработка адреса объекта"""
    try:
        address = message.text.strip()
        if not address:
            msg = bot.send_message(message.chat.id, "❌ Адрес не может быть пустым. Введите адрес объекта:")
            bot.register_next_step_handler(msg, add_object_address, object_name)
            return
            
        start_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        db_execute('INSERT INTO objects (name, address, start_date) VALUES (?, ?, ?)', 
                   (object_name, address, start_date))
        
        bot.send_message(message.chat.id, f"✅ Объект '{object_name}' успешно добавлен!")
        logger.info(f"User {message.from_user.id} added object: {object_name}")
        objects_menu(message.chat.id)
    except Exception as e:
        logger.error(f"Error in add_object_address: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при добавлении объекта")

@bot.message_handler(func=lambda message: message.text == '📋 Список объектов')
def list_objects(message):
    """Показать список объектов"""
    try:
        objects = db_execute('SELECT id, name, address, start_date FROM objects WHERE status = "active"')
        
        if not objects:
            bot.send_message(message.chat.id, "📭 Нет активных объектов")
            return
        
        response = "🏗️ Список объектов:\n\n"
        for obj in objects:
            response += f"ID: {obj[0]}\n"
            response += f"Название: {obj[1]}\n"
            response += f"Адрес: {obj[2]}\n"
            response += f"Дата начала: {obj[3]}\n"
            response += "─" * 20 + "\n"
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed objects list")
    except Exception as e:
        logger.error(f"Error in list_objects: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении списка объектов")

@bot.message_handler(func=lambda message: message.text == '❌ Удалить объект')
def delete_object_start(message):
    """Начало удаления объекта"""
    try:
        objects = db_execute('SELECT id, name FROM objects WHERE status = "active"')
        
        if not objects:
            bot.send_message(message.chat.id, "❌ Нет активных объектов для удаления")
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for obj in objects:
            markup.add(types.KeyboardButton(f"DEL_OBJ_{obj[0]}_{obj[1]}"))
        markup.add(types.KeyboardButton('⬅️ Назад'))
        
        msg = bot.send_message(message.chat.id, "Выберите объект для удаления:", reply_markup=markup)
        logger.info(f"User {message.from_user.id} started object deletion")
    except Exception as e:
        logger.error(f"Error in delete_object_start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при начале удаления объекта")

def delete_object_confirm(message):
    """Подтверждение удаления объекта"""
    try:
        if message.text == '⬅️ Назад':
            objects_menu(message.chat.id)
            return
        
        object_id = int(message.text.split('_')[2])
        object_name = '_'.join(message.text.split('_')[3:])
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(types.KeyboardButton('✅ Да'), types.KeyboardButton('❌ Нет'))
        
        msg = bot.send_message(message.chat.id, 
                              f"Вы уверены, что хотите удалить объект '{object_name}'?",
                              reply_markup=markup)
        bot.register_next_step_handler(msg, delete_object_final, object_id, object_name)
    except Exception as e:
        logger.error(f"Error in delete_object_confirm: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def delete_object_final(message, object_id, object_name):
    """Финальное удаление объекта"""
    try:
        if message.text == '✅ Да':
            db_execute('UPDATE objects SET status = "inactive" WHERE id = ?', (object_id,))
            bot.send_message(message.chat.id, f"✅ Объект '{object_name}' удален!")
            logger.info(f"User {message.from_user.id} deleted object: {object_name}")
        else:
            bot.send_message(message.chat.id, "❌ Удаление отменено")
        
        objects_menu(message.chat.id)
    except Exception as e:
        logger.error(f"Error in delete_object_final: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при удалении объекта")

# Обработчики для материалов
@bot.message_handler(func=lambda message: message.text == '📥 Добавить материал')
def add_material_start(message):
    """Начало добавления материала"""
    try:
        objects = db_execute('SELECT id, name FROM objects WHERE status = "active"')
        
        if not objects:
            bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект.")
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for obj in objects:
            markup.add(types.KeyboardButton(f"OBJ_{obj[0]}_{obj[1]}"))
        markup.add(types.KeyboardButton('⬅️ Назад'))
        
        msg = bot.send_message(message.chat.id, "Выберите объект:", reply_markup=markup)
        logger.info(f"User {message.from_user.id} started adding material")
    except Exception as e:
        logger.error(f"Error in add_material_start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при начале добавления материала")

def add_material_object(message):
    """Обработка выбора объекта для материала"""
    try:
        if message.text == '⬅️ Назад':
            materials_menu(message.chat.id)
            return
        
        object_id = int(message.text.split('_')[1])
        msg = bot.send_message(message.chat.id, "Введите название материала:")
        bot.register_next_step_handler(msg, add_material_name, object_id)
    except Exception as e:
        logger.error(f"Error in add_material_object: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def add_material_name(message, object_id):
    """Обработка названия материала"""
    try:
        material_name = message.text.strip()
        if not material_name:
            msg = bot.send_message(message.chat.id, "❌ Название не может быть пустым. Введите название материала:")
            bot.register_next_step_handler(msg, add_material_name, object_id)
            return
            
        msg = bot.send_message(message.chat.id, "Введите количество:")
        bot.register_next_step_handler(msg, add_material_quantity, object_id, material_name)
    except Exception as e:
        logger.error(f"Error in add_material_name: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке названия материала")

def add_material_quantity(message, object_id, material_name):
    """Обработка количества материала"""
    try:
        if not is_valid_number(message.text):
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число для количества:")
            bot.register_next_step_handler(msg, add_material_quantity, object_id, material_name)
            return
            
        quantity = float(message.text)
        msg = bot.send_message(message.chat.id, "Введите единицу измерения (шт, кг, м и т.д.):")
        bot.register_next_step_handler(msg, add_material_unit, object_id, material_name, quantity)
    except Exception as e:
        logger.error(f"Error in add_material_quantity: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке количества")

def add_material_unit(message, object_id, material_name, quantity):
    """Обработка единицы измерения"""
    try:
        unit = message.text.strip()
        if not unit:
            msg = bot.send_message(message.chat.id, "❌ Единица измерения не может быть пустой. Введите единицу измерения:")
            bot.register_next_step_handler(msg, add_material_unit, object_id, material_name, quantity)
            return
            
        msg = bot.send_message(message.chat.id, "Введите цену за единицу:")
        bot.register_next_step_handler(msg, add_material_price, object_id, material_name, quantity, unit)
    except Exception as e:
        logger.error(f"Error in add_material_unit: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке единицы измерения")

def add_material_price(message, object_id, material_name, quantity, unit):
    """Обработка цены материала и сохранение"""
    try:
        if not is_valid_number(message.text):
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число для цены:")
            bot.register_next_step_handler(msg, add_material_price, object_id, material_name, quantity, unit)
            return
            
        price_per_unit = float(message.text)
        total_cost = quantity * price_per_unit
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        db_execute('''
            INSERT INTO materials (object_id, material_name, quantity, unit, price_per_unit, total_cost, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (object_id, material_name, quantity, unit, price_per_unit, total_cost, date))
        
        bot.send_message(message.chat.id, f"✅ Материал '{material_name}' добавлен!\n"
                         f"Сумма: {total_cost:.2f} руб.")
        logger.info(f"User {message.from_user.id} added material: {material_name} for {total_cost} rub")
        materials_menu(message.chat.id)
    except Exception as e:
        logger.error(f"Error in add_material_price: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при добавлении материала")

@bot.message_handler(func=lambda message: message.text == '📋 Расходы на материалы')
def show_materials_expenses(message):
    """Показать расходы на материалы"""
    try:
        materials = db_execute('''
            SELECT o.name, m.material_name, m.quantity, m.unit, m.total_cost, m.date
            FROM materials m
            JOIN objects o ON m.object_id = o.id
            ORDER BY m.date DESC
            LIMIT 20
        ''')
        
        if not materials:
            bot.send_message(message.chat.id, "📭 Нет данных о материалах")
            return
        
        response = "📦 ПОСЛЕДНИЕ РАСХОДЫ НА МАТЕРИАЛЫ:\n\n"
        total = 0
        for mat in materials:
            response += f"🏗️ {mat[0]}\n"
            response += f"📝 {mat[1]}: {mat[2]} {mat[3]}\n"
            response += f"💰 {mat[4]:.2f} руб.\n"
            response += f"📅 {mat[5]}\n"
            response += "─" * 20 + "\n"
            total += mat[4]
        
        response += f"\n💰 ОБЩАЯ СУММА: {total:.2f} руб."
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed materials expenses")
    except Exception as e:
        logger.error(f"Error in show_materials_expenses: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении расходов на материалы")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика материалов')
def show_materials_statistics(message):
    """Показать статистику материалов"""
    try:
        stats = db_execute('''
            SELECT material_name, SUM(quantity), unit, SUM(total_cost)
            FROM materials 
            GROUP BY material_name, unit
            ORDER BY SUM(total_cost) DESC
        ''')
        
        if not stats:
            bot.send_message(message.chat.id, "📭 Нет данных о материалах")
            return
        
        response = "📊 СТАТИСТИКА МАТЕРИАЛОВ:\n\n"
        total_cost = 0
        
        for stat in stats:
            response += f"📝 {stat[0]}\n"
            response += f"   Количество: {stat[1]} {stat[2]}\n"
            response += f"   Сумма: {stat[3]:.2f} руб.\n"
            response += "─" * 20 + "\n"
            total_cost += stat[3]
        
        response += f"\n💰 ОБЩАЯ СУММА: {total_cost:.2f} руб."
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed materials statistics")
    except Exception as e:
        logger.error(f"Error in show_materials_statistics: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении статистики материалов")

# Обработчики для зарплат
@bot.message_handler(func=lambda message: message.text == '👤 Добавить зарплату')
def add_salary_start(message):
    """Начало добавления зарплаты"""
    try:
        objects = db_execute('SELECT id, name FROM objects WHERE status = "active"')
        
        if not objects:
            bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект.")
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for obj in objects:
            markup.add(types.KeyboardButton(f"SAL_OBJ_{obj[0]}_{obj[1]}"))
        markup.add(types.KeyboardButton('⬅️ Назад'))
        
        msg = bot.send_message(message.chat.id, "Выберите объект:", reply_markup=markup)
        logger.info(f"User {message.from_user.id} started adding salary")
    except Exception as e:
        logger.error(f"Error in add_salary_start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при начале добавления зарплаты")

def add_salary_object(message):
    """Обработка выбора объекта для зарплаты"""
    try:
        if message.text == '⬅️ Назад':
            salaries_menu(message.chat.id)
            return
        
        object_id = int(message.text.split('_')[2])
        msg = bot.send_message(message.chat.id, "Введите ФИО работника:")
        bot.register_next_step_handler(msg, add_salary_worker, object_id)
    except Exception as e:
        logger.error(f"Error in add_salary_object: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def add_salary_worker(message, object_id):
    """Обработка ФИО работника"""
    try:
        worker_name = message.text.strip()
        if not worker_name:
            msg = bot.send_message(message.chat.id, "❌ ФИО не может быть пустым. Введите ФИО работника:")
            bot.register_next_step_handler(msg, add_salary_worker, object_id)
            return
            
        msg = bot.send_message(message.chat.id, "Введите должность:")
        bot.register_next_step_handler(msg, add_salary_position, object_id, worker_name)
    except Exception as e:
        logger.error(f"Error in add_salary_worker: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке ФИО работника")

def add_salary_position(message, object_id, worker_name):
    """Обработка должности"""
    try:
        position = message.text.strip()
        if not position:
            msg = bot.send_message(message.chat.id, "❌ Должность не может быть пустой. Введите должность:")
            bot.register_next_step_handler(msg, add_salary_position, object_id, worker_name)
            return
            
        msg = bot.send_message(message.chat.id, "Введите количество отработанных часов:")
        bot.register_next_step_handler(msg, add_salary_hours, object_id, worker_name, position)
    except Exception as e:
        logger.error(f"Error in add_salary_position: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке должности")

def add_salary_hours(message, object_id, worker_name, position):
    """Обработка отработанных часов"""
    try:
        if not is_valid_number(message.text):
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число часов:")
            bot.register_next_step_handler(msg, add_salary_hours, object_id, worker_name, position)
            return
            
        hours_worked = float(message.text)
        msg = bot.send_message(message.chat.id, "Введите ставку за час (руб.):")
        bot.register_next_step_handler(msg, add_salary_rate, object_id, worker_name, position, hours_worked)
    except Exception as e:
        logger.error(f"Error in add_salary_hours: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при обработке часов")

def add_salary_rate(message, object_id, worker_name, position, hours_worked):
    """Обработка ставки и сохранение зарплаты"""
    try:
        if not is_valid_number(message.text):
            msg = bot.send_message(message.chat.id, "❌ Введите корректное число для ставки:")
            bot.register_next_step_handler(msg, add_salary_rate, object_id, worker_name, position, hours_worked)
            return
            
        hourly_rate = float(message.text)
        total_salary = hours_worked * hourly_rate
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        db_execute('''
            INSERT INTO salaries (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date))
        
        bot.send_message(message.chat.id, f"✅ Зарплата для {worker_name} добавлена!\n"
                         f"Сумма: {total_salary:.2f} руб.")
        logger.info(f"User {message.from_user.id} added salary for {worker_name}: {total_salary} rub")
        salaries_menu(message.chat.id)
    except Exception as e:
        logger.error(f"Error in add_salary_rate: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при добавлении зарплаты")

@bot.message_handler(func=lambda message: message.text == '📋 Выплаты зарплат')
def show_salaries_expenses(message):
    """Показать выплаты зарплат"""
    try:
        salaries = db_execute('''
            SELECT o.name, s.worker_name, s.position, s.hours_worked, s.total_salary, s.date
            FROM salaries s
            JOIN objects o ON s.object_id = o.id
            ORDER BY s.date DESC
            LIMIT 20
        ''')
        
        if not salaries:
            bot.send_message(message.chat.id, "📭 Нет данных о зарплатах")
            return
        
        response = "💵 ПОСЛЕДНИЕ ВЫПЛАТЫ ЗАРПЛАТ:\n\n"
        total = 0
        for sal in salaries:
            response += f"🏗️ {sal[0]}\n"
            response += f"👤 {sal[1]} ({sal[2]})\n"
            response += f"⏱️ {sal[3]} часов\n"
            response += f"💰 {sal[4]:.2f} руб.\n"
            response += f"📅 {sal[5]}\n"
            response += "─" * 20 + "\n"
            total += sal[4]
        
        response += f"\n💰 ОБЩАЯ СУММА: {total:.2f} руб."
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed salaries expenses")
    except Exception as e:
        logger.error(f"Error in show_salaries_expenses: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении выплат зарплат")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика зарплат')
def show_salaries_statistics(message):
    """Показать статистику зарплат"""
    try:
        stats = db_execute('''
            SELECT worker_name, position, SUM(hours_worked), SUM(total_salary)
            FROM salaries 
            GROUP BY worker_name, position
            ORDER BY SUM(total_salary) DESC
        ''')
        
        if not stats:
            bot.send_message(message.chat.id, "📭 Нет данных о зарплатах")
            return
        
        response = "📊 СТАТИСТИКА ЗАРПЛАТ:\n\n"
        total_hours = 0
        total_salary = 0
        
        for stat in stats:
            response += f"👤 {stat[0]} ({stat[1]})\n"
            response += f"   Часы: {stat[2]}\n"
            response += f"   Зарплата: {stat[3]:.2f} руб.\n"
            response += "─" * 20 + "\n"
            total_hours += stat[2]
            total_salary += stat[3]
        
        response += f"\n📈 ИТОГО:\n"
        response += f"   Общее время: {total_hours} часов\n"
        response += f"   Общая сумма: {total_salary:.2f} руб."
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed salaries statistics")
    except Exception as e:
        logger.error(f"Error in show_salaries_statistics: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении статистики зарплат")

# Показать статистику
@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_statistics(message):
    """Показать общую статистику"""
    try:
        # Общая статистика
        objects_count = db_execute('SELECT COUNT(*) FROM objects WHERE status = "active"')[0][0]
        total_materials = db_execute('SELECT SUM(total_cost) FROM materials')[0][0] or 0
        total_salaries = db_execute('SELECT SUM(total_salary) FROM salaries')[0][0] or 0
        total_expenses = total_materials + total_salaries
        
        response = "📊 ОБЩАЯ СТАТИСТИКА\n\n"
        response += f"🏗️ Активных объектов: {objects_count}\n"
        response += f"📦 Общие расходы на материалы: {total_materials:.2f} руб.\n"
        response += f"💵 Общие расходы на зарплаты: {total_salaries:.2f} руб.\n"
        response += f"💰 Общие расходы: {total_expenses:.2f} руб.\n\n"
        
        # Статистика по объектам
        objects_stats = db_execute('''
            SELECT o.name, 
                   COALESCE(SUM(m.total_cost), 0) as materials_cost,
                   COALESCE(SUM(s.total_salary), 0) as salaries_cost
            FROM objects o
            LEFT JOIN materials m ON o.id = m.object_id
            LEFT JOIN salaries s ON o.id = s.object_id
            WHERE o.status = 'active'
            GROUP BY o.id, o.name
        ''')
        
        if objects_stats:
            response += "📈 СТАТИСТИКА ПО ОБЪЕКТАМ:\n"
            for obj in objects_stats:
                response += f"\n🏗️ {obj[0]}:\n"
                response += f"   Материалы: {obj[1]:.2f} руб.\n"
                response += f"   Зарплаты: {obj[2]:.2f} руб.\n"
                response += f"   Всего: {obj[1] + obj[2]:.2f} руб.\n"
        
        bot.send_message(message.chat.id, response)
        logger.info(f"User {message.from_user.id} viewed general statistics")
    except Exception as e:
        logger.error(f"Error in show_statistics: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при получении статистики")

# Запуск бота с обработкой исключений
if __name__ == "__main__":
    logger.info("Бот запущен...")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            logger.error(f"Ошибка в работе бота: {e}")
            import time
            time.sleep(15)
            logger.info("Перезапуск бота...")
