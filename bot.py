import os
import logging
import asyncio
from telegram import Update, InlineQueryResultAudio, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import aiohttp
import json
from typing import List, Dict
import hashlib

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
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("search", self.search_command))
        self.app.add_handler(CommandHandler("menu", self.show_menu))
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
    
    def get_track_actions_keyboard(self, track_id: str, track_url: str):
        """Инлайн-кнопки для действий с треком"""
        keyboard = [
            [
                InlineKeyboardButton("🎵 Скачать", callback_data=f"download_{track_id}"),
                InlineKeyboardButton("📱 Открыть в Яндекс", url=track_url)
            ],
            [
                InlineKeyboardButton("➕ Добавить в плейлист", callback_data=f"add_{track_id}"),
                InlineKeyboardButton("🔍 Похожие", callback_data=f"similar_{track_id}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = (
            "🎵 Добро пожаловать в Яндекс.Музыка Бот!\n\n"
            "Здесь вы можете найти и послушать любую музыку.\n\n"
            "Выберите действие из меню ниже:"
        )
        
        if update.message:
            await update.message.reply_text(
                welcome_text,
                reply_markup=self.get_main_keyboard()
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
            "🎯 **Быстрый поиск по жанрам:**\n"
            "• Нажмите 'Популярное' для готовых подборок\n\n"
            "📱 **Inline режим:**\n"
            "В любом чате напишите @your_bot_username и запрос для поиска"
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
            # Показываем клавиатуру для поиска
            await update.message.reply_text(
                "🔍 Введите запрос для поиска или выберите жанр:",
                reply_markup=self.get_search_keyboard()
            )
            return
        
        query = ' '.join(context.args)
        await self.perform_search(update, query)
    
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
                message_text += f"{i}. **{track['title']}** - {track['artist']}\n"
            
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
                InlineKeyboardButton("🔍 Искать еще", switch_inline_query_current_chat=query),
                InlineKeyboardButton("📄 Следующие результаты", callback_data=f"next_{query}_1")
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
        
        elif data.startswith("next_"):
            parts = data.split("_")
            search_query = parts[1]
            page = int(parts[2])
            await self.show_next_results(query, search_query, page)
        
        elif data == "examples":
            await self.show_examples(query)
    
    async def play_track(self, query, track_id):
        """Воспроизвести трек"""
        await query.edit_message_text(
            "🎵 Подготавливаю трек...\n\n"
            "⚠️ Функция воспроизведения в разработке\n"
            "Используйте inline режим для отправки треков"
        )
    
    async def download_track(self, query, track_id):
        """Скачать трек"""
        await query.edit_message_text(
            "📥 Подготавливаю скачивание...\n\n"
            "⚠️ Функция скачивания в разработке\n"
            "Используйте inline режим для прослушивания"
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
                message_text += f"{i}. **{track['title']}** - {track['artist']}\n"
            
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
            "💡 **Совет:** Используйте inline режим для быстрого доступа!"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔍 Попробовать поиск", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("🎵 Случайный трек", callback_data="random")]
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
            await update.message.reply_text("⚙️ Настройки бота:\n\nДоступны в следующем обновлении!")
        
        elif text == "🔙 Назад":
            await self.show_menu(update, context)
        
        elif text in ["🎸 Рок", "🎤 Поп", "🎧 Электроника", "🎵 Классика", "🎼 Джаз", "🎹 Хип-хоп"]:
            genre = text.split(" ")[1]  # Убираем эмодзи
            await self.search_by_genre(update, genre)
        
        elif text.startswith("🎯 "):
            query = text[2:]  # Убираем эмодзи
            await self.perform_search(update, query)
        
        else:
            # Если сообщение не команда, считаем его поисковым запросом
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

    async def search_yandex_music(self, query: str) -> List[Dict]:
        """Поиск музыки через Яндекс.Музыка API"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
            }
            
            # Используем публичное API Яндекс.Музыки через прокси
            search_url = "https://api.music.yandex.net/search"
            params = {
                'text': query,
                'type': 'track',
                'page': 0,
                'pageSize': 20
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self.parse_search_results(data)
                    else:
                        logger.error(f"API error: {response.status}")
                        return await self.fallback_search(query)
                        
        except Exception as e:
            logger.error(f"Search error: {e}")
            return await self.fallback_search(query)
    
    def parse_search_results(self, data: Dict) -> List[Dict]:
        """Парсинг результатов поиска"""
        results = []
        
        try:
            tracks = data.get('result', {}).get('tracks', {}).get('results', [])
            
            for track in tracks:
                # Базовая информация о треке
                track_info = {
                    'id': str(track['id']),
                    'title': track['title'],
                    'artist': ', '.join(artist['name'] for artist in track['artists']),
                    'duration': track.get('durationMs', 0) // 1000,
                    'url': f"https://music.yandex.ru/album/{track['albums'][0]['id']}/track/{track['id']}",
                    'thumbnail': f"https://{track['coverUri'].replace('%%', '400x400')}" if track.get('coverUri') else None
                }
                
                # Пытаемся получить прямую ссылку на аудио
                download_info = track.get('downloadInfo', [])
                if download_info:
                    download_url = download_info[0].get('downloadUrl')
                    if download_url:
                        track_info['audio_url'] = download_url
                
                results.append(track_info)
                
        except Exception as e:
            logger.error(f"Parse error: {e}")
        
        return results[:15]  # Ограничиваем количество результатов
    
    async def fallback_search(self, query: str) -> List[Dict]:
        """Резервный поиск через веб-интерфейс"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
            }
            
            # Альтернативный эндпоинт для поиска
            search_url = f"https://music.yandex.ru/handlers/music-search.jsx"
            params = {
                'text': query,
                'type': 'tracks',
                'page': 0,
                'lang': 'ru'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        # Иногда ответ может быть в формате JSONP
                        if text.startswith('('):
                            text = text[1:-1]
                        data = json.loads(text)
                        return self.parse_fallback_results(data)
                    else:
                        return []
                        
        except Exception as e:
            logger.error(f"Fallback search error: {e}")
            return []
    
    def parse_fallback_results(self, data: Dict) -> List[Dict]:
        """Парсинг результатов резервного поиска"""
        results = []
        
        try:
            tracks = data.get('tracks', {}).get('items', [])
            
            for track in tracks[:15]:
                track_info = track.get('track') or track
                
                results.append({
                    'id': str(track_info['id']),
                    'title': track_info['title'],
                    'artist': ', '.join(artist['name'] for artist in track_info['artists']),
                    'duration': track_info.get('durationMs', 0) // 1000,
                    'url': f"https://music.yandex.ru/album/{track_info['albums'][0]['id']}/track/{track_info['id']}",
                    'thumbnail': f"https://{track_info['coverUri'].replace('%%', '300x300')}" if track_info.get('coverUri') else None,
                    'audio_url': None  # Прямые ссылки недоступны через этот метод
                })
                
        except Exception as e:
            logger.error(f"Fallback parse error: {e}")
        
        return results
    
    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline запросов"""
        query = update.inline_query.query
        
        if not query or len(query) < 2:
            # Показываем подсказку при пустом запросе
            await update.inline_query.answer([
                InlineQueryResultAudio(
                    id="help",
                    audio_url="https://example.com/placeholder.mp3",
                    title="Введите запрос для поиска музыки",
                    performer="Например: Земфира, рок музыка, саундтреки"
                )
            ], cache_time=300)
            return
        
        logger.info(f"Inline search: {query}")
        
        try:
            # Ищем музыку
            results = await self.search_yandex_music(query)
            
            inline_results = []
            
            for i, track in enumerate(results[:50]):
                try:
                    # Для inline режима нужна прямая ссылка на аудио
                    # Если прямой ссылки нет, используем placeholder
                    audio_url = track.get('audio_url') or "https://example.com/placeholder.mp3"
                    
                    result = InlineQueryResultAudio(
                        id=f"{track['id']}_{hashlib.md5(query.encode()).hexdigest()[:8]}",
                        audio_url=audio_url,
                        title=track['title'][:64],
                        performer=track['artist'][:64],
                        audio_duration=track['duration'] or 180,
                        caption=f"🎵 {track['title']}\n🎤 {track['artist']}\n\n💿 Яндекс.Музыка",
                        reply_markup=self.get_track_actions_keyboard(track['id'], track['url'])
                    )
                    inline_results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error creating inline result: {e}")
                    continue
            
            if not inline_results:
                inline_results.append(
                    InlineQueryResultAudio(
                        id="no_results",
                        audio_url="https://example.com/placeholder.mp3",
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
        self.app.run_polling()

# Упрощенная версия без yandex-music-api зависимости
class SimpleYandexMusicBot(YandexMusicBot):
    """Упрощенная версия бота без внешних зависимостей"""
    
    async def search_yandex_music(self, query: str) -> List[Dict]:
        """Упрощенный поиск через публичные API"""
        try:
            # Используем мок-данные для демонстрации
            # В реальном приложении здесь должен быть настоящий API запрос
            mock_results = [
                {
                    'id': '1',
                    'title': 'Пример трека 1',
                    'artist': 'Исполнитель 1',
                    'duration': 180,
                    'url': 'https://music.yandex.ru/album/123/track/456',
                    'thumbnail': None,
                    'audio_url': 'https://example.com/audio1.mp3'
                },
                {
                    'id': '2', 
                    'title': 'Пример трека 2',
                    'artist': 'Исполнитель 2',
                    'duration': 200,
                    'url': 'https://music.yandex.ru/album/789/track/012',
                    'thumbnail': None,
                    'audio_url': 'https://example.com/audio2.mp3'
                }
            ]
            
            # Для реальных запросов возвращаем мок-данные
            # Замените это на реальный API вызов
            return mock_results
            
        except Exception as e:
            logger.error(f"Simple search error: {e}")
            return []

# Конфигурация и запуск
if __name__ == "__main__":
    # Токен бота от @BotFather
    BOT_TOKEN = "8313764660:AAEOFtGphxmLLz7JKSa82a179-vTvjBu1lo"
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Пожалуйста, установите правильный BOT_TOKEN")
        exit(1)
    
    # Создаем и запускаем бота
    try:
        bot = SimpleYandexMusicBot(BOT_TOKEN)
        print("✅ Бот успешно запущен!")
        bot.run()
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
