import logging
import asyncio
from datetime import datetime, timedelta
import aiosqlite
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import io
import time
import json
import os
from typing import Dict, Any, List

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

# Токен бота
API_TOKEN = 'YOUR_BOT_TOKEN'

# Инициализация бота и диспетчера с хранилищем
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_spreadsheet_url = State()
    waiting_for_sheet_name = State()
    waiting_for_object_name = State()
    waiting_for_object_data = State()
    waiting_for_object_edit = State()

# Модели данных
class UserData:
    def __init__(self):
        self.spreadsheet_url = None
        self.sheet_name = None
        self.objects = {}
        self.import_time = None

# Глобальные переменные для хранения данных
user_data: Dict[int, UserData] = {}
spreadsheet_data: Dict[int, List[Dict]] = {}

# Конфигурация
class Config:
    AUTO_DELETE_TIMEOUT = 60  # seconds
    MAX_OBJECTS_PER_USER = 50
    EXPORT_FILE_TTL = 300  # 5 minutes

# Утилиты
class Utils:
    @staticmethod
    def validate_google_sheets_url(url: str) -> bool:
        """Проверка валидности URL Google Sheets"""
        return url.startswith('https://docs.google.com/spreadsheets/')
    
    @staticmethod
    def format_object_list(objects: Dict) -> str:
        """Форматирование списка объектов"""
        if not objects:
            return "📝 Список объектов пуст"
        
        result = "📋 Ваши объекты:\n\n"
        for i, (name, data) in enumerate(objects.items(), 1):
            result += f"{i}. {name}\n"
        return result
    
    @staticmethod
    def create_main_keyboard() -> ReplyKeyboardMarkup:
        """Создание основной клавиатуры"""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📥 Импорт таблицы"), KeyboardButton(text="➕ Добавить объект")],
                [KeyboardButton(text="📋 Список объектов"), KeyboardButton(text="📊 Экспорт в Excel")],
                [KeyboardButton(text="🔄 Обновить данные"), KeyboardButton(text="❓ Помощь")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие..."
        )
    
    @staticmethod
    def create_objects_keyboard(objects: Dict) -> InlineKeyboardMarkup:
        """Создание инлайн-клавиатуры для объектов"""
        buttons = []
        for name in objects.keys():
            buttons.append([InlineKeyboardButton(text=f"👁️ {name}", callback_data=f"view_{name}")])
            buttons.append([
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{name}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{name}")
            ])
        buttons.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_main")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

# Сервис для работы с Google Sheets
class GoogleSheetsService:
    def __init__(self):
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    def get_sheet_data(self, spreadsheet_url: str, sheet_name: str) -> List[Dict]:
        """Получение данных из Google Sheets"""
        try:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError("Файл credentials.json не найден")
                
            creds = Credentials.from_service_account_file("credentials.json", scopes=self.scope)
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(spreadsheet_url)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            data = worksheet.get_all_records()
            logger.info(f"Успешно получено {len(data)} записей из Google Sheets")
            return data
        except Exception as e:
            logger.error(f"Ошибка при получении данных из Google Sheets: {e}")
            raise

# Менеджер данных пользователя
class UserDataManager:
    @staticmethod
    def get_user_data(user_id: int) -> UserData:
        """Получение или создание данных пользователя"""
        if user_id not in user_data:
            user_data[user_id] = UserData()
        return user_data[user_id]
    
    @staticmethod
    def cleanup_old_data():
        """Очистка старых данных"""
        current_time = datetime.now()
        users_to_remove = []
        
        for user_id, data in user_data.items():
            if data.import_time and (current_time - data.import_time).total_seconds() > Config.AUTO_DELETE_TIMEOUT:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            if user_id in user_data:
                del user_data[user_id]
            if user_id in spreadsheet_data:
                del spreadsheet_data[user_id]
            logger.info(f"Очищены данные пользователя {user_id}")

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_data_manager = UserDataManager.get_user_data(message.from_user.id)
    
    welcome_text = """
🤖 Добро пожаловать в бот для управления данными!

📊 **Основные функции:**
• Импорт данных из Google Sheets
• Добавление и управление объектами
• Экспорт данных в Excel
• Автоматическое обновление

🎯 **Быстрый старт:**
1. Нажмите "📥 Импорт таблицы" для загрузки данных
2. Добавьте свои объекты через "➕ Добавить объект"
3. Экспортируйте результат в Excel

Данные автоматически удаляются через 60 секунд для безопасности 🔒
    """
    
    await message.answer(welcome_text, reply_markup=Utils.create_main_keyboard())

