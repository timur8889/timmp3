import telebot
from telebot import types
import sqlite3
import datetime
import os
import logging
import re
import shutil
import time
import decimal
from typing import List, Tuple, Optional, Dict, Any
from dotenv import load_dotenv
from functools import lru_cache
from threading import Lock, Thread
from collections import defaultdict

# Загрузка переменных окружения
load_dotenv()

# Конфигурация и константы
class Config:
    DB_PATH = 'construction_stats.db'
    BACKUP_DIR = 'backups'
    LOGS_DIR = 'logs'
    MAX_MESSAGE_LENGTH = 4096
    DEFAULT_DATE_FORMAT = '%Y-%m-%d'
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    BACKUP_INTERVAL = 24 * 60 * 60  # 24 часа в секундах
    STATE_TIMEOUT = 300  # 5 минут
    CACHE_TTL = 300  # 5 минут

class Messages:
    WELCOME = """
🏗️ Добро пожаловать в Construction Manager Bot!

✨ Возможности:
• 📍 Учет объектов строительства
• 📦 Ведение расходов на материалов
• 👥 Учет зарплат сотрудников
• 📊 Полная статистика по проектам
• 📤 Экспорт данных в удобном формате

🎯 Выберите раздел в меню ниже 👇
    """
    
    HELP = """
📋 Доступные команды:

/start - Начало работы
/help - Эта справка
/cancel - Отмена текущей операции
/admin - Панель администратора (только для админов)

🎮 Основные разделы:
🏗️ Объекты - управление строительными объектами
📦 Материалы - учет материалов и расходов
💵 Зарплаты - учет выплат сотрудникам
📊 Статистика - общая статистика по проектам
📤 Экспорт данных - выгрузка данных в текстовом формате

📝 Как пользоваться:
1. 🏗️ Сначала создайте объект в разделе "Объекты"
2. 📦 Добавляйте материалы и зарплаты для объектов
3. 📊 Просматривайте статистику в соответствующих разделах
4. 📤 Экспортируйте данные для отчетности

🚀 Для начала работы нажмите /start
    """
    
    ERROR = "❌ Произошла непредвиденная ошибка. Попробуйте позже."
    OPERATION_CANCELLED = "❌ Операция отменена"
    ACCESS_DENIED = "❌ Доступ запрещен"
    INVALID_COMMAND = "❌ Неизвестная команда. Используйте меню."

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{Config.LOGS_DIR}/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Безопасное получение токена
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    exit(1)

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Класс для управления состоянием пользователя с таймаутами
class UserState:
    """Улучшенный класс для отслеживания состояния пользователя с таймаутами"""
    _states = {}
    _timeouts = {}
    
    @classmethod
    def set_state(cls, user_id: int, state: str, data: Optional[Dict] = None, timeout: int = Config.STATE_TIMEOUT):
        cls._states[user_id] = {
            'state': state, 
            'data': data or {},
            'timestamp': datetime.datetime.now()
        }
        cls._timeouts[user_id] = timeout
        logger.info(f"State set for user {user_id}: {state}")
    
    @classmethod
    def get_state(cls, user_id: int) -> Optional[Dict]:
        state_data = cls._states.get(user_id)
        if state_data:
            # Проверяем таймаут
            timeout = cls._timeouts.get(user_id, Config.STATE_TIMEOUT)
            time_diff = (datetime.datetime.now() - state_data['timestamp']).seconds
            if time_diff > timeout:
                cls.clear_state(user_id)
                return None
        return state_data
    
    @classmethod
    def clear_state(cls, user_id: int):
        cls._states.pop(user_id, None)
        cls._timeouts.pop(user_id, None)
        logger.info(f"State cleared for user {user_id}")
    
    @classmethod
    def cleanup_expired(cls):
        """Очистка просроченных состояний"""
        now = datetime.datetime.now()
        expired_users = []
        
        for user_id, state_data in cls._states.items():
            timeout = cls._timeouts.get(user_id, Config.STATE_TIMEOUT)
            time_diff = (now - state_data['timestamp']).seconds
            if time_diff > timeout:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            cls.clear_state(user_id)
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired states")

# Класс для работы с базой данных с улучшениями
class DatabaseManager:
    """Улучшенный менеджер для работы с базой данных"""
    
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self._init_directories()
        self._init_tables()
        
    def _init_directories(self):
        """Инициализация необходимых директорий"""
        for directory in [Config.BACKUP_DIR, Config.LOGS_DIR]:
            os.makedirs(directory, exist_ok=True)
        
    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def execute_query(self, query: str, params: Tuple = (), fetch: bool = True):
        """Выполнить запрос с обработкой ошибок"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch:
                result = cursor.fetchall()
            else:
                result = None
                
            conn.commit()
            return result
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Инициализация всех таблиц с улучшенной схемой"""
        tables = {
            'objects': '''
                CREATE TABLE IF NOT EXISTS objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    address TEXT,
                    start_date TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''',
            'materials': '''
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id INTEGER,
                    material_name TEXT NOT NULL,
                    quantity REAL,
                    unit TEXT,
                    price_per_unit REAL,
                    total_cost REAL,
                    date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (object_id) REFERENCES objects (id) ON DELETE CASCADE
                )
            ''',
            'salaries': '''
                CREATE TABLE IF NOT EXISTS salaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id INTEGER,
                    worker_name TEXT NOT NULL,
                    position TEXT,
                    hours_worked REAL,
                    hourly_rate REAL,
                    total_salary REAL,
                    date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (object_id) REFERENCES objects (id) ON DELETE CASCADE
                )
            '''
        }
        
        try:
            for table_name, schema in tables.items():
                self.execute_query(schema, fetch=False)
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

# Класс для кэширования статистики
class CachedStatistics:
    """Кэширование статистических данных"""
    
    def __init__(self):
        self._cache = {}
        self._cache_timestamps = {}
        self._lock = Lock()
    
    def get_cached_data(self, cache_key: str, ttl: int = Config.CACHE_TTL):
        """Получить данные из кэша"""
        with self._lock:
            if cache_key in self._cache:
                timestamp = self._cache_timestamps.get(cache_key)
                if timestamp and (datetime.datetime.now() - timestamp).seconds < ttl:
                    return self._cache[cache_key]
            return None
    
    def set_cached_data(self, cache_key: str, data: Any):
        """Сохранить данные в кэш"""
        with self._lock:
            self._cache[cache_key] = data
            self._cache_timestamps[cache_key] = datetime.datetime.now()
    
    def clear_cache(self, cache_key: str = None):
        """Очистить кэш"""
        with self._lock:
            if cache_key:
                self._cache.pop(cache_key, None)
                self._cache_timestamps.pop(cache_key, None)
            else:
                self._cache.clear()
                self._cache_timestamps.clear()

