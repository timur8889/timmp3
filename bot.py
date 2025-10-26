import os
import logging
import asyncio
import requests
from telegram import Update, InlineQueryResultAudio, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import aiohttp
import json
from typing import List, Dict
import hashlib
import tempfile
import uuid
from urllib.parse import quote

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class YandexMusicBot:
    def __init__(self, token: str, yandex_token: str = None):
        self.token = token
        self.yandex_token = yandex_token or os.getenv('YANDEX_MUSIC_TOKEN')
        self.app = Application.builder().token(token).build()
        self.setup_handlers()
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("search", self.search_command))
        self.app.add_handler(CommandHandler("menu", self.show_menu))
        self.app.add_handler(CommandHandler("download", self.download_command))
        self.app.add_handler(InlineQueryHandler(self.inline_query))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def get_main_keyboard(self):
        """Главное меню с кнопками"""
        keyboard = [
            [KeyboardButton("🔍 Поиск музыки"), KeyboardButton("🎵 Популярное")],
            [KeyboardButton("📖 Помощь"), KeyboardButton("⚙️ Настройки")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")
    
    def get_search_keyboard(self):
        """Клавиатура для поиска"""
        keyboard = [
            [KeyboardButton("🎸 Рок"), KeyboardButton("🎤 Поп"), KeyboardButton("🎧 Электроника")],
            [KeyboardButton("🎵 Классика"), KeyboardButton("🎼 Джаз"), KeyboardButton("🎹 Хип-хоп")],
            [KeyboardButton("🔙 Назад")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_track_actions_keyboard(self, track_id: str, track_url: str, can_download: bool = True):
        """Инлайн-кнопки для действий с треком"""
        keyboard = [
            [
                InlineKeyboardButton("🎵 Скачать", callback_data=f"download_{track_id}"),
                InlineKeyboardButton("📱 Открыть в Яндекс", url=track_url)
            ]
        ]
        
        if can_download:
            keyboard.append([
                InlineKeyboardButton("▶️ Воспроизвести", callback_data=f"play_{track_id}"),
                InlineKeyboardButton("🔍 Похожие", callback_data=f"similar_{track_id}")
            ])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = (
            "🎵 Добро пожаловать в Яндекс.Музыка Бот!\n\n"
            "Здесь вы можете найти, скачать и послушать любую музыку.\n\n"
            "**Доступные функции:**\n"
            "• 🔍 Поиск музыки\n"
            "• 🎵 Воспроизведение треков\n"
            "• 📥 Скачивание музыки\n"
            "• 🔗 Отправка в чаты\n\n"
            "Выберите действие из меню ниже:"
        )
        
        if update.message:
            await update.message.reply_text(
                welcome_text,
                reply_markup=self.get_main_keyboard(),
                parse_mode='Markdown'
            )
    
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        await update.message.reply_text(
            "🏠 Главное меню:",
            reply_markup=self.get_main_keyboard()
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "🎵 Помощь по Яндекс.Музыка боту:\n\n"
            "🔍 **Поиск музыки:**\n"
            "• Используйте кнопку 'Поиск музыки'\n"
            "• Или команду /search <запрос>\n"
            "• Или inline режим: @your_bot_username <запрос>\n\n"
            "🎵 **Воспроизведение:**\n"
            "• Нажмите '▶️ Воспроизвести' для прослушивания\n"
            "• Используйте inline режим для отправки в чаты\n\n"
            "📥 **Скачивание:**\n"
            "• Нажмите '🎵 Скачать' для загрузки трека\n"
            "• Или используйте /download <запрос>\n\n"
            "🎯 **Быстрый поиск по жанрам:**\n"
            "• Нажмите 'Популярное' для готовых подборок"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔍 Начать поиск", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("📚 Примеры запросов", callback_data="examples")]
        ]
        
        await update.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /search"""
        if not context.args:
            await update.message.reply_text(
                "🔍 Введите запрос для поиска или выберите жанр:",
                reply_markup=self.get_search_keyboard()
            )
            return
        
        query = ' '.join(context.args)
        await self.perform_search(update, query)
    
    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /download"""
        if not context.args:
            await update.message.reply_text(
                "📥 Использование: /download <название трека или исполнитель>\n\n"
                "Пример: /download Земфира Хочешь"
            )
            return
        
        query = ' '.join(context.args)
        await self.perform_download_search(update, query)
    
    async def perform_download_search(self, update: Update, query: str):
        """Поиск трека для скачивания"""
        search_message = await update.message.reply_text(f"🔍 Ищу: **{query}**...", parse_mode='Markdown')
        
        results = await self.search_yandex_music(query)
        
        if not results:
            await search_message.edit_text(f"❌ По запросу **{query}** ничего не найдено", parse_mode='Markdown')
            return
        
        # Показываем результаты для скачивания
        message_text = f"📥 Выберите трек для скачивания (**{query}**):\n\n"
        for i, track in enumerate(results[:5], 1):
            duration = self.format_duration(track['duration'])
            message_text += f"{i}. **{track['title']}** - {track['artist']} ({duration})\n"
        
        keyboard = []
        for i, track in enumerate(results[:5], 1):
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {i}. {track['title'][:20]}...", 
                    callback_data=f"dl_{track['id']}"
                )
            ])
        
        await search_message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def perform_search(self, update: Update, query: str, page: int = 0):
        """Выполнить поиск и показать результаты"""
        try:
            search_message = await update.message.reply_text(f"🔍 Ищу: **{query}**...", parse_mode='Markdown')
            
            results = await self.search_yandex_music(query)
            
            if not results:
                await search_message.edit_text(f"❌ По запросу **{query}** ничего не найдено", parse_mode='Markdown')
                return
            
            # Показываем первые 5 результатов
            message_text = f"🎵 Найдено по запросу **{query}**:\n\n"
            for i, track in enumerate(results[:5], 1):
                duration = self.format_duration(track['duration'])
                message_text += f"{i}. **{track['title']}** - {track['artist']} ({duration})\n"
            
            # Добавляем кнопки действий
            keyboard = []
            for i, track in enumerate(results[:3], 1):
                keyboard.append([
                    InlineKeyboardButton(
                        f"🎵 {i}. {track['title'][:15]}...", 
                        callback_data=f"play_{track['id']}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("📥 Скачать трек", callback_data=f"dlsearch_{query}"),
                InlineKeyboardButton("🔍 Еще результаты", callback_data=f"next_{query}_1")
            ])
            
            await search_message.edit_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Search error: {e}")
            await update.message.reply_text("❌ Произошла ошибка при поиске")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("play_"):
            track_id = data.split("_")[1]
            await self.play_track(query, track_id)
        
        elif data.startswith("download_"):
            track_id = data.split("_")[1]
            await self.download_track(query, track_id)
        
        elif data.startswith("dl_"):
            track_id = data.split("_")[1]
            await self.download_track_callback(query, track_id)
        
        elif data.startswith("dlsearch_"):
            search_query = data.split("_", 1)[1]
            await self.perform_download_search_callback(query, search_query)
        
        elif data.startswith("next_"):
            parts = data.split("_")
            search_query = parts[1]
            page = int(parts[2])
            await self.show_next_results(query, search_query, page)
        
        elif data == "examples":
            await self.show_examples(query)
    
    async def play_track(self, query, track_id):
        """Воспроизвести трек"""
        try:
            await query.edit_message_text("🎵 Получаю информацию о треке...")
            
            # Получаем информацию о треке
            track_info = await self.get_track_info(track_id)
            if not track_info:
                await query.edit_message_text("❌ Не удалось получить информацию о треке")
                return
            
            # Проверяем, есть ли прямая ссылка на аудио
            if track_info.get('audio_url'):
                await query.edit_message_text(
                    f"🎵 **{track_info['title']}**\n"
                    f"🎤 {track_info['artist']}\n"
                    f"⏱ {self.format_duration(track_info['duration'])}\n\n"
                    "▶️ Трек готов к воспроизведению!",
                    parse_mode='Markdown',
                    reply_markup=self.get_track_actions_keyboard(track_id, track_info['url'], True)
                )
                
                # Отправляем аудиофайл
                await query.message.reply_audio(
                    audio=track_info['audio_url'],
                    title=track_info['title'],
                    performer=track_info['artist'],
                    duration=track_info['duration'],
                    reply_markup=self.get_track_actions_keyboard(track_id, track_info['url'], False)
                )
            else:
                # Если прямой ссылки нет, предлагаем альтернативы
                await query.edit_message_text(
                    f"🎵 **{track_info['title']}**\n"
                    f"🎤 {track_info['artist']}\n\n"
                    "⚠️ Прямое воспроизведение недоступно\n"
                    "Используйте следующие варианты:",
                    parse_mode='Markdown',
                    reply_markup=self.get_track_actions_keyboard(track_id, track_info['url'], True)
                )
                
        except Exception as e:
            logger.error(f"Play track error: {e}")
            await query.edit_message_text("❌ Ошибка при воспроизведении трека")
    
    async def download_track_callback(self, query, track_id):
        """Скачать трек (callback версия)"""
        await self.download_track(query, track_id, is_callback=True)
    
    async def download_track(self, query, track_id, is_callback=False):
        """Скачать трек"""
        try:
            if is_callback:
                await query.edit_message_text("📥 Подготавливаю скачивание...")
            else:
                await query.answer("Начинаю скачивание...")
            
            # Получаем информацию о треке
            track_info = await self.get_track_info(track_id)
            if not track_info:
                if is_callback:
                    await query.edit_message_text("❌ Не удалось получить информацию о треке")
                return
            
            # Пытаемся скачать трек
            download_result = await self.download_audio_file(track_info)
            
            if download_result and download_result.get('success'):
                file_path = download_result['file_path']
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Размер в MB
                
                if is_callback:
                    await query.edit_message_text(
                        f"✅ **{track_info['title']}**\n"
                        f"🎤 {track_info['artist']}\n"
                        f"💾 Размер: {file_size:.1f} MB\n\n"
                        "📤 Отправляю файл...",
                        parse_mode='Markdown'
                    )
                
                # Отправляем файл пользователю
                with open(file_path, 'rb') as audio_file:
                    await query.message.reply_audio(
                        audio=audio_file,
                        title=track_info['title'],
                        performer=track_info['artist'],
                        duration=track_info['duration'],
                        caption=f"🎵 {track_info['title']}\n🎤 {track_info['artist']}",
                        reply_markup=self.get_track_actions_keyboard(track_id, track_info['url'], False)
                    )
                
                # Удаляем временный файл
                os.remove(file_path)
                
            else:
                error_msg = "❌ Не удалось скачать трек. Попробуйте другой трек или воспользуйтесь ссылкой на Яндекс.Музыку."
                if is_callback:
                    await query.edit_message_text(
                        error_msg,
                        reply_markup=self.get_track_actions_keyboard(track_id, track_info['url'], True)
                    )
                else:
                    await query.message.reply_text(error_msg)
                    
        except Exception as e:
            logger.error(f"Download track error: {e}")
            error_msg = "❌ Ошибка при скачивании трека"
            if is_callback:
                await query.edit_message_text(error_msg)
            else:
                await query.message.reply_text(error_msg)
    
    async def perform_download_search_callback(self, query, search_query):
        """Поиск для скачивания (callback версия)"""
        await query.edit_message_text(f"🔍 Ищу: **{search_query}**...", parse_mode='Markdown')
        
        results = await self.search_yandex_music(search_query)
        
        if not results:
            await query.edit_message_text(f"❌ По запросу **{search_query}** ничего не найдено", parse_mode='Markdown')
            return
        
        message_text = f"📥 Выберите трек для скачивания (**{search_query}**):\n\n"
        for i, track in enumerate(results[:5], 1):
            duration = self.format_duration(track['duration'])
            message_text += f"{i}. **{track['title']}** - {track['artist']} ({duration})\n"
        
        keyboard = []
        for i, track in enumerate(results[:5], 1):
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {i}. {track['title'][:20]}...", 
                    callback_data=f"dl_{track['id']}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("🔙 Назад к поиску", callback_data=f"back_search_{search_query}")
        ])
        
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def show_next_results(self, query, search_query, page):
        """Показать следующие результаты"""
        try:
            results = await self.search_yandex_music(search_query)
            
            if not results or len(results) <= page * 5:
                await query.edit_message_text("❌ Больше результатов нет")
                return
            
            start_idx = page * 5
            end_idx = start_idx + 5
            
            message_text = f"🎵 Результаты по запросу **{search_query}** (стр. {page+1}):\n\n"
            for i, track in enumerate(results[start_idx:end_idx], start_idx + 1):
                duration = self.format_duration(track['duration'])
                message_text += f"{i}. **{track['title']}** - {track['artist']} ({duration})\n"
            
            keyboard = []
            for i, track in enumerate(results[start_idx:start_idx+3], start_idx + 1):
                keyboard.append([
                    InlineKeyboardButton(
                        f"🎵 {i}. {track['title'][:15]}...", 
                        callback_data=f"play_{track['id']}"
                    )
                ])
            
            # Кнопки пагинации
            pagination_buttons = []
            if page > 0:
                pagination_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"next_{search_query}_{page-1}"))
            
            if len(results) > end_idx:
                pagination_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"next_{search_query}_{page+1}"))
            
            if pagination_buttons:
                keyboard.append(pagination_buttons)
            
            keyboard.append([
                InlineKeyboardButton("📥 Скачать трек", callback_data=f"dlsearch_{search_query}"),
                InlineKeyboardButton("🔍 Новый поиск", switch_inline_query_current_chat="")
            ])
            
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Next results error: {e}")
            await query.edit_message_text("❌ Произошла ошибка при загрузке результатов")
    
    async def show_examples(self, query):
        """Показать примеры запросов"""
        examples_text = (
            "🎯 **Примеры запросов для поиска:**\n\n"
            "• `Земфира` - поиск исполнителя\n"
            "• `Любэ Позови меня` - трек по названию\n"
            "• `рок 90-х` - музыка по жанру\n"
            "• `саундтрек интерстеллар` - саундтреки\n"
            "• `для тренировки` - подборки\n\n"
            "💡 **Совет:** Используйте команду /download для прямого скачивания!"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔍 Попробовать поиск", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("📥 Скачать музыку", callback_data="download_example")]
        ]
        
        await query.edit_message_text(
            examples_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (для кнопок)"""
        text = update.message.text
        
        if text == "🔍 Поиск музыки":
            await update.message.reply_text(
                "Введите запрос для поиска или выберите жанр:",
                reply_markup=self.get_search_keyboard()
            )
        
        elif text == "🎵 Популярное":
            await self.show_popular(update)
        
        elif text == "📖 Помощь":
            await self.help(update, context)
        
        elif text == "⚙️ Настройки":
            await update.message.reply_text(
                "⚙️ Настройки бота:\n\n"
                "• Формат скачивания: MP3\n"
                "• Качество: Высокое\n"
                "• Лимит поиска: 20 треков\n\n"
                "Настройки будут доступны для изменения в следующем обновлении!"
            )
        
        elif text == "🔙 Назад":
            await self.show_menu(update, context)
        
        elif text in ["🎸 Рок", "🎤 Поп", "🎧 Электроника", "🎵 Классика", "🎼 Джаз", "🎹 Хип-хоп"]:
            genre = text.split(" ")[1]
            await self.search_by_genre(update, genre)
        
        elif text.startswith("🎯 "):
            query = text[2:]
            await self.perform_search(update, query)
        
        else:
            await self.perform_search(update, text)
    
    async def show_popular(self, update: Update):
        """Показать популярные треки"""
        popular_queries = ["Топ 100", "Новинки", "Чарт Яндекс.Музыки", "Популярное сегодня"]
        
        keyboard = []
        for query in popular_queries:
            keyboard.append([KeyboardButton(f"🎯 {query}")])
        keyboard.append([KeyboardButton("🔙 Назад")])
        
        await update.message.reply_text(
            "🎵 Популярные подборки:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    
    async def search_by_genre(self, update: Update, genre: str):
        """Поиск по жанру"""
        genre_queries = {
            "Рок": "русский рок 2024",
            "Поп": "популярная музыка 2024",
            "Электроника": "электронная музыка",
            "Классика": "классическая музыка",
            "Джаз": "джаз музыка",
            "Хип-хоп": "русский хип-хоп 2024"
        }
        
        query = genre_queries.get(genre, genre)
        await self.perform_search(update, query)

    # Методы для работы с музыкой
    async def search_yandex_music(self, query: str) -> List[Dict]:
        """Поиск музыки через Яндекс.Музыка API"""
        try:
            # Используем мок-данные для демонстрации
            # В реальном приложении замените на реальный API
            return await self.mock_search_results(query)
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return await self.mock_search_results(query)
    
    async def mock_search_results(self, query: str) -> List[Dict]:
        """Мок-данные для демонстрации"""
        # В реальном приложении замените на реальный API вызов
        mock_data = {
            "земфира": [
                {
                    'id': 'zemfira_1',
                    'title': 'Хочешь',
                    'artist': 'Земфира',
                    'duration': 240,
                    'url': 'https://music.yandex.ru/album/123/track/456',
                    'thumbnail': None,
                    'audio_url': 'https://example.com/audio1.mp3'
                },
                {
                    'id': 'zemfira_2',
                    'title': 'Искала',
                    'artist': 'Земфира',
                    'duration': 210,
                    'url': 'https://music.yandex.ru/album/123/track/789',
                    'thumbnail': None,
                    'audio_url': 'https://example.com/audio2.mp3'
                }
            ],
            "рок": [
                {
                    'id': 'rock_1',
                    'title': 'Группа крови',
                    'artist': 'Кино',
                    'duration': 290,
                    'url': 'https://music.yandex.ru/album/456/track/123',
                    'thumbnail': None,
                    'audio_url': 'https://example.com/audio3.mp3'
                }
            ]
        }
        
        query_lower = query.lower()
        for key in mock_data:
            if key in query_lower:
                return mock_data[key]
        
        # Возвращаем общие мок-данные
        return [
            {
                'id': f'track_{hashlib.md5(query.encode()).hexdigest()[:8]}',
                'title': f'Пример трека ({query})',
                'artist': 'Исполнитель',
                'duration': 180,
                'url': f'https://music.yandex.ru/search?text={quote(query)}',
                'thumbnail': None,
                'audio_url': 'https://example.com/audio_sample.mp3'
            }
        ]
    
    async def get_track_info(self, track_id: str) -> Dict:
        """Получить информацию о треке по ID"""
        try:
            # В реальном приложении замените на реальный API вызов
            # Здесь используем мок-данные
            mock_tracks = {
                'zemfira_1': {
                    'id': 'zemfira_1',
                    'title': 'Хочешь',
                    'artist': 'Земфира',
                    'duration': 240,
                    'url': 'https://music.yandex.ru/album/123/track/456',
                    'thumbnail': None,
                    'audio_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'  # Реальная тестовая ссылка
                },
                'zemfira_2': {
                    'id': 'zemfira_2', 
                    'title': 'Искала',
                    'artist': 'Земфира',
                    'duration': 210,
                    'url': 'https://music.yandex.ru/album/123/track/789',
                    'thumbnail': None,
                    'audio_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3'
                },
                'rock_1': {
                    'id': 'rock_1',
                    'title': 'Группа крови',
                    'artist': 'Кино',
                    'duration': 290,
                    'url': 'https://music.yandex.ru/album/456/track/123',
                    'thumbnail': None,
                    'audio_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3'
                }
            }
            
            # Если трек не найден в мок-данных, создаем базовую информацию
            if track_id not in mock_tracks:
                return {
                    'id': track_id,
                    'title': 'Неизвестный трек',
                    'artist': 'Неизвестный исполнитель',
                    'duration': 180,
                    'url': f'https://music.yandex.ru/track/{track_id}',
                    'thumbnail': None,
                    'audio_url': None
                }
            
            return mock_tracks[track_id]
            
        except Exception as e:
            logger.error(f"Get track info error: {e}")
            return None
    
    async def download_audio_file(self, track_info: Dict) -> Dict:
        """Скачать аудиофайл"""
        try:
            if not track_info.get('audio_url'):
                return {'success': False, 'error': 'No audio URL'}
            
            # Создаем временный файл
            filename = f"{track_info['id']}_{uuid.uuid4().hex[:8]}.mp3"
            file_path = os.path.join(self.download_dir, filename)
            
            # Скачиваем файл
            async with aiohttp.ClientSession() as session:
                async with session.get(track_info['audio_url']) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                        
                        return {'success': True, 'file_path': file_path}
                    else:
                        return {'success': False, 'error': f'HTTP {response.status}'}
                        
        except Exception as e:
            logger.error(f"Download audio error: {e}")
            return {'success': False, 'error': str(e)}
    
    def format_duration(self, seconds: int) -> str:
        """Форматирование длительности трека"""
        if not seconds:
            return "0:00"
        
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline запросов"""
        query = update.inline_query.query
        
        if not query or len(query) < 2:
            await update.inline_query.answer([
                InlineQueryResultAudio(
                    id="help",
                    audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                    title="Введите запрос для поиска музыки",
                    performer="Например: Земфира, рок музыка"
                )
            ], cache_time=300)
            return
        
        logger.info(f"Inline search: {query}")
        
        try:
            results = await self.search_yandex_music(query)
            
            inline_results = []
            
            for i, track in enumerate(results[:50]):
                try:
                    # Используем реальные тестовые аудио для демонстрации
                    audio_url = track.get('audio_url') or f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{(i % 3) + 1}.mp3"
                    
                    result = InlineQueryResultAudio(
                        id=f"{track['id']}_{hashlib.md5(query.encode()).hexdigest()[:8]}",
                        audio_url=audio_url,
                        title=track['title'][:64],
                        performer=track['artist'][:64],
                        audio_duration=track['duration'] or 180,
                        caption=f"🎵 {track['title']}\n🎤 {track['artist']}\n\n💿 Яндекс.Музыка",
                        reply_markup=self.get_track_actions_keyboard(track['id'], track['url'], True)
                    )
                    inline_results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error creating inline result: {e}")
                    continue
            
            if not inline_results:
                inline_results.append(
                    InlineQueryResultAudio(
                        id="no_results",
                        audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                        title="Ничего не найдено",
                        performer="Попробуйте другой запрос"
                    )
                )
            
            await update.inline_query.answer(inline_results, cache_time=300, auto_pagination=True)
            
        except Exception as e:
            logger.error(f"Inline query error: {e}")
            await update.inline_query.answer([], cache_time=300)
    
    def run(self):
        """Запуск бота"""
        print("🎵 Яндекс.Музыка бот запущен...")
        print("✅ Функции воспроизведения и скачивания активны!")
        print("⚠️  Для работы с реальным API Яндекс.Музыки замените mock-методы на реальные API вызовы")
        self.app.run_polling()

# Конфигурация и запуск
if __name__ == "__main__":
    BOT_TOKEN = "8313764660:AAEOFtGphxmLLz7JKSa82a179-vTvjBu1lo"
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Пожалуйста, установите правильный BOT_TOKEN")
        exit(1)
    
    try:
        bot = YandexMusicBot(BOT_TOKEN)
        print("✅ Бот успешно запущен с функциями воспроизведения и скачивания!")
        bot.run()
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
