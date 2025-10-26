import logging
import json
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.executor import start_webhook
from flask import Flask, render_template, jsonify, request

from config import Config

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher(bot)

# Flask приложение для веб-интерфейса
app = Flask(__name__)

# Хранилище для данных (в продакшене используйте БД)
user_sessions = {}
playlists = {}

class HitmosAPI:
    def __init__(self):
        self.base_url = "https://hitmos.me"
    
    async def search_music(self, query: str):
        """Поиск музыки на Hitmos.me"""
        try:
            # Эмуляция поиска (так как API Hitmos может быть недоступно)
            # В реальном приложении замените на реальные API вызовы
            mock_results = [
                {
                    'id': '1',
                    'title': 'Пример трека 1',
                    'artist': 'Исполнитель 1',
                    'cover': 'https://via.placeholder.com/150',
                    'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'
                },
                {
                    'id': '2', 
                    'title': 'Пример трека 2',
                    'artist': 'Исполнитель 2',
                    'cover': 'https://via.placeholder.com/150',
                    'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3'
                }
            ]
            
            # Фильтруем моковые данные по запросу
            filtered_results = [track for track in mock_results 
                              if query.lower() in track['title'].lower() 
                              or query.lower() in track['artist'].lower()]
            
            return filtered_results if filtered_results else mock_results
            
        except Exception as e:
            logging.error(f"Error searching music: {e}")
            return []
    
    async def get_track_url(self, track_id: str):
        """Получение URL трека"""
        try:
            # Моковые URL для демонстрации
            track_urls = {
                '1': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
                '2': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3',
                '3': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3'
            }
            return track_urls.get(track_id)
        except Exception as e:
            logging.error(f"Error getting track URL: {e}")
            return None

hitmos_api = HitmosAPI()

# Команда старт
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    welcome_text = """
🎵 Добро пожаловать в музыкальный плеер! 🎵

*С любовью к нашим подписчикам от Тимура Андреева*

Возможности бота:
• 🔍 Поиск музыки с Hitmos.me
• ▶️ Воспроизведение треков
• 📱 Удобный визуальный интерфейс
• 💾 Сохранение плейлистов

Нажмите кнопку ниже, чтобы открыть музыкальный плеер!
    """
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            "🎵 Открыть музыкальный плеер",
            web_app=WebAppInfo(url=f"{Config.WEBHOOK_URL}/player")
        ),
        InlineKeyboardButton(
            "🔍 Поиск музыки",
            callback_data="search_music"
        )
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчик поиска музыки
@dp.callback_query_handler(lambda c: c.data == 'search_music')
async def process_search(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Введите название трека или исполнителя для поиска:")

# Обработчик текстовых сообщений (поиск)
@dp.message_handler(content_types=types.ContentType.TEXT)
async def process_text_message(message: types.Message):
    search_query = message.text
    
    await message.answer(f"🔍 Ищу музыку по запросу: {search_query}")
    
    # Поиск на Hitmos.me
    results = await hitmos_api.search_music(search_query)
    
    if not results:
        await message.answer("❌ Ничего не найдено. Попробуйте другой запрос.")
        return
    
    # Создаем клавиатуру с результатами
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for i, track in enumerate(results[:5]):  # Ограничиваем 5 результатами
        keyboard.add(
            InlineKeyboardButton(
                f"🎵 {track.get('title', 'Unknown')} - {track.get('artist', 'Unknown')}",
                callback_data=f"play_{track.get('id')}"
            )
        )
    
    keyboard.add(
        InlineKeyboardButton(
            "📱 Открыть в плеере",
            web_app=WebAppInfo(url=f"{Config.WEBHOOK_URL}/player?search={search_query}")
        )
    )
    
    await message.answer("Найденные треки:", reply_markup=keyboard)

# Обработчик воспроизведения трека
@dp.callback_query_handler(lambda c: c.data.startswith('play_'))
async def process_play_track(callback_query: types.CallbackQuery):
    track_id = callback_query.data.replace('play_', '')
    
    # Получаем URL трека
    track_url = await hitmos_api.get_track_url(track_id)
    
    if track_url:
        await callback_query.message.answer_audio(
            track_url,
            caption="🎵 Наслаждайтесь музыкой! \n*С любовью к подписчикам - Тимур Андреев*",
            parse_mode="Markdown"
        )
    else:
        await callback_query.answer("❌ Не удалось загрузить трек", show_alert=True)

# Веб-интерфейс плеера
@app.route('/')
def index():
    return render_template('player.html', search_query='')

@app.route('/player')
def player():
    search_query = request.args.get('search', '')
    return render_template('player.html', search_query=search_query)

# API для поиска музыки
@app.route('/api/search')
async def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    results = await hitmos_api.search_music(query)
    return jsonify(results)

# API для получения трека
@app.route('/api/track/<track_id>')
async def api_track(track_id):
    track_url = await hitmos_api.get_track_url(track_id)
    return jsonify({'url': track_url})

# Статические файлы
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# Обработчик вебхука для Telegram
@app.route('/webhook', methods=['POST'])
async def webhook_handler():
    update = types.Update(**request.json)
    await dp.process_update(update)
    return 'ok'

# Запуск приложения
async def on_startup(dp):
    await bot.set_webhook(Config.WEBHOOK_URL + '/webhook')

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    # Для локальной разработки
    if Config.WEBHOOK_URL.startswith('https://your-domain.com'):
        # Локальный запуск без вебхука
        from aiogram.utils import executor
        executor.start_polling(dp, skip_updates=True)
    else:
        # Продакшен запуск с вебхуком
        start_webhook(
            dispatcher=dp,
            webhook_path='/webhook',
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            host=Config.WEBAPP_HOST,
            port=Config.WEBAPP_PORT
        )