# Менеджер уведомлений
class NotificationManager:
    """Менеджер уведомлений и отчетов"""
    
    @staticmethod
    def send_daily_report(bot_instance, chat_id: int = None):
        """Отправка ежедневного отчета"""
        try:
            db = DatabaseManager()
            
            # Статистика за сегодня
            today = datetime.datetime.now().strftime(Config.DEFAULT_DATE_FORMAT)
            
            daily_materials = db.execute_query(
                'SELECT SUM(total_cost) FROM materials WHERE date = ?', 
                (today,)
            )[0][0] or 0
            
            daily_salaries = db.execute_query(
                'SELECT SUM(total_salary) FROM salaries WHERE date = ?', 
                (today,)
            )[0][0] or 0
            
            daily_total = daily_materials + daily_salaries
            
            report = f"""
📊 ЕЖЕДНЕВНЫЙ ОТЧЕТ
📅 {datetime.datetime.now().strftime('%d.%m.%Y')}

📦 Расходы на материалы: {daily_materials:.2f} руб.
💵 Расходы на зарплаты: {daily_salaries:.2f} руб.
💰 Итого за день: {daily_total:.2f} руб.

🏗️ Успешной работы!
            """
            
            if chat_id:
                bot_instance.send_message(chat_id, report)
            else:
                # Здесь можно добавить отправку администраторам
                admin_ids = os.getenv('ADMIN_IDS', '').split(',')
                for admin_id in admin_ids:
                    if admin_id.strip():
                        try:
                            bot_instance.send_message(int(admin_id.strip()), report)
                        except Exception as e:
                            logger.error(f"Error sending report to admin {admin_id}: {e}")
            
            logger.info(f"Daily report sent: Materials: {daily_materials}, Salaries: {daily_salaries}")
            
        except Exception as e:
            logger.error(f"Error in daily report: {e}")

# Утилиты для валидации
class Validators:
    """Класс с методами валидации"""
    
    @staticmethod
    def is_valid_number(text: str) -> bool:
        """Проверить, является ли текст числом"""
        try:
            float(text)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_russian_text(text: str, min_length: int = 2) -> bool:
        """Проверка русского текста"""
        if not text or len(text.strip()) < min_length:
            return False
        pattern = r'^[а-яА-ЯёЁ0-9\s\-\.,!?()":;]+$'
        return bool(re.match(pattern, text))

    @staticmethod
    def validate_date(date_text: str) -> bool:
        """Проверка корректности даты"""
        try:
            datetime.datetime.strptime(date_text, Config.DEFAULT_DATE_FORMAT)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_phone_number(phone: str) -> bool:
        """Проверка номера телефона"""
        pattern = r'^\+?[1-9]\d{1,14}$'
        return bool(re.match(pattern, phone))

    @staticmethod
    def validate_email(email: str) -> bool:
        """Проверка email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_decimal(value: str, max_digits: int = 10, decimal_places: int = 2) -> bool:
        """Проверка десятичного числа"""
        try:
            decimal_value = decimal.Decimal(value)
            if decimal_value.as_tuple().exponent < -decimal_places:
                return False
            if len(str(decimal_value).replace('.', '').replace('-', '')) > max_digits:
                return False
            return True
        except:
            return False

# Утилиты для пагинации
class PaginationUtils:
    """Утилиты для работы с пагинацией"""
    
    @staticmethod
    def send_paginated_message(bot_instance, chat_id: int, text: str, page_size: int = Config.MAX_MESSAGE_LENGTH):
        """Отправка сообщения с пагинацией"""
        if len(text) <= page_size:
            bot_instance.send_message(chat_id, f"<pre>{text}</pre>", parse_mode='HTML')
            return
        
        parts = [text[i:i+page_size] for i in range(0, len(text), page_size)]
        for i, part in enumerate(parts, 1):
            bot_instance.send_message(
                chat_id, 
                f"<pre>{part}</pre>\n\n📄 Страница {i}/{len(parts)}", 
                parse_mode='HTML'
            )

# Инициализация менеджеров
db = DatabaseManager()
stats_cache = CachedStatistics()
notification_manager = NotificationManager()

# Декораторы для безопасности и логирования
def safe_execute(func):
    """Декоратор для безопасного выполнения функций"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            if len(args) > 0 and hasattr(args[0], 'chat'):
                bot.send_message(args[0].chat.id, Messages.ERROR)
            return None
    return wrapper

def log_message(func):
    """Декоратор для логирования сообщений"""
    def wrapper(message):
        logger.info(f"User {message.from_user.id} ({message.from_user.username}) sent: {message.text}")
        return func(message)
    return wrapper

def admin_required(func):
    """Декоратор для проверки прав администратора"""
    def wrapper(message):
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        if str(message.from_user.id) not in admin_ids:
            bot.send_message(message.chat.id, Messages.ACCESS_DENIED)
            return
        return func(message)
    return wrapper

# Резервное копирование
def backup_database() -> str:
    """Создать резервную копию базы данных"""
    try:
        backup_name = f"{Config.BACKUP_DIR}/backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(Config.DB_PATH, backup_name)
        
        # Удаляем старые бэкапы (оставляем последние 10)
        backups = sorted([f for f in os.listdir(Config.BACKUP_DIR) if f.startswith('backup_')])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(Config.BACKUP_DIR, old_backup))
        
        logger.info(f"Backup created: {backup_name}")
        return backup_name
    except Exception as e:
        logger.error(f"Backup error: {e}")
        raise

# Фоновые задачи
class BackgroundTasks:
    """Управление фоновыми задачами"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.running = False
    
    def start(self):
        """Запуск фоновых задач"""
        self.running = True
        
        # Задача очистки состояний
        def cleanup_states():
            while self.running:
                try:
                    UserState.cleanup_expired()
                    time.sleep(60)  # Проверка каждую минуту
                except Exception as e:
                    logger.error(f"Error in cleanup_states: {e}")
        
        # Задача резервного копирования
        def backup_task():
            while self.running:
                try:
                    # Резервное копирование каждый день в 2:00
                    now = datetime.datetime.now()
                    if now.hour == 2 and now.minute == 0:
                        backup_database()
                    time.sleep(60)  # Проверка каждую минуту
                except Exception as e:
                    logger.error(f"Error in backup_task: {e}")
        
        # Задача ежедневных отчетов
        def daily_reports():
            while self.running:
                try:
                    now = datetime.datetime.now()
                    if now.hour == 9 and now.minute == 0:  # Каждый день в 9:00
                        notification_manager.send_daily_report(self.bot)
                    time.sleep(60)  # Проверка каждую минуту
                except Exception as e:
                    logger.error(f"Error in daily_reports: {e}")
        
        # Запускаем задачи в отдельных потоках
        Thread(target=cleanup_states, daemon=True).start()
        Thread(target=backup_task, daemon=True).start()
        Thread(target=daily_reports, daemon=True).start()
        
        logger.info("Background tasks started")
    
    def stop(self):
        """Остановка фоновых задач"""
        self.running = False
        logger.info("Background tasks stopped")

# Инициализация фоновых задач
background_tasks = BackgroundTasks(bot)

# Главное меню
@safe_execute
def main_menu(chat_id):
    """Главное меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('🏗️ Объекты')
    btn2 = types.KeyboardButton('📦 Материалы')
    btn3 = types.KeyboardButton('💵 Зарплаты')
    btn4 = types.KeyboardButton('📊 Статистика')
    btn5 = types.KeyboardButton('📤 Экспорт данных')
    
    # Кнопка администратора только для админов
    admin_ids = os.getenv('ADMIN_IDS', '').split(',')
    if str(chat_id) in admin_ids:
        btn6 = types.KeyboardButton('👨‍💼 Админ')
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    else:
        markup.add(btn1, btn2, btn3, btn4, btn5)
    
    bot.send_message(chat_id, "🎯 Выберите раздел:", reply_markup=markup)
    logger.info(f"Main menu shown for chat {chat_id}")

