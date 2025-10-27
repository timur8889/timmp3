import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from flask import Flask, render_template, jsonify, request
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
WEBAPP_URL = os.getenv('WEBAPP_URL', 'http://localhost:5000')

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Flask приложение
app = Flask(__name__)

class MusicAPI:
    def __init__(self):
        self.tracks = [
            {
                'id': '1',
                'title': 'Summer Vibes',
                'artist': 'Ocean Waves',
                'cover': 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=150',
                'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
                'duration': '3:45'
            },
            {
                'id': '2',
                'title': 'Night Drive', 
                'artist': 'City Lights',
                'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=150',
                'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3',
                'duration': '4:20'
            },
            {
                'id': '3',
                'title': 'Morning Coffee',
                'artist': 'Jazz Ensemble',
                'cover': 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=150',
                'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3',
                'duration': '2:55'
            },
            {
                'id': '4',
                'title': 'Forest Walk',
                'artist': 'Nature Sounds',
                'cover': 'https://images.unsplash.com/photo-1518837695005-2083093ee35b?w=150',
                'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3',
                'duration': '5:10'
            },
            {
                'id': '5',
                'title': 'Urban Rhythm',
                'artist': 'Street Beats', 
                'cover': 'https://images.unsplash.com/photo-1498038432885-c6f3f1b912ee?w=150',
                'url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3',
                'duration': '3:30'
            }
        ]
    
    def search_music(self, query: str):
        """Поиск музыки"""
        if not query:
            return self.tracks
        
        query = query.lower()
        results = []
        for track in self.tracks:
            if (query in track['title'].lower() or 
                query in track['artist'].lower()):
                results.append(track)
        
        return results if results else self.tracks
    
    def get_track(self, track_id: str):
        """Получение трека по ID"""
        for track in self.tracks:
            if track['id'] == track_id:
                return track
        return None

music_api = MusicAPI()

# Команда старт
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    welcome_text = """
🎵 <b>Музыкальный Плеер</b> 🎵

<i>С любовью к подписчикам - Тимур Андреев</i>

✨ <b>Возможности:</b>
• 🎧 Прослушивание треков
• 🔍 Поиск музыки  
• 📱 Удобный плеер
• 💫 Красивый дизайн

Нажмите кнопку ниже, чтобы открыть музыкальный плеер!
    """
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            "🎵 Открыть Музыкальный Плеер",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/player")
        )
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# Обработчик текстовых сообщений (поиск)
@dp.message_handler(content_types=types.ContentType.TEXT)
async def process_text_message(message: types.Message):
    search_query = message.text
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            "🔍 Искать в плеере", 
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/player?search={search_query}")
        )
    )
    
    await message.answer(
        f"🔍 <b>Поиск:</b> {search_query}\n\nНажмите кнопку ниже для поиска в музыкальном плеере:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

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
def api_search():
    query = request.args.get('q', '')
    results = music_api.search_music(query)
    return jsonify(results)

# API для получения трека
@app.route('/api/track/<track_id>')
def api_track(track_id):
    track = music_api.get_track(track_id)
    if track:
        return jsonify(track)
    return jsonify({'error': 'Track not found'}), 404

# Запуск Flask
def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    from aiogram import executor
    import threading
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота
    executor.start_polling(dp, skip_updates=True)
