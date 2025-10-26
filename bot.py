import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pygame
import os
import requests
from urllib.parse import quote
import json
import threading
import time
from datetime import datetime
import yt_dlp
import asyncio
import sys

# С любовью к своим подписчикам - Тимур Андреев ❤️

class MusicBot:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 Music Bot - Тимур Андреев")
        self.root.geometry("1000x700")
        self.root.configure(bg='#1e1e1e')
        
        # Инициализация pygame для воспроизведения
        pygame.mixer.init()
        self.current_track = None
        self.playing = False
        self.paused = False
        self.playlist = []
        self.current_index = 0
        self.volume = 0.7
        
        # Загрузка настроек
        self.settings_file = "music_bot_settings.json"
        self.settings = self.load_settings()
        
        # Создаем папки если нет
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("playlists", exist_ok=True)
        
        self.create_widgets()
        self.apply_settings()
        
    def load_settings(self):
        """Загрузка настроек из файла"""
        default_settings = {
            "theme": "dark",
            "volume": 0.7,
            "download_path": "downloads",
            "auto_play": True,
            "search_provider": "youtube"
        }
        
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")
        
        return default_settings
    
    def save_settings(self):
        """Сохранение настроек в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
    
    def apply_settings(self):
        """Применение настроек"""
        self.volume = self.settings["volume"]
        pygame.mixer.music.set_volume(self.volume)
        os.makedirs(self.settings["download_path"], exist_ok=True)
    
    def create_widgets(self):
        # Стиль
        style = ttk.Style()
        style.configure('Custom.TButton', background='#3498db', foreground='white')
        
        # Главный фрейм
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Заголовок
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill='x', pady=(0, 10))
        
        title = tk.Label(title_frame, text="🎵 Music Bot", 
                        font=('Arial', 20, 'bold'), 
                        bg='#1e1e1e', fg='white')
        title.pack()
        
        subtitle = tk.Label(title_frame, text="Поиск, скачивание и воспроизведение музыки", 
                           font=('Arial', 10), 
                           bg='#1e1e1e', fg='#bdc3c7')
        subtitle.pack()
        
        # Фрейм поиска
        search_frame = ttk.LabelFrame(main_frame, text="🔍 Поиск музыки", padding=10)
        search_frame.pack(fill='x', pady=(0, 10))
        
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill='x')
        
        self.search_entry = ttk.Entry(search_input_frame, font=('Arial', 12))
        self.search_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.search_entry.bind('<Return>', lambda e: self.search_music())
        
        self.search_btn = ttk.Button(search_input_frame, text="Искать", 
                                   command=self.search_music)
        self.search_btn.pack(side='left')
        
        # Результаты поиска
        results_frame = ttk.LabelFrame(main_frame, text="📋 Результаты поиска", padding=10)
        results_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # Таблица результатов
        columns = ('#', 'Название', 'Автор', 'Длительность', 'Действия')
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show='headings', height=8)
        
        # Настройка колонок
        self.results_tree.heading('#', text='#')
        self.results_tree.heading('Название', text='Название')
        self.results_tree.heading('Автор', text='Автор')
        self.results_tree.heading('Длительность', text='Длительность')
        self.results_tree.heading('Действия', text='Действия')
        
        self.results_tree.column('#', width=50)
        self.results_tree.column('Название', width=300)
        self.results_tree.column('Автор', width=200)
        self.results_tree.column('Длительность', width=100)
        self.results_tree.column('Действия', width=150)
        
        self.results_tree.pack(fill='both', expand=True)
        
        # Полоса прокрутки для таблицы
        scrollbar = ttk.Scrollbar(results_frame, orient='vertical', command=self.results_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        # Фрейм управления плеером
        player_frame = ttk.LabelFrame(main_frame, text="🎵 Проигрыватель", padding=10)
        player_frame.pack(fill='x', pady=(0, 10))
        
        # Информация о текущем треке
        self.current_track_label = tk.Label(player_frame, text="Трек не выбран", 
                                          font=('Arial', 12, 'bold'), 
                                          bg='#1e1e1e', fg='white')
        self.current_track_label.pack(anchor='w')
        
        # Элементы управления
        control_frame = ttk.Frame(player_frame)
        control_frame.pack(fill='x', pady=10)
        
        self.play_btn = ttk.Button(control_frame, text="▶️ Воспроизвести", 
                                 command=self.play_music, state='disabled')
        self.play_btn.pack(side='left', padx=5)
        
        self.pause_btn = ttk.Button(control_frame, text="⏸️ Пауза", 
                                  command=self.pause_music, state='disabled')
        self.pause_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹️ Стоп", 
                                 command=self.stop_music, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        self.next_btn = ttk.Button(control_frame, text="⏭️ Следующий", 
                                 command=self.next_track, state='disabled')
        self.next_btn.pack(side='left', padx=5)
        
        self.prev_btn = ttk.Button(control_frame, text="⏮️ Предыдущий", 
                                 command=self.previous_track, state='disabled')
        self.prev_btn.pack(side='left', padx=5)
        
        # Громкость
        volume_frame = ttk.Frame(player_frame)
        volume_frame.pack(fill='x', pady=5)
        
        tk.Label(volume_frame, text="Громкость:", bg='#1e1e1e', fg='white').pack(side='left')
        self.volume_scale = ttk.Scale(volume_frame, from_=0, to=1, orient='horizontal',
                                    command=self.change_volume)
        self.volume_scale.set(self.volume)
        self.volume_scale.pack(side='left', fill='x', expand=True, padx=10)
        
        # Прогресс воспроизведения
        self.progress = ttk.Progressbar(player_frame, mode='determinate')
        self.progress.pack(fill='x', pady=5)
        
        # Статус
        self.status_label = tk.Label(player_frame, text="Готов к работе", 
                                   font=('Arial', 10), 
                                   bg='#1e1e1e', fg='#27ae60')
        self.status_label.pack(anchor='w')
        
        # Фрейм плейлиста
        playlist_frame = ttk.LabelFrame(main_frame, text="🎼 Текущий плейлист", padding=10)
        playlist_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.playlist_text = scrolledtext.ScrolledText(playlist_frame, height=6, 
                                                     font=('Arial', 10))
        self.playlist_text.pack(fill='both', expand=True)
        self.update_playlist_display()
        
        # Нижняя панель
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill='x')
        
        # Кнопки управления
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(side='left')
        
        ttk.Button(btn_frame, text="💾 Сохранить плейлист", 
                 command=self.save_playlist).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📂 Загрузить плейлист", 
                 command=self.load_playlist).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🧹 Очистить плейлист", 
                 command=self.clear_playlist).pack(side='left', padx=5)
        
        # Подпись
        signature = tk.Label(bottom_frame, 
                           text="С любовью к своим подписчикам - Тимур Андреев ❤️", 
                           font=('Arial', 10, 'bold'), 
                           bg='#1e1e1e', fg='#e74c3c')
        signature.pack(side='right')
        
        # Запуск обновления прогресса
        self.update_progress()
    
    def search_music(self):
        """Поиск музыки"""
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Внимание", "Введите поисковый запрос")
            return
        
        self.status_label.config(text="🔍 Поиск...", fg='#f39c12')
        self.search_btn.config(state='disabled')
        
        # Запуск поиска в отдельном потоке
        threading.Thread(target=self._search_music_thread, args=(query,), daemon=True).start()
    
    def _search_music_thread(self, query):
        """Поток поиска музыки"""
        try:
            # Имитация поиска через YouTube/звуковые сервисы
            results = self.mock_search(query)
            
            # Обновление UI в главном потоке
            self.root.after(0, self._display_search_results, results)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка поиска: {str(e)}"))
            self.root.after(0, lambda: self.status_label.config(text="Ошибка поиска", fg='#e74c3c'))
        finally:
            self.root.after(0, lambda: self.search_btn.config(state='normal'))
    
    def mock_search(self, query):
        """Имитация поиска музыки (заглушка)"""
        # В реальном приложении здесь будет интеграция с YouTube API или другими сервисами
        time.sleep(1)  # Имитация задержки поиска
        
        mock_results = [
            {
                'title': f"{query} - Официальный трек",
                'author': "Известный исполнитель",
                'duration': "3:45",
                'url': f"https://example.com/{quote(query)}",
                'video_id': '1'
            },
            {
                'title': f"{query} (Remix)",
                'author': "DJ Remixer",
                'duration': "4:20",
                'url': f"https://example.com/{quote(query)}_remix",
                'video_id': '2'
            },
            {
                'title': f"{query} - Акустическая версия",
                'author': "Акустический исполнитель",
                'duration': "3:15",
                'url': f"https://example.com/{quote(query)}_acoustic",
                'video_id': '3'
            },
            {
                'title': f"Лучшая версия {query}",
                'author': "Разные исполнители",
                'duration': "5:10",
                'url': f"https://example.com/best_{quote(query)}",
                'video_id': '4'
            }
        ]
        
        return mock_results
    
    def _display_search_results(self, results):
        """Отображение результатов поиска"""
        # Очистка предыдущих результатов
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Добавление новых результатов
        for i, result in enumerate(results, 1):
            self.results_tree.insert('', 'end', values=(
                i,
                result['title'],
                result['author'],
                result['duration'],
                "🎵 Добавить 🎵"
            ), tags=(result['video_id'],))
        
        # Привязка событий для кнопок действий
        self.results_tree.bind('<Button-1>', self.on_tree_click)
        
        self.status_label.config(text=f"Найдено результатов: {len(results)}", fg='#27ae60')
    
    def on_tree_click(self, event):
        """Обработка клика по таблице"""
        item = self.results_tree.identify_row(event.y)
        column = self.results_tree.identify_column(event.x)
        
        if item and column == '#5':  # Колонка "Действия"
            video_id = self.results_tree.item(item)['tags'][0]
            track_info = self.get_track_info_from_tree(item)
            self.add_to_playlist(track_info)
    
    def get_track_info_from_tree(self, item):
        """Получение информации о треке из таблицы"""
        values = self.results_tree.item(item)['values']
        return {
            'title': values[1],
            'author': values[2],
            'duration': values[3],
            'video_id': self.results_tree.item(item)['tags'][0]
        }
    
    def add_to_playlist(self, track_info):
        """Добавление трека в плейлист"""
        self.playlist.append(track_info)
        self.update_playlist_display()
        
        if len(self.playlist) == 1 and self.settings['auto_play']:
            self.play_selected_track(0)
        
        self.status_label.config(text=f"✅ Добавлено: {track_info['title']}", fg='#27ae60')
        
        # Активируем кнопки управления если плейлист не пустой
        if len(self.playlist) > 0:
            self.play_btn.config(state='normal')
            self.next_btn.config(state='normal')
            self.prev_btn.config(state='normal')
    
    def update_playlist_display(self):
        """Обновление отображения плейлиста"""
        self.playlist_text.delete(1.0, tk.END)
        
        for i, track in enumerate(self.playlist, 1):
            status = "▶️ " if i-1 == self.current_index and self.playing else ""
            self.playlist_text.insert(tk.END, 
                                    f"{status}{i}. {track['title']} - {track['author']} ({track['duration']})\n")
    
    def play_selected_track(self, index):
        """Воспроизведение выбранного трека"""
        if index < 0 or index >= len(self.playlist):
            return
        
        self.current_index = index
        track = self.playlist[index]
        self.current_track = track
        
        # Имитация воспроизведения (в реальном приложении здесь будет загрузка и воспроизведение)
        self.playing = True
        self.paused = False
        
        self.current_track_label.config(text=f"Сейчас играет: {track['title']} - {track['author']}")
        self.play_btn.config(state='disabled')
        self.pause_btn.config(state='normal')
        self.stop_btn.config(state='normal')
        
        self.status_label.config(text=f"🎵 Воспроизведение: {track['title']}", fg='#3498db')
        self.update_playlist_display()
        
        # Запуск имитации прогресса
        self.progress['maximum'] = 100
        self.progress['value'] = 0
    
    def play_music(self):
        """Воспроизведение музыки"""
        if not self.playlist:
            messagebox.showwarning("Внимание", "Плейлист пуст")
            return
        
        if self.paused:
            # Продолжение воспроизведения после паузы
            pygame.mixer.music.unpause()
            self.paused = False
            self.play_btn.config(state='disabled')
            self.pause_btn.config(state='normal')
            self.status_label.config(text="▶️ Воспроизведение продолжено", fg='#3498db')
        else:
            # Начать воспроизведение с текущего трека
            self.play_selected_track(self.current_index)
    
    def pause_music(self):
        """Пауза музыки"""
        if self.playing and not self.paused:
            pygame.mixer.music.pause()
            self.paused = True
            self.play_btn.config(state='normal')
            self.pause_btn.config(state='disabled')
            self.status_label.config(text="⏸️ Пауза", fg='#f39c12')
    
    def stop_music(self):
        """Остановка музыки"""
        pygame.mixer.music.stop()
        self.playing = False
        self.paused = False
        self.play_btn.config(state='normal')
        self.pause_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.progress['value'] = 0
        self.status_label.config(text="⏹️ Воспроизведение остановлено", fg='#e74c3c')
    
    def next_track(self):
        """Следующий трек"""
        if not self.playlist:
            return
        
        next_index = (self.current_index + 1) % len(self.playlist)
        self.play_selected_track(next_index)
    
    def previous_track(self):
        """Предыдущий трек"""
        if not self.playlist:
            return
        
        prev_index = (self.current_index - 1) % len(self.playlist)
        self.play_selected_track(prev_index)
    
    def change_volume(self, value):
        """Изменение громкости"""
        self.volume = float(value)
        pygame.mixer.music.set_volume(self.volume)
        self.settings['volume'] = self.volume
        self.save_settings()
    
    def update_progress(self):
        """Обновление прогресса воспроизведения"""
        if self.playing and not self.paused:
            current_value = self.progress['value']
            if current_value < self.progress['maximum']:
                self.progress['value'] = current_value + 1
            else:
                # Трек закончился, переходим к следующему
                self.next_track()
        
        self.root.after(1000, self.update_progress)  # Обновление каждую секунду
    
    def save_playlist(self):
        """Сохранение плейлиста"""
        if not self.playlist:
            messagebox.showwarning("Внимание", "Плейлист пуст")
            return
        
        filename = f"playlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join("playlists", filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.playlist, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Успех", f"Плейлист сохранен: {filename}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить плейлист: {str(e)}")
    
    def load_playlist(self):
        """Загрузка плейлиста"""
        try:
            from tkinter import filedialog
            filepath = filedialog.askopenfilename(
                title="Выберите файл плейлиста",
                initialdir="playlists",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if filepath:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.playlist = json.load(f)
                
                self.current_index = 0
                self.update_playlist_display()
                
                if self.playlist and self.settings['auto_play']:
                    self.play_btn.config(state='normal')
                    self.next_btn.config(state='normal')
                    self.prev_btn.config(state='normal')
                
                messagebox.showinfo("Успех", f"Загружено треков: {len(self.playlist)}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить плейлист: {str(e)}")
    
    def clear_playlist(self):
        """Очистка плейлиста"""
        if self.playlist:
            result = messagebox.askyesno("Подтверждение", "Очистить весь плейлист?")
            if result:
                self.playlist.clear()
                self.current_index = 0
                self.stop_music()
                self.update_playlist_display()
                self.current_track_label.config(text="Трек не выбран")
                self.status_label.config(text="Плейлист очищен", fg='#27ae60')

# Создание и запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = MusicBot(root)
    root.mainloop()