# Обработчик команды /start
@bot.message_handler(commands=['start'])
@log_message
@safe_execute
def start_command(message):
    """Обработчик команды /start"""
    bot.send_message(message.chat.id, Messages.WELCOME)
    main_menu(message.chat.id)
    logger.info(f"Start command from user {message.from_user.id}")

# Обработчик команды /help
@bot.message_handler(commands=['help'])
@log_message
@safe_execute
def help_command(message):
    """Обработчик команды /help"""
    bot.send_message(message.chat.id, Messages.HELP)
    logger.info(f"Help command from user {message.from_user.id}")

# Обработчик команды /cancel
@bot.message_handler(commands=['cancel'])
@log_message
@safe_execute
def cancel_operation(message):
    """Отмена текущей операции"""
    UserState.clear_state(message.from_user.id)
    bot.send_message(message.chat.id, Messages.OPERATION_CANCELLED)
    main_menu(message.chat.id)
    logger.info(f"User {message.from_user.id} cancelled operation")

# Обработчик команды /admin
@bot.message_handler(commands=['admin'])
@log_message
@safe_execute
@admin_required
def admin_command(message):
    """Панель администратора"""
    admin_menu(message.chat.id)

@safe_execute
def admin_menu(chat_id):
    """Меню администратора"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📊 Статистика системы')
    btn2 = types.KeyboardButton('🔄 Резервная копия')
    btn3 = types.KeyboardButton('🧹 Очистка кэша')
    btn4 = types.KeyboardButton('📢 Рассылка')
    btn5 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4, btn5)
    
    bot.send_message(chat_id, "👨‍💼 Панель администратора:", reply_markup=markup)

# Обработчики для админ-панели
@bot.message_handler(func=lambda message: message.text == '👨‍💼 Админ')
@safe_execute
@admin_required
def handle_admin_button(message):
    """Обработчик кнопки админа"""
    admin_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика системы')
@safe_execute
@admin_required
def system_stats(message):
    """Статистика системы"""
    try:
        # Статистика базы данных
        objects_count = db.execute_query('SELECT COUNT(*) FROM objects WHERE status = "active"')[0][0]
        materials_count = db.execute_query('SELECT COUNT(*) FROM materials')[0][0]
        salaries_count = db.execute_query('SELECT COUNT(*) FROM salaries')[0][0]
        
        # Статистика пользователей
        active_states = len(UserState._states)
        
        # Статистика кэша
        cache_size = len(stats_cache._cache)
        
        # Размер базы данных
        db_size = os.path.getsize(Config.DB_PATH) if os.path.exists(Config.DB_PATH) else 0
        
        response = f"""
📊 СТАТИСТИКА СИСТЕМЫ

🏗️ Объекты: {objects_count}
📦 Материалы: {materials_count} записей
💵 Зарплаты: {salaries_count} записей

👥 Активные сессии: {active_states}
💾 Размер кэша: {cache_size} записей
📁 Размер БД: {db_size / 1024 / 1024:.2f} MB

