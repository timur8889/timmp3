import logging
import json
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.executor import set_webhook
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
        self.base_url = Config.HITMOS_API_URL
    
    async def search_music(self, query: str):
        """Поиск музыки на Hitmos.me"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/search", params={"q": query}) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logging.error(f"Error searching music: {e}")
            return []
    
    async def get_track_url(self, track_id: str):
        """Получение URL трека"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/track/{track_id}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('url')
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
    
    for i, track in enumerate(results[:10]):  # Ограничиваем 10 результатами
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

# Запуск приложения
if __name__ == '__main__':
    set_webhook(
        dispatcher=dp,
        webhook_path='/webhook',
        skip_updates=True,
        on_startup=None,
        on_shutdown=None,
        web_app=app,
        host=Config.WEBAPP_HOST,
        port=Config.WEBAPP_PORT
    )
