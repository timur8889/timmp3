import os
import logging
import asyncio
from telegram import Update, InlineQueryResultAudio, InputTextMessageContent
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes
import aiohttp
import json
from typing import List, Dict
import hashlib

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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
        self.app.add_handler(InlineQueryHandler(self.inline_query))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        await update.message.reply_text(
            "🎵 Яндекс.Музыка Бот\n\n"
            "Используйте:\n"
            "/search <название> - поиск музыки\n"
            "Или в любом чате: @your_bot_username <запрос>\n\n"
            "Пример: /search Земфира"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        await update.message.reply_text(
            "🎵 Помощь по Яндекс.Музыка боту:\n\n"
            "Команды:\n"
            "/start - начать работу\n"
            "/search <запрос> - поиск музыки\n"
            "/help - эта справка\n\n"
            "Inline режим:\n"
            "В любом чате напишите @your_bot_username и запрос"
        )
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /search"""
        if not context.args:
            await update.message.reply_text("❌ Укажите запрос для поиска\nПример: /search Земфира")
            return
        
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Ищу: {query}...")
        
        results = await self.search_yandex_music(query)
        
        if not results:
            await update.message.reply_text("❌ Ничего не найдено")
            return
        
        # Отправляем первые 5 результатов
        message_text = "🎵 Найденные треки:\n\n"
        for i, track in enumerate(results[:5], 1):
            message_text += f"{i}. {track['artist']} - {track['title']}\n"
        
        message_text += "\n💡 Используйте inline режим для отправки в чаты!"
        await update.message.reply_text(message_text)
    
    async def search_yandex_music(self, query: str) -> List[Dict]:
        """Поиск музыки через Яндекс.Музыка API"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            # Используем публичное API Яндекс.Музыки
            search_url = "https://api.music.yandex.net/search"
            params = {
                'text': query,
                'type': 'track',
                'page': 0,
                'pageSize': 20
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self.parse_search_results(data)
                    else:
                        logging.error(f"API error: {response.status}")
                        return await self.fallback_search(query)
                        
        except Exception as e:
            logging.error(f"Search error: {e}")
            return await self.fallback_search(query)
    
    def parse_search_results(self, data: Dict) -> List[Dict]:
        """Парсинг результатов поиска"""
        results = []
        
        try:
            tracks = data.get('result', {}).get('tracks', {}).get('results', [])
            
            for track in tracks:
                # Получаем прямую ссылку на трек
                download_info = track.get('downloadInfo', [])
                if download_info:
                    # Берем первую доступную ссылку
                    audio_url = download_info[0].get('downloadUrl')
                else:
                    # Альтернативный способ получения ссылки
                    audio_url = f"https://music.yandex.ru/album/{track['albums'][0]['id']}/track/{track['id']}"
                
                results.append({
                    'id': track['id'],
                    'title': track['title'],
                    'artist': ', '.join(artist['name'] for artist in track['artists']),
                    'duration': track.get('durationMs', 0) // 1000,
                    'url': audio_url,
                    'thumbnail': f"https://{track['coverUri'].replace('%%', '400x400')}" if track.get('coverUri') else None
                })
                
        except Exception as e:
            logging.error(f"Parse error: {e}")
        
        return results
    
    async def fallback_search(self, query: str) -> List[Dict]:
        """Резервный поиск через веб-интерфейс"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            search_url = f"https://music.yandex.ru/handlers/music-search.jsx"
            params = {
                'text': query,
                'type': 'tracks',
                'page': 0
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, params=params) as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        return self.parse_fallback_results(data)
                    else:
                        return []
                        
        except Exception as e:
            logging.error(f"Fallback search error: {e}")
            return []
    
    def parse_fallback_results(self, data: Dict) -> List[Dict]:
        """Парсинг результатов резервного поиска"""
        results = []
        
        try:
            tracks = data.get('tracks', {}).get('items', [])
            
            for track in tracks[:15]:  # Ограничиваем количество
                track_info = track.get('track') or track
                
                results.append({
                    'id': track_info['id'],
                    'title': track_info['title'],
                    'artist': ', '.join(artist['name'] for artist in track_info['artists']),
                    'duration': track_info.get('durationMs', 0) // 1000,
                    'url': f"https://music.yandex.ru/album/{track_info['albums'][0]['id']}/track/{track_info['id']}",
                    'thumbnail': f"https://{track_info['coverUri'].replace('%%', '300x300')}" if track_info.get('coverUri') else None
                })
                
        except Exception as e:
            logging.error(f"Fallback parse error: {e}")
        
        return results
    
    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline запросов"""
        query = update.inline_query.query
        
        if not query or len(query) < 2:
            return
        
        logging.info(f"Inline search: {query}")
        
        # Показываем "ищу..." сообщение
        await update.inline_query.answer([
            InlineQueryResultAudio(
                id="searching",
                audio_url="https://example.com/placeholder.mp3",
                title="Ищем музыку...",
                performer="Пожалуйста, подождите"
            )
        ], cache_time=1)
        
        # Ищем музыку
        results = await self.search_yandex_music(query)
        
        inline_results = []
        
        for i, track in enumerate(results[:50]):  # Telegram ограничение
            try:
                # Создаем результат с кэшированным аудио
                result = InlineQueryResultAudio(
                    id=str(track['id']),
                    audio_url=track['url'],
                    title=track['title'][:64],
                    performer=track['artist'][:64],
                    audio_duration=track['duration'],
                    caption=f"🎵 {track['title']}\n🎤 {track['artist']}\n\n💿 Яндекс.Музыка"
                )
                inline_results.append(result)
                
            except Exception as e:
                logging.error(f"Error creating inline result: {e}")
                continue
        
        await update.inline_query.answer(inline_results, cache_time=300)
    
    def run(self):
        """Запуск бота"""
        print("🎵 Яндекс.Музыка бот запущен...")
        self.app.run_polling()

# Альтернативная версия с использованием библиотеки yandex-music
class YandexMusicAPIBot(YandexMusicBot):
    def __init__(self, token: str, yandex_token: str = None):
        try:
            from yandex_music import Client
            self.yandex_client = Client(yandex_token).init() if yandex_token else None
        except ImportError:
            self.yandex_client = None
            logging.warning("yandex-music-api not installed, using web API")
        
        super().__init__(token, yandex_token)
    
    async def search_yandex_music(self, query: str) -> List[Dict]:
        """Поиск через официальную библиотеку yandex-music"""
        if not self.yandex_client:
            return await super().search_yandex_music(query)
        
        try:
            search_result = self.yandex_client.search(query)
            
            if not search_result or not search_result.tracks:
                return []
            
            results = []
            for track in search_result.tracks.results[:20]:
                # Получаем информацию для скачивания
                download_info = track.get_download_info()
                audio_url = None
                
                if download_info:
                    # Получаем прямую ссылку на трек
                    for info in download_info:
                        if info.codec == 'mp3':
                            audio_url = info.get_direct_link()
                            break
                
                results.append({
                    'id': track.id,
                    'title': track.title,
                    'artist': ', '.join(artist.name for artist in track.artists),
                    'duration': track.duration_ms // 1000,
                    'url': audio_url or f"https://music.yandex.ru/album/{track.albums[0].id}/track/{track.id}",
                    'thumbnail': f"https://{track.cover_uri.replace('%%', '400x400')}" if track.cover_uri else None
                })
            
            return results
            
        except Exception as e:
            logging.error(f"Yandex Music API error: {e}")
            return await super().search_yandex_music(query)

# Конфигурация и запуск
if __name__ == "__main__":
    # Токен бота от @BotFather
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    # Токен Яндекс.Музыка (опционально)
    YANDEX_TOKEN = os.getenv('YANDEX_MUSIC_TOKEN') or "YOUR_YANDEX_TOKEN"
    
    # Создаем и запускаем бота
    try:
        # Пробуем использовать официальную API
        bot = YandexMusicAPIBot(BOT_TOKEN, YANDEX_TOKEN)
    except:
        # Fallback на веб-версию
        bot = YandexMusicBot(BOT_TOKEN, YANDEX_TOKEN)
    
    bot.run()