🕒 Время работы: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
        """
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logger.error(f"Error in system_stats: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении статистики системы")

@bot.message_handler(func=lambda message: message.text == '🔄 Резервная копия')
@safe_execute
@admin_required
def create_backup(message):
    """Создание резервной копии"""
    try:
        backup_path = backup_database()
        bot.send_message(message.chat.id, f"✅ Резервная копия создана: {os.path.basename(backup_path)}")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании резервной копии")

@bot.message_handler(func=lambda message: message.text == '🧹 Очистка кэша')
@safe_execute
@admin_required
def clear_cache(message):
    """Очистка кэша"""
    try:
        stats_cache.clear_cache()
        bot.send_message(message.chat.id, "✅ Кэш очищен")
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при очистке кэша")

@bot.message_handler(func=lambda message: message.text == '📢 Рассылка')
@safe_execute
@admin_required
def start_broadcast(message):
    """Начало рассылки"""
    UserState.set_state(message.from_user.id, 'waiting_broadcast_message')
    bot.send_message(message.chat.id, "📢 Введите сообщение для рассылки:")

# Обработчик текстовых сообщений (основной)
@bot.message_handler(content_types=['text'])
@log_message
@safe_execute
def handle_text(message):
    """Обработчик текстовых сообщений"""
    chat_id = message.chat.id
    text = message.text
    
    # Основное меню
    if text == '🏗️ Объекты':
        objects_menu(chat_id)
    elif text == '📦 Материалы':
        materials_menu(chat_id)
    elif text == '💵 Зарплаты':
        salaries_menu(chat_id)
    elif text == '📊 Статистика':
        show_statistics(chat_id)
    elif text == '📤 Экспорт данных':
        export_data_menu(chat_id)
    elif text == '⬅️ Назад':
        main_menu(chat_id)
    
    # Админ-меню
    elif text == '📊 Статистика системы':
        system_stats(message)
    elif text == '🔄 Резервная копия':
        create_backup(message)
    elif text == '🧹 Очистка кэша':
        clear_cache(message)
    elif text == '📢 Рассылка':
        start_broadcast(message)
    
    # Динамические кнопки
    elif text.startswith('🗑️_'):
        delete_object_confirm(message)
    elif text.startswith('🏗️_'):
        add_material_object(message)
    elif text.startswith('👤_'):
        add_salary_object(message)
    elif text.startswith('📤_'):
        handle_export_choice(message)
    
    # Кнопки подтверждения удаления
    elif text in ['✅ Да', '❌ Нет']:
        handle_delete_confirmation(message)
    
    # Кнопки экспорта
    elif text in ['📤_export_full_stats', '📤_export_objects_stats', 
                  '📤_export_materials_detailed', '📤_export_materials_summary',
                  '📤_export_salaries_detailed', '📤_export_salaries_summary']:
        handle_export_choice(message)
    
    else:
        # Проверяем состояние пользователя для обработки многошаговых операций
        user_state = UserState.get_state(message.from_user.id)
        if user_state:
            handle_user_state(message, user_state)
        else:
            bot.send_message(message.chat.id, Messages.INVALID_COMMAND)

def handle_user_state(message, user_state):
    """Обработка состояний пользователя для многошаговых операций"""
    state = user_state['state']
    
    if state == 'waiting_object_name':
        add_object_name(message)
    elif state == 'waiting_object_address':
        add_object_address(message, user_state['data']['object_name'])
    elif state == 'waiting_broadcast_message':
        handle_broadcast_message(message)
    elif state == 'waiting_material_name':
        add_material_name(message, user_state['data']['object_id'])
    elif state == 'waiting_material_quantity':
        add_material_quantity(message, user_state['data']['object_id'], user_state['data']['material_name'])
    elif state == 'waiting_material_unit':
        add_material_unit(message, user_state['data']['object_id'], user_state['data']['material_name'], user_state['data']['quantity'])
    elif state == 'waiting_material_price':
        add_material_price(message, user_state['data']['object_id'], user_state['data']['material_name'], user_state['data']['quantity'], user_state['data']['unit'])
    elif state == 'waiting_salary_worker':
        add_salary_worker(message, user_state['data']['object_id'])
    elif state == 'waiting_salary_position':
        add_salary_position(message, user_state['data']['object_id'], user_state['data']['worker_name'])
    elif state == 'waiting_salary_hours':
        add_salary_hours(message, user_state['data']['object_id'], user_state['data']['worker_name'], user_state['data']['position'])
    elif state == 'waiting_salary_rate':
        add_salary_rate(message, user_state['data']['object_id'], user_state['data']['worker_name'], user_state['data']['position'], user_state['data']['hours_worked'])

@safe_execute
def handle_broadcast_message(message):
    """Обработка сообщения для рассылки"""
    UserState.clear_state(message.from_user.id)
    broadcast_text = message.text
    
    # Здесь должна быть логика получения всех пользователей
    # Для демонстрации просто подтверждаем
    bot.send_message(
        message.chat.id, 
        f"✅ Сообщение для рассылки подготовлено:\n\n{broadcast_text}\n\n(В реальной системе здесь была бы отправка всем пользователям)"
    )
    admin_menu(message.chat.id)

@safe_execute
def handle_delete_confirmation(message):
    """Обработка подтверждения удаления"""
    # Эта функция будет вызываться при нажатии кнопок ✅ Да или ❌ Нет
    # В реальной реализации здесь должна быть логика определения контекста удаления
    bot.send_message(message.chat.id, "❌ Функция подтверждения удаления в разработке")
    objects_menu(message.chat.id)

# Меню объектов
@safe_execute
def objects_menu(chat_id):
    """Меню управления объектами"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('➕ Добавить объект')
    btn2 = types.KeyboardButton('📋 Список объектов')
    btn3 = types.KeyboardButton('❌ Удалить объект')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "🏗️ Управление объектами:", reply_markup=markup)

# Меню материалов
@safe_execute
def materials_menu(chat_id):
    """Меню управления материалами"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📥 Добавить материал')
    btn2 = types.KeyboardButton('📋 Расходы на материалы')
    btn3 = types.KeyboardButton('📊 Статистика материалов')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "📦 Управление материалами:", reply_markup=markup)

# Меню зарплат
@safe_execute
def salaries_menu(chat_id):
    """Меню управления зарплатами"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('👤 Добавить зарплату')
    btn2 = types.KeyboardButton('📋 Выплаты зарплат')
    btn3 = types.KeyboardButton('📊 Статистика зарплат')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "💵 Управление зарплатами:", reply_markup=markup)

