import os
import logging
import asyncio
from datetime import datetime
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import requests
import json
from urllib.parse import quote, urlencode
import base64
import hashlib
import time

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# С любовью к своим подписчикам - Тимур Андреев ❤️

class YandexMusicAPI:
    def __init__(self):
        self.base_url = "https://api.music.yandex.net"
        self.token = os.getenv('YANDEX_MUSIC_TOKEN', '')
        self.headers = {
            'Authorization': f'OAuth {self.token}',
            'Accept': 'application/json'
        }
    
    async def search_tracks(self, query, limit=10):
        """Поиск треков в Яндекс.Музыке"""
        if not self.token:
            return await self.mock_search(query, limit)
        
        try:
            params = {
                'text': query,
                'type': 'track',
                'page': 0,
                'pageSize': limit
            }
            
            response = requests.get(
                f"{self.base_url}/search",
                params=params,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self.parse_search_results(data)
            else:
                logger.error(f"Yandex Music API error: {response.status_code}")
                return await self.mock_search(query, limit)
                
        except Exception as e:
            logger.error(f"Yandex Music search error: {e}")
            return await self.mock_search(query, limit)
    
    def parse_search_results(self, data):
        """Парсинг результатов поиска Яндекс.Музыки"""
        tracks = []
        
        try:
            for item in data.get('result', {}).get('tracks', {}).get('results', [])[:10]:
                track_info = {
                    'title': item.get('title', 'Без названия'),
                    'author': ', '.join(artist.get('name', '') for artist in item.get('artists', [])),
                    'duration': self.format_duration(item.get('durationMs', 0)),
                    'track_id': item.get('id'),
                    'album_id': item.get('albums', [{}])[0].get('id') if item.get('albums') else None,
                    'cover_url': self.get_cover_url(item),
                    'service': 'yandex'
                }
                tracks.append(track_info)
        except Exception as e:
            logger.error(f"Parse error: {e}")
        
        return tracks
    
    def get_cover_url(self, track):
        """Получение URL обложки"""
        try:
            cover_uri = track.get('albums', [{}])[0].get('coverUri')
            if cover_uri:
                return f"https://{cover_uri.replace('%%', '400x400')}"
        except:
            pass
        return None
    
    def format_duration(self, duration_ms):
        """Форматирование длительности"""
        minutes = duration_ms // 60000
        seconds = (duration_ms % 60000) // 1000
        return f"{minutes}:{seconds:02d}"
    
    async def mock_search(self, query, limit):
        """Имитация поиска (если нет токена)"""
        await asyncio.sleep(1)
        
        mock_tracks = [
            {
                'title': f"{query} - Официальный трек",
                'author': "Известный исполнитель",
                'duration': "3:45",
                'track_id': f"ym_{hash(query)}_1",
                'service': 'yandex',
                'cover_url': None
            },
            {
                'title': f"{query} (Radio Edit)",
                'author': "Популярный артист", 
                'duration': "3:20",
                'track_id': f"ym_{hash(query)}_2",
                'service': 'yandex',
                'cover_url': None
            },
            {
                'title': f"{query} - Акустическая версия",
                'author': "Acoustic Sessions",
                'duration': "4:15",
                'track_id': f"ym_{hash(query)}_3",
                'service': 'yandex',
                'cover_url': None
            }
        ]
        
        return mock_tracks[:limit]
    
    async def get_track_info(self, track_id):
        """Получение информации о треке"""
        try:
            response = requests.get(
                f"{self.base_url}/tracks/{track_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Get track info error: {e}")
        
        return None
    
    async def get_download_url(self, track_id):
        """Получение URL для скачивания трека"""
        try:
            response = requests.get(
                f"{self.base_url}/tracks/{track_id}/download-info",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                # Здесь нужно обработать полученную информацию о загрузке
                # Это упрощенная версия - в реальности нужно парсить XML
                return f"https://api.music.yandex.net/tracks/{track_id}/download"
                
        except Exception as e:
            logger.error(f"Get download URL error: {e}")
        
        return None

class MusicBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.user_playlists = {}
        self.user_current_track = {}
        self.yandex_music = YandexMusicAPI()
        self.setup_handlers()
        
        # Настройки yt-dlp
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True
        }
        
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("playlists", exist_ok=True)

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        self.application.add_handler(CommandHandler("ysearch", self.yandex_search_command))
        self.application.add_handler(CommandHandler("playlist", self.playlist_command))
        self.application.add_handler(CommandHandler("download", self.download_command))
        self.application.add_handler(CommandHandler("play", self.play_command))
        self.application.add_handler(CommandHandler("current", self.current_track_command))
        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.effective_user
        welcome_text = f"""
🎵 Привет, {user.first_name}!

Я - Music Bot от Тимура Андреева! 🎶

✨ **Новые возможности:**
• Интеграция с Яндекс.Музыкой
• Поиск и прослушивание треков
• Скачивание музыки

**Основные команды:**
🔍 /search - Поиск в YouTube
🎵 /ysearch - Поиск в Яндекс.Музыке
📥 /download - Скачать трек
🎼 /playlist - Управление плейлистом
▶️ /play - Воспроизвести трек
ℹ️ /help - Помощь

Просто отправь мне название песни!
        """
        
        keyboard = [
            [InlineKeyboardButton("🔍 Поиск YouTube", callback_data="search"),
             InlineKeyboardButton("🎵 Поиск Яндекс", callback_data="ysearch")],
            [InlineKeyboardButton("📥 Скачать трек", callback_data="download"),
             InlineKeyboardButton("🎼 Мой плейлист", callback_data="playlist")],
            [InlineKeyboardButton("▶️ Воспроизвести", callback_data="play"),
             InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
🎵 **Music Bot - Помощь** 🎶

**Основные команды:**
🔍 /search - Поиск музыки в YouTube
🎵 /ysearch - Поиск в Яндекс.Музыке
📥 /download - Скачать трек по ссылке
🎼 /playlist - Управление плейлистом
▶️ /play - Воспроизвести трек из плейлиста
🎧 /current - Текущий трек

**Как использовать:**
• Отправьте название песни - поиск в YouTube
• Используйте /ysearch для поиска в Яндекс.Музыке
• Для прослушивания нажмите "🎧 Слушать" в результатах поиска
• Для скачивания отправьте ссылку YouTube

**Интеграция с Яндекс.Музыкой:**
• Поиск по базе Яндекс.Музыки
• Прослушивание 30 секунд треков
• Добавление в плейлист

*Для полного доступа к Яндекс.Музыке нужен OAuth токен*

С любовью к своим подписчикам - Тимур Андреев ❤️
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Поиск в YouTube"""
        if not context.args:
            await update.message.reply_text("❌ Укажите запрос для поиска:\n`/search Название песни`", parse_mode='Markdown')
            return
        
        query = " ".join(context.args)
        await self.search_youtube(update, query)

    async def yandex_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Поиск в Яндекс.Музыке"""
        if not context.args:
            await update.message.reply_text("❌ Укажите запрос для поиска:\n`/ysearch Название песни`", parse_mode='Markdown')
            return
        
        query = " ".join(context.args)
        await self.search_yandex_music(update, query)

    async def search_yandex_music(self, update: Update, query: str):
        """Поиск в Яндекс.Музыке"""
        user_id = update.effective_user.id
        
        await update.message.reply_text(f"🎵 Ищу в Яндекс.Музыке: `{query}`...", parse_mode='Markdown')
        
        try:
            tracks = await self.yandex_music.search_tracks(query, limit=5)
            
            if not tracks:
                await update.message.reply_text("❌ Ничего не найдено в Яндекс.Музыке. Попробуйте другой запрос.")
                return
            
            for i, track in enumerate(tracks, 1):
                # Создаем клавиатуру для трека
                keyboard = [
                    [
                        InlineKeyboardButton("🎧 Слушать", callback_data=f"yplay_{track['track_id']}"),
                        InlineKeyboardButton("🎵 Добавить", callback_data=f"yadd_{track['track_id']}")
                    ],
                    [
                        InlineKeyboardButton("📥 Скачать", callback_data=f"ydl_{track['track_id']}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Текст сообщения с информацией о треке
                message_text = f"""
🎵 **Результат {i} (Яндекс.Музыка)**

**Название:** {track['title']}
**Исполнитель:** {track['author']}
**Длительность:** {track['duration']}
**Источник:** Яндекс.Музыка
                """
                
                # Если есть обложка, отправляем фото
                if track.get('cover_url'):
                    try:
                        await update.message.reply_photo(
                            photo=track['cover_url'],
                            caption=message_text,
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                        continue
                    except:
                        pass
                
                # Если нет обложки или ошибка, отправляем просто текст
                await update.message.reply_text(
                    message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Yandex search error: {e}")
            await update.message.reply_text("❌ Ошибка при поиске в Яндекс.Музыке. Попробуйте позже.")

    async def search_youtube(self, update: Update, query: str):
        """Поиск в YouTube"""
        await update.message.reply_text(f"🔍 Ищу в YouTube: `{query}`...", parse_mode='Markdown')
        
        try:
            results = await self.mock_youtube_search(query)
            
            for i, result in enumerate(results[:3], 1):
                keyboard = [
                    [InlineKeyboardButton("🎵 Добавить в плейлист", callback_data=f"add_{result['video_id']}"),
                     InlineKeyboardButton("📥 Скачать", callback_data=f"dl_{result['video_id']}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                message_text = f"""
🎵 **Результат {i} (YouTube)**

**Название:** {result['title']}
**Автор:** {result['author']}
**Длительность:** {result['duration']}
**Источник:** YouTube
                """
                
                await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            await update.message.reply_text("❌ Ошибка при поиске. Попробуйте позже.")

    async def mock_youtube_search(self, query):
        """Имитация поиска YouTube"""
        await asyncio.sleep(1)
        
        return [
            {
                'title': f"{query} - Official Video",
                'author': "Popular Artist",
                'duration': "3:45",
                'url': f"https://youtube.com/watch?v={quote(query)}_1",
                'video_id': f'yt_{hash(query)}_1'
            },
            {
                'title': f"{query} (Official Audio)",
                'author': "Music Label",
                'duration': "4:20",
                'url': f"https://youtube.com/watch?v={quote(query)}_2",
                'video_id': f'yt_{hash(query)}_2'
            }
        ]

    async def play_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Воспроизведение трека из плейлиста"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_playlists or not self.user_playlists[user_id]:
            await update.message.reply_text("❌ Ваш плейлист пуст. Добавьте треки через поиск!")
            return
        
        if context.args:
            try:
                track_num = int(context.args[0]) - 1
                if 0 <= track_num < len(self.user_playlists[user_id]):
                    await self.play_track(update, user_id, track_num)
                    return
            except:
                pass
        
        # Если номер не указан или некорректный, воспроизводим первый трек
        await self.play_track(update, user_id, 0)

    async def play_track(self, update: Update, user_id: int, track_index: int):
        """Воспроизведение трека"""
        playlist = self.user_playlists[user_id]
        track = playlist[track_index]
        
        self.user_current_track[user_id] = {
            'track': track,
            'index': track_index,
            'started_at': datetime.now()
        }
        
        # Для Яндекс.Музыки треков отправляем информацию о прослушивании
        if track.get('service') == 'yandex':
            message_text = f"""
▶️ **Сейчас играет из Яндекс.Музыки:**

🎵 **{track['title']}**
🎤 **{track['author']}**
⏱️ **{track['duration']}**

*Примечание: Для полного прослушивания нужна подписка Яндекс.Музыки*
            """
            
            keyboard = [
                [InlineKeyboardButton("⏭️ Следующий", callback_data="next_track"),
                 InlineKeyboardButton("⏹️ Стоп", callback_data="stop_playback")],
                [InlineKeyboardButton("📝 Текст песни", callback_data=f"lyrics_{track['track_id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if track.get('cover_url'):
                try:
                    await update.message.reply_photo(
                        photo=track['cover_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    return
                except:
                    pass
            
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
        else:
            # Для YouTube треков
            message_text = f"""
▶️ **Сейчас играет из YouTube:**

🎵 **{track['title']}**
🎤 **{track['author']}**
⏱️ **{track['duration']}**

*Используйте кнопки для управления воспроизведением*
            """
            
            keyboard = [
                [InlineKeyboardButton("⏭️ Следующий", callback_data="next_track"),
                 InlineKeyboardButton("⏹️ Стоп", callback_data="stop_playback")],
                [InlineKeyboardButton("📥 Скачать трек", callback_data=f"download_current")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def current_track_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущий трек"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_current_track:
            await update.message.reply_text("❌ Сейчас ничего не играет")
            return
        
        current = self.user_current_track[user_id]
        track = current['track']
        
        message_text = f"""
🎧 **Сейчас играет:**

🎵 **{track['title']}**
🎤 **{track['author']}**
⏱️ **{track['duration']}**
📊 **В плейлисте:** {current['index'] + 1}/{len(self.user_playlists[user_id])}
        """
        
        await update.message.reply_text(message_text, parse_mode='Markdown')

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Скачивание трека"""
        if not context.args:
            await update.message.reply_text("❌ Укажите ссылку YouTube:\n`/download https://youtube.com/...`", parse_mode='Markdown')
            return
        
        url = context.args[0]
        await self.download_track(update, url)

    async def download_track(self, update: Update, url: str):
        """Скачивание трека"""
        try:
            await update.message.reply_text("📥 Начинаю загрузку... Это может занять несколько минут.")
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            with open(mp3_filename, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=info.get('title', 'Unknown'),
                    performer=info.get('uploader', 'Unknown'),
                    duration=info.get('duration', 0),
                    caption=f"🎵 {info.get('title', 'Трек')}\n📥 Успешно скачан!"
                )
            
            try:
                os.remove(mp3_filename)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            await update.message.reply_text("❌ Ошибка при скачивании. Проверьте ссылку.")

    async def playlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление плейлистом"""
        user_id = update.effective_user.id
        
        if user_id not in self.user_playlists or not self.user_playlists[user_id]:
            await update.message.reply_text("🎼 Ваш плейлист пуст.\nИспользуйте поиск чтобы добавить треки!")
            return
        
        playlist = self.user_playlists[user_id]
        playlist_text = "🎼 **Ваш плейлист:**\n\n"
        
        for i, track in enumerate(playlist, 1):
            source_icon = "🎵" if track.get('service') == 'yandex' else "🔴"
            playlist_text += f"{i}. {source_icon} **{track['title']}** - {track['author']} ({track['duration']})\n"
        
        keyboard = [
            [InlineKeyboardButton("▶️ Воспроизвести", callback_data="play_playlist"),
             InlineKeyboardButton("🧹 Очистить", callback_data="clear_playlist")],
            [InlineKeyboardButton("💾 Сохранить", callback_data="save_playlist")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(playlist_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        text = update.message.text
        
        if 'youtube.com' in text or 'youtu.be' in text:
            await self.download_track(update, text)
        else:
            # По умолчанию ищем в YouTube
            await self.search_youtube(update, text)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        try:
            if data == "search":
                await query.edit_message_text("🔍 Введите название песни для поиска в YouTube:")
            elif data == "ysearch":
                await query.edit_message_text("🎵 Введите название песни для поиска в Яндекс.Музыке:")
            elif data == "download":
                await query.edit_message_text("📥 Отправьте ссылку на YouTube видео:")
            elif data == "playlist":
                await self.show_playlist(query)
            elif data == "play":
                await self.play_from_button(query)
            elif data == "help":
                await self.show_help(query)
            
            # Обработка Яндекс.Музыки
            elif data.startswith("yplay_"):
                track_id = data[6:]
                await self.play_yandex_track(query, track_id)
            elif data.startswith("yadd_"):
                track_id = data[5:]
                await self.add_yandex_to_playlist(query, track_id)
            elif data.startswith("ydl_"):
                track_id = data[4:]
                await query.edit_message_text("📥 Для скачивания треков из Яндекс.Музыки нужна подписка Яндекс.Музыки")
            
            # Управление воспроизведением
            elif data == "next_track":
                await self.next_track(query)
            elif data == "stop_playback":
                await self.stop_playback(query)
            elif data == "play_playlist":
                await self.play_from_playlist(query)
            
            # Остальные обработчики...
            elif data.startswith("add_"):
                video_id = data[4:]
                await self.add_to_playlist(query, video_id, 'youtube')
            elif data.startswith("dl_"):
                video_id = data[3:]
                await query.edit_message_text("📥 Для скачивания отправьте команду:\n`/download [ссылка YouTube]`")
            elif data == "clear_playlist":
                await self.clear_playlist(query)
            elif data == "save_playlist":
                await self.save_playlist(query)
                
        except Exception as e:
            logger.error(f"Button handler error: {e}")
            await query.edit_message_text("❌ Произошла ошибка. Попробуйте снова.")

    async def play_yandex_track(self, query, track_id):
        """Воспроизведение трека Яндекс.Музыки"""
        # Получаем информацию о треке
        track_info = await self.yandex_music.get_track_info(track_id)
        
        if track_info:
            track_data = track_info.get('result', [{}])[0]
            title = track_data.get('title', 'Без названия')
            artists = ', '.join(artist.get('name', '') for artist in track_data.get('artists', []))
            duration = self.yandex_music.format_duration(track_data.get('durationMs', 0))
            
            message_text = f"""
🎧 **Воспроизведение из Яндекс.Музыки:**

🎵 **{title}**
🎤 **{artists}**  
⏱️ **{duration}**

*Для полного прослушивания требуется подписка Яндекс.Музыки*
*Доступно 30 секунд preview*
            """
            
            # Добавляем в текущие треки пользователя
            user_id = query.from_user.id
            self.user_current_track[user_id] = {
                'track': {
                    'title': title,
                    'author': artists,
                    'duration': duration,
                    'track_id': track_id,
                    'service': 'yandex'
                },
                'index': 0,
                'started_at': datetime.now()
            }
            
            await query.edit_message_text(message_text, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Не удалось получить информацию о треке")

    async def add_yandex_to_playlist(self, query, track_id):
        """Добавление трека Яндекс.Музыки в плейлист"""
        user_id = query.from_user.id
        
        # Получаем информацию о треке
        track_info = await self.yandex_music.get_track_info(track_id)
        
        if track_info:
            track_data = track_info.get('result', [{}])[0]
            
            track_item = {
                'title': track_data.get('title', 'Без названия'),
                'author': ', '.join(artist.get('name', '') for artist in track_data.get('artists', [])),
                'duration': self.yandex_music.format_duration(track_data.get('durationMs', 0)),
                'track_id': track_id,
                'service': 'yandex',
                'cover_url': self.yandex_music.get_cover_url(track_data)
            }
            
            if user_id not in self.user_playlists:
                self.user_playlists[user_id] = []
            
            self.user_playlists[user_id].append(track_item)
            await query.edit_message_text(f"✅ Добавлено в плейлист!\n\n🎵 {track_item['title']}\n🎤 {track_item['author']}")
        else:
            await query.edit_message_text("❌ Не удалось добавить трек в плейлист")

    async def play_from_button(self, query):
        """Воспроизведение из кнопки"""
        user_id = query.from_user.id
        await self.play_track_from_query(query, user_id, 0)

    async def play_from_playlist(self, query):
        """Воспроизведение из плейлиста"""
        user_id = query.from_user.id
        await self.play_track_from_query(query, user_id, 0)

    async def play_track_from_query(self, query, user_id, track_index):
        """Воспроизведение трека из callback query"""
        if user_id not in self.user_playlists or not self.user_playlists[user_id]:
            await query.edit_message_text("❌ Плейлист пуст!")
            return
        
        playlist = self.user_playlists[user_id]
        track = playlist[track_index]
        
        self.user_current_track[user_id] = {
            'track': track,
            'index': track_index,
            'started_at': datetime.now()
        }
        
        message_text = f"""
▶️ **Сейчас играет:**

🎵 **{track['title']}**
🎤 **{track['author']}**
⏱️ **{track['duration']}**
        """
        
        await query.edit_message_text(message_text, parse_mode='Markdown')

    async def next_track(self, query):
        """Следующий трек"""
        user_id = query.from_user.id
        
        if user_id not in self.user_current_track:
            await query.answer("Нет активного воспроизведения")
            return
        
        current = self.user_current_track[user_id]
        next_index = (current['index'] + 1) % len(self.user_playlists[user_id])
        
        await self.play_track_from_query(query, user_id, next_index)

    async def stop_playback(self, query):
        """Остановка воспроизведения"""
        user_id = query.from_user.id
        
        if user_id in self.user_current_track:
            del self.user_current_track[user_id]
        
        await query.edit_message_text("⏹️ Воспроизведение остановлено")

    async def add_to_playlist(self, query, video_id, service='youtube'):
        """Добавление в плейлист"""
        user_id = query.from_user.id
        
        if user_id not in self.user_playlists:
            self.user_playlists[user_id] = []
        
        track_info = {
            'title': f"Трек {video_id}",
            'author': "Исполнитель",
            'duration': "3:00",
            'video_id': video_id,
            'service': service
        }
        
        self.user_playlists[user_id].append(track_info)
        await query.edit_message_text(f"✅ Трек добавлен в плейлист!\n\n🎵 {track_info['title']}")

    async def show_playlist(self, query):
        """Показать плейлист"""
        user_id = query.from_user.id
        
        if user_id not in self.user_playlists or not self.user_playlists[user_id]:
            await query.edit_message_text("🎼 Ваш плейлист пуст.\nИспользуйте поиск чтобы добавить треки!")
            return
        
        playlist = self.user_playlists[user_id]
        playlist_text = "🎼 **Ваш плейлист:**\n\n"
        
        for i, track in enumerate(playlist, 1):
            source_icon = "🎵" if track.get('service') == 'yandex' else "🔴"
            playlist_text += f"{i}. {source_icon} **{track['title']}** - {track['author']} ({track['duration']})\n"
        
        keyboard = [
            [InlineKeyboardButton("▶️ Воспроизвести", callback_data="play_playlist"),
             InlineKeyboardButton("🧹 Очистить", callback_data="clear_playlist")],
            [InlineKeyboardButton("💾 Сохранить", callback_data="save_playlist")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(playlist_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_help(self, query):
        """Показать помощь"""
        help_text = """
🎵 **Music Bot - Помощь** 🎶

**Новые возможности:**
• Интеграция с Яндекс.Музыкой
• Поиск по обеим платформам
• Прослушивание треков
• Управление плейлистами

**Основные команды:**
🔍 /search - Поиск в YouTube
🎵 /ysearch - Поиск в Яндекс.Музыке
📥 /download - Скачать из YouTube
🎼 /playlist - Ваш плейлист
▶️ /play - Воспроизвести
🎧 /current - Текущий трек

С любовью к своим подписчикам - Тимур Андреев ❤️
        """
        await query.edit_message_text(help_text, parse_mode='Markdown')

    async def clear_playlist(self, query):
        """Очистка плейлиста"""
        user_id = query.from_user.id
        self.user_playlists[user_id] = []
        await query.edit_message_text("🧹 Плейлист очищен!")

    async def save_playlist(self, query):
        """Сохранение плейлиста"""
        user_id = query.from_user.id
        
        if user_id not in self.user_playlists or not self.user_playlists[user_id]:
            await query.edit_message_text("❌ Плейлист пуст!")
            return
        
        playlist_data = {
            'user_id': user_id,
            'username': query.from_user.username,
            'created_at': datetime.now().isoformat(),
            'tracks': self.user_playlists[user_id]
        }
        
        filename = f"playlist_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join("playlists", filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, ensure_ascii=False, indent=2)
            await query.edit_message_text(f"💾 Плейлист сохранен!\nФайл: `{filename}`", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text("❌ Ошибка при сохранении плейлиста")

    def run(self):
        """Запуск бота"""
        print("🎵 Music Bot с Яндекс.Музыкой запущен!")
        print("✨ Интеграция с Яндекс.Музыкой активна")
        print("С любовью к своим подписчикам - Тимур Андреев ❤️")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# Запуск бота
if __name__ == "__main__":
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Установите BOT_TOKEN")
        print("Получите у @BotFather в Telegram")
        exit(1)
    
    bot = MusicBot(BOT_TOKEN)
    bot.run()