# Обработчик команды /help
@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
📖 **Справка по командам:**

📥 **Импорт таблицы** - загрузка данных из Google Sheets
➡️ Введите URL таблицы и название листа

➕ **Добавить объект** - создание нового объекта
➡️ Введите название и данные в формате:
Поле: Значение
Поле2: Значение2

📋 **Список объектов** - просмотр всех объектов
➡️ Показывает список с возможностью управления

📊 **Экспорт в Excel** - выгрузка данных в Excel
➡️ Создает файл с текущими данными

🔄 **Обновить данные** - обновление импортированных данных
➡️ Перезагружает данные из Google Sheets

⚡ **Автоматическое удаление данных через 60 секунд**
    """
    await message.answer(help_text)

# Обработчик кнопки "Импорт таблицы"
@dp.message(F.text == "📥 Импорт таблицы")
async def import_table(message: types.Message, state: FSMContext):
    await message.answer(
        "📥 Введите URL Google Sheets таблицы:\n\n"
        "Пример: https://docs.google.com/spreadsheets/d/...",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_for_spreadsheet_url)

# Обработчик URL таблицы
@dp.message(Form.waiting_for_spreadsheet_url)
async def process_spreadsheet_url(message: types.Message, state: FSMContext):
    spreadsheet_url = message.text.strip()
    
    if not Utils.validate_google_sheets_url(spreadsheet_url):
        await message.answer("❌ Неверный формат URL Google Sheets. Попробуйте еще раз:")
        return
    
    await state.update_data(spreadsheet_url=spreadsheet_url)
    await message.answer("📋 Введите название листа в таблице:")
    await state.set_state(Form.waiting_for_sheet_name)

# Обработчик названия листа
@dp.message(Form.waiting_for_sheet_name)
async def process_sheet_name(message: types.Message, state: FSMContext):
    sheet_name = message.text.strip()
    user_id = message.from_user.id
    
    data = await state.get_data()
    spreadsheet_url = data.get('spreadsheet_url')
    
    try:
        # Получение данных из Google Sheets
        sheets_service = GoogleSheetsService()
        data = sheets_service.get_sheet_data(spreadsheet_url, sheet_name)
        
        if data:
            user_data_manager = UserDataManager.get_user_data(user_id)
            user_data_manager.spreadsheet_url = spreadsheet_url
            user_data_manager.sheet_name = sheet_name
            user_data_manager.import_time = datetime.now()
            
            spreadsheet_data[user_id] = data
            
            # Запуск таймера автоматического удаления
            asyncio.create_task(delete_imported_data(user_id))
            
            await message.answer(
                f"✅ Таблица успешно импортирована!\n"
                f"📊 Записей загружено: {len(data)}\n"
                f"⏰ Данные будут автоматически удалены через {Config.AUTO_DELETE_TIMEOUT} секунд",
                reply_markup=Utils.create_main_keyboard()
            )
        else:
            await message.answer(
                "❌ Не удалось загрузить данные. Проверьте название листа и доступы.",
                reply_markup=Utils.create_main_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Ошибка импорта для пользователя {user_id}: {e}")
        await message.answer(
            f"❌ Ошибка при импорте таблицы: {str(e)}",
            reply_markup=Utils.create.create_main_keyboard()
        )
    
    await state.clear()

# Обработчик кнопки "Добавить объект"
@dp.message(F.text == "➕ Добавить объект")
async def add_object(message: types.Message, state: FSMContext):
    user_data_manager = UserDataManager.get_user_data(message.from_user.id)
    
    # Проверка лимита объектов
    if len(user_data_manager.objects) >= Config.MAX_OBJECTS_PER_USER:
        await message.answer(f"❌ Достигнут лимит объектов ({Config.MAX_OBJECTS_PER_USER}). Удалите некоторые объекты чтобы добавить новые.")
        return
    
    await message.answer("📝 Введите название объекта:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_object_name)

# Обработчик названия объекта
@dp.message(Form.waiting_for_object_name)
async def process_object_name(message: types.Message, state: FSMContext):
    object_name = message.text.strip()
    user_data_manager = UserDataManager.get_user_data(message.from_user.id)
    
    # Проверка существования объекта
    if object_name in user_data_manager.objects:
        await message.answer("❌ Объект с таким названием уже существует. Введите другое название:")
        return
    
    await state.update_data(object_name=object_name)
    
    await message.answer(
        f"📄 Введите данные для объекта '{object_name}' в формате:\n\n"
        "Поле1: Значение1\n"
        "Поле2: Значение2\n"
        "и т.д.\n\n"
        "Пример:\n"
        "Название: Проект А\n"
        "Статус: В работе\n"
        "Ответственный: Иванов И."
    )
    await state.set_state(Form.waiting_for_object_data)

# Обработчик данных объекта
@dp.message(Form.waiting_for_object_data)
async def process_object_data(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    object_name = data.get('object_name')
    object_data = message.text
    
    user_data_manager = UserDataManager.get_user_data(user_id)
    user_data_manager.objects[object_name] = {
        'data': object_data,
        'created_at': datetime.now().isoformat()
    }
    
    await message.answer(
        f"✅ Объект '{object_name}' успешно добавлен!",
        reply_markup=Utils.create_main_keyboard()
    )
    await state.clear()

# Обработчик кнопки "Список объектов"
@dp.message(F.text == "📋 Список объектов")
async def list_objects(message: types.Message):
    user_data_manager = UserDataManager.get_user_data(message.from_user.id)
    
    if user_data_manager.objects:
        response_text = Utils.format_object_list(user_data_manager.objects)
        keyboard = Utils.create_objects_keyboard(user_data_manager.objects)
        await message.answer(response_text, reply_markup=keyboard)
    else:
        await message.answer("📝 У вас пока нет добавленных объектов.")

# Обработчик инлайн-кнопок объектов
@dp.callback_query(F.data.startswith(("view_", "edit_", "delete_", "back_")))
async def handle_object_actions(callback: types.CallbackQuery, state: FSMContext):
    user_data_manager = UserDataManager.get_user_data(callback.from_user.id)
    action = callback.data
    
    if action == "back_to_main":
        await callback.message.edit_text("Главное меню", reply_markup=None)
        await callback.message.answer("Выберите действие:", reply_markup=Utils.create_main_keyboard())
    
    elif action.startswith("view_"):
        object_name = action[5:]
        if object_name in user_data_manager.objects:
            object_data = user_data_manager.objects[object_name]['data']
            await callback.message.edit_text(
                f"👁️ Просмотр объекта: {object_name}\n\n"
                f"📄 Данные:\n{object_data}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Назад к списку", callback_data="back_to_list")]
                ])
            )
    
    elif action.startswith("delete_"):
        object_name = action[7:]
        if object_name in user_data_manager.objects:
            del user_data_manager.objects[object_name]
            await callback.message.edit_text(
                f"✅ Объект '{object_name}' удален!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Назад к списку", callback_data="back_to_list")]
                ])
            )
    
    await callback.answer()

# Обработчик кнопки "Экспорт в Excel"
@dp.message(F.text == "📊 Экспорт в Excel")
async def export_to_excel(message: types.Message):
    user_id = message.from_user.id
    user_data_manager = UserDataManager.get_user_data(user_id)
    
    try:
        # Создание комбинированных данных
        all_data = []
        
        # Добавление импортированных данных
        if user_id in spreadsheet_data and spreadsheet_data[user_id]:
            all_data.extend(spreadsheet_data[user_id])
        
        # Добавление пользовательских объектов
        if user_data_manager.objects:
            for obj_name, obj_data in user_data_manager.objects.items():
                obj_row = {'Object Name': obj_name, 'User Data': obj_data['data']}
                all_data.append(obj_row)
        
        if not all_data:
            await message.answer("❌ Нет данных для экспорта.")
            return
        
        # Создание DataFrame
        df = pd.DataFrame(all_data)
        
        # Создание Excel файла в памяти
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Exported Data', index=False)
            
            # Форматирование
            workbook = writer.book
            worksheet = writer.sheets['Exported Data']
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 20)
        
        output.seek(0)
        
        # Отправка файла
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        await message.answer_document(
            types.BufferedInputFile(output.read(), filename=filename),
            caption=f"📊 Экспорт данных\n🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n📁 Записей: {len(all_data)}"
        )
        
        logger.info(f"Пользователь {user_id} экспортировал {len(all_data)} записей")
        
    except Exception as e:
        logger.error(f"Ошибка экспорта для пользователя {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при создании Excel файла.")

# Обработчик кнопки "Обновить данные"
@dp.message(F.text == "🔄 Обновить данные")
async def refresh_data(message: types.Message):
    user_id = message.from_user.id
    user_data_manager = UserDataManager.get_user_data(user_id)
    
    if not user_data_manager.spreadsheet_url or not user_data_manager.sheet_name:
        await message.answer("❌ Нет данных для обновления. Сначала импортируйте таблицу.")
        return
    
    try:
        sheets_service = GoogleSheetsService()
        data = sheets_service.get_sheet_data(
            user_data_manager.spreadsheet_url, 
            user_data_manager.sheet_name
        )
        
        if data:
            spreadsheet_data[user_id] = data
            user_data_manager.import_time = datetime.now()
            
            # Перезапуск таймера автоматического удаления
            asyncio.create_task(delete_imported_data(user_id))
            
            await message.answer(
                f"✅ Данные успешно обновлены!\n"
                f"📊 Записей загружено: {len(data)}\n"
                f"⏰ Данные будут автоматически удалены через {Config.AUTO_DELETE_TIMEOUT} секунд"
            )
        else:
            await message.answer("❌ Не удалось обновить данные.")
            
    except Exception as e:
        logger.error(f"Ошибка обновления для пользователя {user_id}: {e}")
        await message.answer(f"❌ Ошибка при обновлении данных: {str(e)}")

# Функция для автоматического удаления импортированных данных
async def delete_imported_data(user_id: int):
    await asyncio.sleep(Config.AUTO_DELETE_TIMEOUT)
    
    if user_id in spreadsheet_data:
        del spreadsheet_data[user_id]
        user_data_manager = UserDataManager.get_user_data(user_id)
        user_data_manager.import_time = None
        
        logger.info(f"Автоматически удалены импортированные данные для пользователя {user_id}")
        
        # Уведомление пользователя
        try:
            await bot.send_message(
                user_id, 
                "🕒 Время хранения импортированных данных истекло. Данные были автоматически удалены.\n"
                "Для продолжения работы импортируйте таблицу заново."
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить пользователя {user_id} об удалении данных: {e}")

# Периодическая очистка старых данных
async def scheduled_cleanup():
    while True:
        await asyncio.sleep(300)  # Каждые 5 минут
        UserDataManager.cleanup_old_data()
        logger.info("Выполнена плановая очистка старых данных")

# Обработчик неизвестных команд
@dp.message()
async def unknown_command(message: types.Message):
    await message.answer(
        "🤔 Неизвестная команда. Используйте кнопки меню или введите /help для справки.",
        reply_markup=Utils.create_main_keyboard()
    )

# Запуск бота
async def main():
    logger.info("Запуск бота...")
    
    # Запуск фоновых задач
    asyncio.create_task(scheduled_cleanup())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