# Меню экспорта данных
@safe_execute
def export_data_menu(chat_id):
    """Меню экспорта данных"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📊 Экспорт статистики')
    btn2 = types.KeyboardButton('📦 Экспорт материалов')
    btn3 = types.KeyboardButton('💵 Экспорт зарплат')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "📤 Экспорт данных:", reply_markup=markup)

# Обработчики для объектов
@bot.message_handler(func=lambda message: message.text == '➕ Добавить объект')
@safe_execute
def add_object_start(message):
    """Начало добавления объекта"""
    UserState.set_state(message.from_user.id, 'waiting_object_name')
    bot.send_message(message.chat.id, "🏗️ Введите название объекта:")

@safe_execute
def add_object_name(message):
    """Обработка названия объекта"""
    UserState.clear_state(message.from_user.id)
    object_name = message.text.strip()
    
    if not Validators.validate_russian_text(object_name):
        UserState.set_state(message.from_user.id, 'waiting_object_name')
        bot.send_message(message.chat.id, "❌ Название содержит недопустимые символы или слишком короткое. Введите название объекта:")
        return
        
    UserState.set_state(message.from_user.id, 'waiting_object_address', {'object_name': object_name})
    bot.send_message(message.chat.id, "📍 Введите адрес объекта:")

@safe_execute
def add_object_address(message, object_name):
    """Обработка адреса объекта"""
    UserState.clear_state(message.from_user.id)
    address = message.text.strip()
    
    if not Validators.validate_russian_text(address, min_length=5):
        UserState.set_state(message.from_user.id, 'waiting_object_address', {'object_name': object_name})
        bot.send_message(message.chat.id, "❌ Адрес содержит недопустимые символы или слишком короткий. Введите адрес объекта:")
        return
        
    start_date = datetime.datetime.now().strftime(Config.DEFAULT_DATE_FORMAT)
    
    db.execute_query('INSERT INTO objects (name, address, start_date) VALUES (?, ?, ?)', 
                   (object_name, address, start_date), fetch=False)
    
    bot.send_message(message.chat.id, f"✅ Объект '{object_name}' успешно добавлен! 🎉")
    objects_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📋 Список объектов')
@safe_execute
def list_objects(message):
    """Показать список объектов"""
    objects = db.execute_query('SELECT id, name, address, start_date FROM objects WHERE status = "active"')
    
    if not objects:
        bot.send_message(message.chat.id, "📭 Нет активных объектов")
        return
    
    response = "🏗️ СПИСОК ОБЪЕКТОВ:\n\n"
    for obj in objects:
        response += f"🆔 ID: {obj[0]}\n"
        response += f"📝 Название: {obj[1]}\n"
        response += f"📍 Адрес: {obj[2]}\n"
        response += f"📅 Дата начала: {obj[3]}\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n"
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '❌ Удалить объект')
@safe_execute
def delete_object_start(message):
    """Начало удаления объекта"""
    objects = db.execute_query('SELECT id, name FROM objects WHERE status = "active"')
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов для удаления")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"🗑️_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    bot.send_message(message.chat.id, "🗑️ Выберите объект для удаления:", reply_markup=markup)

@safe_execute
def delete_object_confirm(message):
    """Подтверждение удаления объекта"""
    if message.text == '⬅️ Назад':
        objects_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[1])
        object_name = '_'.join(message.text.split('_')[2:])
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(types.KeyboardButton('✅ Да'), types.KeyboardButton('❌ Нет'))
        
        UserState.set_state(message.from_user.id, 'waiting_delete_confirmation', {
            'object_id': object_id,
            'object_name': object_name
        })
        
        bot.send_message(message.chat.id, 
                        f"⚠️ Вы уверены, что хотите удалить объект '{object_name}'?",
                        reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in delete_object_confirm: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

@safe_execute
def delete_object_final(message, object_id, object_name):
    """Финальное удаление объекта"""
    if message.text == '✅ Да':
        db.execute_query('UPDATE objects SET status = "inactive" WHERE id = ?', (object_id,), fetch=False)
        bot.send_message(message.chat.id, f"✅ Объект '{object_name}' удален! 🗑️")
    else:
        bot.send_message(message.chat.id, "❌ Удаление отменено")
    
    objects_menu(message.chat.id)

# Обработчики для материалов
@bot.message_handler(func=lambda message: message.text == '📥 Добавить материал')
@safe_execute
def add_material_start(message):
    """Начало добавления материала"""
    objects = db.execute_query('SELECT id, name FROM objects WHERE status = "active"')
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект. 🏗️")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"🏗️_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    bot.send_message(message.chat.id, "🏗️ Выберите объект:", reply_markup=markup)

@safe_execute
def add_material_object(message):
    """Обработка выбора объекта для материала"""
    if message.text == '⬅️ Назад':
        materials_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[1])
        UserState.set_state(message.from_user.id, 'waiting_material_name', {'object_id': object_id})
        bot.send_message(message.chat.id, "📝 Введите название материала:")
    except Exception as e:
        logger.error(f"Error in add_material_object: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

@safe_execute
def add_material_name(message, object_id):
    """Обработка названия материала"""
    material_name = message.text.strip()
    if not Validators.validate_russian_text(material_name):
        UserState.set_state(message.from_user.id, 'waiting_material_name', {'object_id': object_id})
        bot.send_message(message.chat.id, "❌ Название содержит недопустимые символы. Введите название материала:")
        return
        
    UserState.set_state(message.from_user.id, 'waiting_material_quantity', {
        'object_id': object_id,
        'material_name': material_name
    })
    bot.send_message(message.chat.id, "🔢 Введите количество:")

@safe_execute
def add_material_quantity(message, object_id, material_name):
    """Обработка количества материала"""
    if not Validators.is_valid_number(message.text):
        UserState.set_state(message.from_user.id, 'waiting_material_quantity', {
            'object_id': object_id,
            'material_name': material_name
        })
        bot.send_message(message.chat.id, "❌ Введите корректное число для количества:")
        return
        
    quantity = float(message.text)
    UserState.set_state(message.from_user.id, 'waiting_material_unit', {
        'object_id': object_id,
        'material_name': material_name,
        'quantity': quantity
    })
    bot.send_message(message.chat.id, "📏 Введите единицу измерения (шт, кг, м и т.д.):")

@safe_execute
def add_material_unit(message, object_id, material_name, quantity):
    """Обработка единицы измерения"""
    unit = message.text.strip()
    if not unit:
        UserState.set_state(message.from_user.id, 'waiting_material_unit', {
            'object_id': object_id,
            'material_name': material_name,
            'quantity': quantity
        })
        bot.send_message(message.chat.id, "❌ Единица измерения не может быть пустой. Введите единицу измерения:")
        return
        
    UserState.set_state(message.from_user.id, 'waiting_material_price', {
        'object_id': object_id,
        'material_name': material_name,
        'quantity': quantity,
        'unit': unit
    })
    bot.send_message(message.chat.id, "💰 Введите цену за единицу:")

@safe_execute
def add_material_price(message, object_id, material_name, quantity, unit):
    """Обработка цены материала и сохранение"""
    UserState.clear_state(message.from_user.id)
    
    if not Validators.is_valid_number(message.text):
        UserState.set_state(message.from_user.id, 'waiting_material_price', {
            'object_id': object_id,
            'material_name': material_name,
            'quantity': quantity,
            'unit': unit
        })
        bot.send_message(message.chat.id, "❌ Введите корректное число для цены:")
        return
        
    price_per_unit = float(message.text)
    total_cost = quantity * price_per_unit
    date = datetime.datetime.now().strftime(Config.DEFAULT_DATE_FORMAT)
    
    db.execute_query('''
        INSERT INTO materials (object_id, material_name, quantity, unit, price_per_unit, total_cost, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (object_id, material_name, quantity, unit, price_per_unit, total_cost, date), fetch=False)
    
    bot.send_message(message.chat.id, f"✅ Материал '{material_name}' добавлен! 📦\n"
                     f"💸 Сумма: {total_cost:.2f} руб. 💰")
    materials_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📋 Расходы на материалы')
@safe_execute
def show_materials_expenses(message):
    """Показать расходы на материалы"""
    cache_key = "materials_expenses"
    cached_data = stats_cache.get_cached_data(cache_key)
    
    if cached_data:
        bot.send_message(message.chat.id, cached_data)
        return
    
    materials = db.execute_query('''
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
        response += "━━━━━━━━━━━━━━━━━━━━\n"
        total += mat[4]
    
    response += f"\n💵 ОБЩАЯ СУММА: {total:.2f} руб. 💸"
    
    stats_cache.set_cached_data(cache_key, response)
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика материалов')
@safe_execute
def show_materials_statistics(message):
    """Показать статистику материалов"""
    cache_key = "materials_statistics"
    cached_data = stats_cache.get_cached_data(cache_key)
    
    if cached_data:
        bot.send_message(message.chat.id, cached_data)
        return
    
    stats = db.execute_query('''
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
        response += f"📦 {stat[0]}\n"
        response += f"   📏 Количество: {stat[1]} {stat[2]}\n"
        response += f"   💰 Сумма: {stat[3]:.2f} руб.\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n"
        total_cost += stat[3]
    
    response += f"\n💵 ОБЩАЯ СУММА: {total_cost:.2f} руб. 💸"
    
    stats_cache.set_cached_data(cache_key, response)
    bot.send_message(message.chat.id, response)

# Обработчики для зарплат
@bot.message_handler(func=lambda message: message.text == '👤 Добавить зарплату')
@safe_execute
def add_salary_start(message):
    """Начало добавления зарплаты"""
    objects = db.execute_query('SELECT id, name FROM objects WHERE status = "active"')
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект. 🏗️")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"👤_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    bot.send_message(message.chat.id, "🏗️ Выберите объект:", reply_markup=markup)

@safe_execute
def add_salary_object(message):
    """Обработка выбора объекта для зарплаты"""
    if message.text == '⬅️ Назад':
        salaries_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[1])
        UserState.set_state(message.from_user.id, 'waiting_salary_worker', {'object_id': object_id})
        bot.send_message(message.chat.id, "👨‍💼 Введите ФИО работника:")
    except Exception as e:
        logger.error(f"Error in add_salary_object: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

@safe_execute
def add_salary_worker(message, object_id):
    """Обработка ФИО работника"""
    worker_name = message.text.strip()
    if not Validators.validate_russian_text(worker_name, min_length=5):
        UserState.set_state(message.from_user.id, 'waiting_salary_worker', {'object_id': object_id})
        bot.send_message(message.chat.id, "❌ ФИО содержит недопустимые символы или слишком короткое. Введите ФИО работника:")
        return
        
    UserState.set_state(message.from_user.id, 'waiting_salary_position', {
        'object_id': object_id,
        'worker_name': worker_name
    })
    bot.send_message(message.chat.id, "💼 Введите должность:")

@safe_execute
def add_salary_position(message, object_id, worker_name):
    """Обработка должности"""
    position = message.text.strip()
    if not Validators.validate_russian_text(position):
        UserState.set_state(message.from_user.id, 'waiting_salary_position', {
            'object_id': object_id,
            'worker_name': worker_name
        })
        bot.send_message(message.chat.id, "❌ Должность содержит недопустимые символы. Введите должность:")
        return
        
    UserState.set_state(message.from_user.id, 'waiting_salary_hours', {
        'object_id': object_id,
        'worker_name': worker_name,
        'position': position
    })
    bot.send_message(message.chat.id, "⏱️ Введите количество отработанных часов:")

@safe_execute
def add_salary_hours(message, object_id, worker_name, position):
    """Обработка отработанных часов"""
    if not Validators.is_valid_number(message.text):
        UserState.set_state(message.from_user.id, 'waiting_salary_hours', {
            'object_id': object_id,
            'worker_name': worker_name,
            'position': position
        })
        bot.send_message(message.chat.id, "❌ Введите корректное число часов:")
        return
        
    hours_worked = float(message.text)
    UserState.set_state(message.from_user.id, 'waiting_salary_rate', {
        'object_id': object_id,
        'worker_name': worker_name,
        'position': position,
        'hours_worked': hours_worked
    })
    bot.send_message(message.chat.id, "💰 Введите ставку за час (руб.):")

@safe_execute
def add_salary_rate(message, object_id, worker_name, position, hours_worked):
    """Обработка ставки и сохранение зарплаты"""
    UserState.clear_state(message.from_user.id)
    
    if not Validators.is_valid_number(message.text):
        UserState.set_state(message.from_user.id, 'waiting_salary_rate', {
            'object_id': object_id,
            'worker_name': worker_name,
            'position': position,
            'hours_worked': hours_worked
        })
        bot.send_message(message.chat.id, "❌ Введите корректное число для ставки:")
        return
        
    hourly_rate = float(message.text)
    total_salary = hours_worked * hourly_rate
    date = datetime.datetime.now().strftime(Config.DEFAULT_DATE_FORMAT)
    
    db.execute_query('''
        INSERT INTO salaries (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date), fetch=False)
    
    bot.send_message(message.chat.id, f"✅ Зарплата для {worker_name} добавлена! 💵\n"
                     f"💸 Сумма: {total_salary:.2f} руб. 💰")
    salaries_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📋 Выплаты зарплат')
@safe_execute
def show_salaries_expenses(message):
    """Показать выплаты зарплат"""
    cache_key = "salaries_expenses"
    cached_data = stats_cache.get_cached_data(cache_key)
    
    if cached_data:
        bot.send_message(message.chat.id, cached_data)
        return
    
    salaries = db.execute_query('''
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
        response += "━━━━━━━━━━━━━━━━━━━━\n"
        total += sal[4]
    
    response += f"\n💵 ОБЩАЯ СУММА: {total:.2f} руб. 💸"
    
    stats_cache.set_cached_data(cache_key, response)
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика зарплат')
@safe_execute
def show_salaries_statistics(message):
    """Показать статистику зарплат"""
    cache_key = "salaries_statistics"
    cached_data = stats_cache.get_cached_data(cache_key)
    
    if cached_data:
        bot.send_message(message.chat.id, cached_data)
        return
    
    stats = db.execute_query('''
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
        response += f"   ⏱️ Часы: {stat[2]}\n"
        response += f"   💰 Зарплата: {stat[3]:.2f} руб.\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n"
        total_hours += stat[2]
        total_salary += stat[3]
    
    response += f"\n📈 ИТОГО:\n"
    response += f"   ⏱️ Общее время: {total_hours} часов\n"
    response += f"   💵 Общая сумма: {total_salary:.2f} руб. 💸"
    
    stats_cache.set_cached_data(cache_key, response)
    bot.send_message(message.chat.id, response)

# Функции для экспорта данных
@bot.message_handler(func=lambda message: message.text == '📊 Экспорт статистики')
@safe_execute
def export_statistics_start(message):
    """Начало экспорта статистики"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📤_export_full_stats')
    btn2 = types.KeyboardButton('📤_export_objects_stats')
    btn3 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3)
    
    bot.send_message(message.chat.id, "📊 Выберите тип экспорта статистики:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '📦 Экспорт материалов')
@safe_execute
def export_materials_start(message):
    """Начало экспорта материалов"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📤_export_materials_detailed')
    btn2 = types.KeyboardButton('📤_export_materials_summary')
    btn3 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3)
    
    bot.send_message(message.chat.id, "📦 Выберите тип экспорта материалов:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '💵 Экспорт зарплат')
@safe_execute
def export_salaries_start(message):
    """Начало экспорта зарплат"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📤_export_salaries_detailed')
    btn2 = types.KeyboardButton('📤_export_salaries_summary')
    btn3 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3)
    
    bot.send_message(message.chat.id, "💵 Выберите тип экспорта зарплат:", reply_markup=markup)

@safe_execute
def handle_export_choice(message):
    """Обработка выбора типа экспорта с пагинацией"""
    if message.text == '⬅️ Назад':
        export_data_menu(message.chat.id)
        return
    
    export_type = message.text.split('_')[1]
    
    if export_type == 'export_full_stats':
        report = generate_full_statistics_report()
    elif export_type == 'export_objects_stats':
        report = generate_objects_statistics_report()
    elif export_type == 'export_materials_detailed':
        report = generate_materials_detailed_report()
    elif export_type == 'export_materials_summary':
        report = generate_materials_summary_report()
    elif export_type == 'export_salaries_detailed':
        report = generate_salaries_detailed_report()
    elif export_type == 'export_salaries_summary':
        report = generate_salaries_summary_report()
    else:
        bot.send_message(message.chat.id, "❌ Неизвестный тип экспорта")
        return
    
    # Используем пагинацию для длинных отчетов
    PaginationUtils.send_paginated_message(bot, message.chat.id, report)
    bot.send_message(message.chat.id, "✅ Экспорт завершен!")

def generate_full_statistics_report() -> str:
    """Генерация полного отчета статистики с кэшированием"""
    cache_key = "full_stats_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    # Общая статистика
    objects_count = db.execute_query('SELECT COUNT(*) FROM objects WHERE status = "active"')[0][0]
    total_materials = db.execute_query('SELECT SUM(total_cost) FROM materials')[0][0] or 0
    total_salaries = db.execute_query('SELECT SUM(total_salary) FROM salaries')[0][0] or 0
    total_expenses = total_materials + total_salaries
    
    report = f"""
ОТЧЕТ ПО СТРОИТЕЛЬНЫМ ОБЪЕКТАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}

ОБЩАЯ СТАТИСТИКА:
🏗️ Активных объектов: {objects_count}
📦 Расходы на материалы: {total_materials:.2f} руб.
💵 Расходы на зарплаты: {total_salaries:.2f} руб.
💰 Общие расходы: {total_expenses:.2f} руб.

{'='*50}
СТАТИСТИКА ПО ОБЪЕКТАМ:
"""
    # Статистика по объектам
    objects_stats = db.execute_query('''
        SELECT o.name, o.address, o.start_date,
               COALESCE(SUM(m.total_cost), 0) as materials_cost,
               COALESCE(SUM(s.total_salary), 0) as salaries_cost
        FROM objects o
        LEFT JOIN materials m ON o.id = m.object_id
        LEFT JOIN salaries s ON o.id = s.object_id
        WHERE o.status = 'active'
        GROUP BY o.id, o.name, o.address, o.start_date
    ''')
    
    for obj in objects_stats:
        total_obj = obj[3] + obj[4]
        report += f"\n🏗️ ОБЪЕКТ: {obj[0]}\n"
        report += f"   📍 Адрес: {obj[1]}\n"
        report += f"   📅 Начало: {obj[2]}\n"
        report += f"   📦 Материалы: {obj[3]:.2f} руб.\n"
        report += f"   👥 Зарплаты: {obj[4]:.2f} руб.\n"
        report += f"   💰 Всего расходов: {total_obj:.2f} руб.\n"
        report += "   " + "─" * 40 + "\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

def generate_objects_statistics_report() -> str:
    """Генерация отчета по объектам с кэшированием"""
    cache_key = "objects_stats_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    objects_stats = db.execute_query('''
        SELECT o.name, o.address, o.start_date,
               COUNT(DISTINCT m.id) as materials_count,
               COUNT(DISTINCT s.id) as salaries_count,
               COALESCE(SUM(m.total_cost), 0) as materials_cost,
               COALESCE(SUM(s.total_salary), 0) as salaries_cost
        FROM objects o
        LEFT JOIN materials m ON o.id = m.object_id
        LEFT JOIN salaries s ON o.id = s.object_id
        WHERE o.status = 'active'
        GROUP BY o.id, o.name, o.address, o.start_date
        ORDER BY (COALESCE(SUM(m.total_cost), 0) + COALESCE(SUM(s.total_salary), 0)) DESC
    ''')
    
    report = f"""
ОТЧЕТ ПО ОБЪЕКТАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}
"""
    total_materials = 0
    total_salaries = 0
    
    for obj in objects_stats:
        total_obj = obj[5] + obj[6]
        total_materials += obj[5]
        total_salaries += obj[6]
        
        report += f"\n🏗️ {obj[0]}\n"
        report += f"   📍 {obj[1]}\n"
        report += f"   📅 Начало: {obj[2]}\n"
        report += f"   📦 Материалов: {obj[3]} записей\n"
        report += f"   👥 Выплат: {obj[4]} записей\n"
        report += f"   💰 Материалы: {obj[5]:.2f} руб.\n"
        report += f"   💵 Зарплаты: {obj[6]:.2f} руб.\n"
        report += f"   🎯 Всего: {total_obj:.2f} руб.\n"
        report += "   " + "─" * 40 + "\n"
    
    report += f"\n{'='*50}\n"
    report += f"ИТОГО ПО ВСЕМ ОБЪЕКТАМ:\n"
    report += f"📦 Материалы: {total_materials:.2f} руб.\n"
    report += f"💵 Зарплаты: {total_salaries:.2f} руб.\n"
    report += f"💰 Общие расходы: {total_materials + total_salaries:.2f} руб.\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

def generate_materials_detailed_report() -> str:
    """Генерация детального отчета по материалам с кэшированием"""
    cache_key = "materials_detailed_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    materials = db.execute_query('''
        SELECT o.name, m.material_name, m.quantity, m.unit, 
               m.price_per_unit, m.total_cost, m.date
        FROM materials m
        JOIN objects o ON m.object_id = o.id
        ORDER BY m.date DESC, o.name
    ''')
    
    report = f"""
ДЕТАЛЬНЫЙ ОТЧЕТ ПО МАТЕРИАЛАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}
"""
    total_cost = 0
    
    for mat in materials:
        report += f"\n🏗️ {mat[0]}\n"
        report += f"   📦 {mat[1]}\n"
        report += f"   📏 {mat[2]} {mat[3]}\n"
        report += f"   💰 Цена: {mat[4]:.2f} руб./{mat[3]}\n"
        report += f"   💵 Сумма: {mat[5]:.2f} руб.\n"
        report += f"   📅 Дата: {mat[6]}\n"
        report += "   " + "─" * 40 + "\n"
        total_cost += mat[5]
    
    report += f"\n{'='*50}\n"
    report += f"ОБЩАЯ СУММА: {total_cost:.2f} руб.\n"
    report += f"КОЛИЧЕСТВО ЗАПИСЕЙ: {len(materials)}\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

def generate_materials_summary_report() -> str:
    """Генерация сводного отчета по материалам с кэшированием"""
    cache_key = "materials_summary_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    stats = db.execute_query('''
        SELECT material_name, unit, 
               SUM(quantity) as total_quantity,
               AVG(price_per_unit) as avg_price,
               SUM(total_cost) as total_cost
        FROM materials 
        GROUP BY material_name, unit
        ORDER BY SUM(total_cost) DESC
    ''')
    
    report = f"""
СВОДНЫЙ ОТЧЕТ ПО МАТЕРИАЛАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}
"""
    total_cost = 0
    
    for stat in stats:
        report += f"\n📦 {stat[0]}\n"
        report += f"   📏 Всего: {stat[2]} {stat[1]}\n"
        report += f"   💰 Средняя цена: {stat[3]:.2f} руб./{stat[1]}\n"
        report += f"   💵 Общая стоимость: {stat[4]:.2f} руб.\n"
        report += "   " + "─" * 40 + "\n"
        total_cost += stat[4]
    
    report += f"\n{'='*50}\n"
    report += f"ОБЩАЯ СУММА: {total_cost:.2f} руб.\n"
    report += f"КОЛИЧЕСТВО ВИДОВ МАТЕРИАЛОВ: {len(stats)}\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

def generate_salaries_detailed_report() -> str:
    """Генерация детального отчета по зарплатам с кэшированием"""
    cache_key = "salaries_detailed_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    salaries = db.execute_query('''
        SELECT o.name, s.worker_name, s.position, 
               s.hours_worked, s.hourly_rate, s.total_salary, s.date
        FROM salaries s
        JOIN objects o ON s.object_id = o.id
        ORDER BY s.date DESC, o.name
    ''')
    
    report = f"""
ДЕТАЛЬНЫЙ ОТЧЕТ ПО ЗАРПЛАТАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}
"""
    total_salary = 0
    total_hours = 0
    
    for sal in salaries:
        report += f"\n🏗️ {sal[0]}\n"
        report += f"   👤 {sal[1]} ({sal[2]})\n"
        report += f"   ⏱️ {sal[3]} часов\n"
        report += f"   💰 Ставка: {sal[4]:.2f} руб./час\n"
        report += f"   💵 Сумма: {sal[5]:.2f} руб.\n"
        report += f"   📅 Дата: {sal[6]}\n"
        report += "   " + "─" * 40 + "\n"
        total_salary += sal[5]
        total_hours += sal[3]
    
    report += f"\n{'='*50}\n"
    report += f"ОБЩАЯ СУММА: {total_salary:.2f} руб.\n"
    report += f"ОБЩЕЕ ВРЕМЯ: {total_hours} часов\n"
    report += f"КОЛИЧЕСТВО ВЫПЛАТ: {len(salaries)}\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

def generate_salaries_summary_report() -> str:
    """Генерация сводного отчета по зарплатам с кэшированием"""
    cache_key = "salaries_summary_report"
    cached_report = stats_cache.get_cached_data(cache_key)
    if cached_report:
        return cached_report
    
    stats = db.execute_query('''
        SELECT worker_name, position,
               SUM(hours_worked) as total_hours,
               AVG(hourly_rate) as avg_rate,
               SUM(total_salary) as total_salary
        FROM salaries 
        GROUP BY worker_name, position
        ORDER BY SUM(total_salary) DESC
    ''')
    
    report = f"""
СВОДНЫЙ ОТЧЕТ ПО ЗАРПЛАТАМ
Сгенерирован: {datetime.datetime.now().strftime(Config.DATETIME_FORMAT)}
{'='*50}
"""
    total_salary = 0
    total_hours = 0
    
    for stat in stats:
        report += f"\n👤 {stat[0]}\n"
        report += f"   💼 Должность: {stat[1]}\n"
        report += f"   ⏱️ Отработано: {stat[2]} часов\n"
        report += f"   💰 Средняя ставка: {stat[3]:.2f} руб./час\n"
        report += f"   💵 Общая зарплата: {stat[4]:.2f} руб.\n"
        report += "   " + "─" * 40 + "\n"
        total_salary += stat[4]
        total_hours += stat[2]
    
    avg_hourly_rate = total_salary / total_hours if total_hours > 0 else 0
    
    report += f"\n{'='*50}\n"
    report += f"ОБЩАЯ СУММА: {total_salary:.2f} руб.\n"
    report += f"ОБЩЕЕ ВРЕМЯ: {total_hours} часов\n"
    report += f"СРЕДНЯЯ СТАВКА: {avg_hourly_rate:.2f} руб./час\n"
    report += f"КОЛИЧЕСТВО РАБОТНИКОВ: {len(stats)}\n"
    
    stats_cache.set_cached_data(cache_key, report)
    return report

# Показать статистику
@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
@safe_execute
def show_statistics(message):
    """Показать общую статистику"""
    cache_key = "general_statistics"
    cached_data = stats_cache.get_cached_data(cache_key)
    
    if cached_data:
        bot.send_message(message.chat.id, cached_data)
        return
    
    # Общая статистика
    objects_count = db.execute_query('SELECT COUNT(*) FROM objects WHERE status = "active"')[0][0]
    total_materials = db.execute_query('SELECT SUM(total_cost) FROM materials')[0][0] or 0
    total_salaries = db.execute_query('SELECT SUM(total_salary) FROM salaries')[0][0] or 0
    total_expenses = total_materials + total_salaries
    
    response = "📊 ОБЩАЯ СТАТИСТИКА\n\n"
    response += f"🏗️ Активных объектов: {objects_count}\n"
    response += f"📦 Расходы на материалы: {total_materials:.2f} руб.\n"
    response += f"💵 Расходы на зарплаты: {total_salaries:.2f} руб.\n"
    response += f"💰 Общие расходы: {total_expenses:.2f} руб.\n\n"
    
    # Статистика по объектам
    objects_stats = db.execute_query('''
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
            total_obj = obj[1] + obj[2]
            response += f"\n🏗️ {obj[0]}:\n"
            response += f"   📦 Материалы: {obj[1]:.2f} руб.\n"
            response += f"   👥 Зарплаты: {obj[2]:.2f} руб.\n"
            response += f"   💰 Всего: {total_obj:.2f} руб.\n"
            response += "   ━━━━━━━━━━━━━━━━━━\n"
    
    stats_cache.set_cached_data(cache_key, response)
    bot.send_message(message.chat.id, response)

# Запуск бота с улучшенной обработкой
def main():
    """Основная функция запуска"""
    logger.info("🚀 Запуск Construction Manager Bot...")
    
    # Создаем необходимые директории
    for directory in [Config.BACKUP_DIR, Config.LOGS_DIR]:
        os.makedirs(directory, exist_ok=True)
    
    # Запускаем фоновые задачи
    background_tasks.start()
    
    # Создаем резервную копию при старте
    try:
        if os.path.exists(Config.DB_PATH):
            backup_database()
    except Exception as e:
        logger.error(f"Error creating initial backup: {e}")
    
    # Основной цикл бота
    while True:
        try:
            logger.info("Бот запущен и готов к работе")
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            logger.error(f"❌ Ошибка в работе бота: {e}")
            logger.info("🔄 Перезапуск через 15 секунд...")
            time.sleep(15)

if __name__ == "__main__":
    main()
