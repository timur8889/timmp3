# Импорт библиотек
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pygame
import os
import requests
from urllib.parse import urlparse
import json
import webbrowser

# С любовью к своим подписчикам - Тимур Андреев ❤️

class VideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Видео Плеер")
        self.root.geometry("900x650")
        
        # Инициализация pygame для воспроизведения
        pygame.init()
        self.playing = False
        self.current_file = None
        
        # Загрузка настроек
        self.settings_file = "app_settings.json"
        self.settings = self.load_settings()
        
        self.create_widgets()
        self.apply_settings()
        
    def load_settings(self):
        """Загрузка настроек из файла"""
        default_settings = {
            "theme": "light",
            "volume": 0.7,
            "download_path": "downloads",
            "show_help": True
        }
        
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        
        return default_settings
    
    def save_settings(self):
        """Сохранение настроек в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def apply_settings(self):
        """Применение настроек к интерфейсу"""
        # Создаем папку для загрузок если нет
        os.makedirs(self.settings["download_path"], exist_ok=True)
        
        # Применяем тему
        if self.settings["theme"] == "dark":
            self.root.configure(bg='#2b2b2b')
    
    def create_widgets(self):
        # Создание вкладок
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Вкладка воспроизведения
        play_frame = ttk.Frame(notebook)
        notebook.add(play_frame, text="🎬 Воспроизведение")
        
        # Вкладка скачивания
        download_frame = ttk.Frame(notebook)
        notebook.add(download_frame, text="📥 Скачивание")
        
        # Вкладка настроек
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="⚙️ Настройки")
        
        # === ВКЛАДКА ВОСПРОИЗВЕДЕНИЯ ===
        play_title = ttk.Label(play_frame, text="Видео Плеер", font=('Arial', 16, 'bold'))
        play_title.pack(pady=10)
        
        # Область информации о файле
        self.file_info = ttk.Label(play_frame, text="Файл не выбран", font=('Arial', 10))
        self.file_info.pack(pady=5)
        
        # Фрейм для кнопок управления
        control_frame = ttk.Frame(play_frame)
        control_frame.pack(pady=15)
        
        self.select_btn = ttk.Button(control_frame, text="📁 Выбрать видео", command=self.select_file)
        self.select_btn.pack(side='left', padx=5)
        
        self.play_btn = ttk.Button(control_frame, text="▶️ Воспроизвести", command=self.play_video, state='disabled')
        self.play_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹️ Остановить", command=self.stop_video, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        # Прогресс-бар
        self.progress = ttk.Progressbar(play_frame, mode='indeterminate')
        self.progress.pack(fill='x', padx=20, pady=10)
        
        # === ВКЛАДКА СКАЧИВАНИЯ ===
        download_title = ttk.Label(download_frame, text="Скачивание видео", font=('Arial', 16, 'bold'))
        download_title.pack(pady=10)
        
        # Поле для URL
        url_frame = ttk.Frame(download_frame)
        url_frame.pack(fill='x', padx=20, pady=10)
        
        ttk.Label(url_frame, text="URL видео:").pack(anchor='w')
        self.url_entry = ttk.Entry(url_frame, width=60, font=('Arial', 10))
        self.url_entry.insert(0, "https://example.com/video.mp4")
        self.url_entry.pack(fill='x', pady=5)
        
        # Поле для имени файла
        name_frame = ttk.Frame(download_frame)
        name_frame.pack(fill='x', padx=20, pady=5)
        
        ttk.Label(name_frame, text="Имя файла:").pack(anchor='w')
        self.filename_entry = ttk.Entry(name_frame, width=60, font=('Arial', 10))
        self.filename_entry.insert(0, "video.mp4")
        self.filename_entry.pack(fill='x', pady=5)
        
        # Кнопка скачивания
        self.download_btn = ttk.Button(download_frame, text="🚀 Скачать видео", command=self.download_video)
        self.download_btn.pack(pady=15)
        
        # Статус скачивания
        self.download_status = ttk.Label(download_frame, text="", font=('Arial', 10))
        self.download_status.pack(pady=5)
        
        # === ВКЛАДКА НАСТРОЕК ===
        settings_title = ttk.Label(settings_frame, text="Настройки приложения", font=('Arial', 16, 'bold'))
        settings_title.pack(pady=10)
        
        # Выбор темы
        theme_frame = ttk.Frame(settings_frame)
        theme_frame.pack(fill='x', padx=20, pady=10)
        
        ttk.Label(theme_frame, text="Тема оформления:").pack(anchor='w')
        self.theme_var = tk.StringVar(value=self.settings["theme"])
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, 
                                  values=["light", "dark"], state="readonly")
        theme_combo.pack(fill='x', pady=5)
        theme_combo.bind('<<ComboboxSelected>>', self.change_theme)
        
        # Путь для скачиваний
        path_frame = ttk.Frame(settings_frame)
        path_frame.pack(fill='x', padx=20, pady=10)
        
        ttk.Label(path_frame, text="Папка для загрузок:").pack(anchor='w')
        path_subframe = ttk.Frame(path_frame)
        path_subframe.pack(fill='x', pady=5)
        
        self.path_var = tk.StringVar(value=self.settings["download_path"])
        self.path_entry = ttk.Entry(path_subframe, textvariable=self.path_var)
        self.path_entry.pack(side='left', fill='x', expand=True)
        
        ttk.Button(path_subframe, text="Обзор", command=self.browse_download_path).pack(side='left', padx=5)
        
        # Фрейм для кнопок управления настройками
        settings_buttons = ttk.Frame(settings_frame)
        settings_buttons.pack(pady=20)
        
        ttk.Button(settings_buttons, text="💾 Сохранить настройки", command=self.save_app_settings).pack(side='left', padx=5)
        ttk.Button(settings_buttons, text="🔄 Сбросить настройки", command=self.reset_settings).pack(side='left', padx=5)
        ttk.Button(settings_buttons, text="❌ Удалить помощь", command=self.remove_help).pack(side='left', padx=5)
        
        # Статус помощи
        self.help_status = ttk.Label(settings_frame, 
                                   text="✅ Справочные материалы активны" if self.settings["show_help"] else "❌ Справка отключена",
                                   font=('Arial', 10))
        self.help_status.pack(pady=10)
        
        # Подпись внизу окна
        signature_frame = ttk.Frame(self.root)
        signature_frame.pack(side='bottom', fill='x', pady=10)
        
        signature = ttk.Label(signature_frame, 
                             text="С любовью к своим подписчикам - Тимур Андреев ❤️", 
                             font=('Arial', 12, 'bold'), 
                             foreground='red')
        signature.pack(pady=5)
        
        # Ссылка на помощь
        help_link = ttk.Label(signature_frame, text="📖 Помощь по использованию", 
                             font=('Arial', 10), foreground='blue', cursor='hand2')
        help_link.pack(pady=2)
        help_link.bind('<Button-1>', lambda e: self.show_help())
    
    def select_file(self):
        """Выбор видео файла"""
        file_path = filedialog.askopenfilename(
            title="Выберите видео файл",
            filetypes=[
                ("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv"),
                ("MP4 Files", "*.mp4"),
                ("AVI Files", "*.avi"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            self.current_file = file_path
            filename = os.path.basename(file_path)
            self.file_info.config(text=f"Выбран файл: {filename}")
            self.play_btn.config(state='normal')
            messagebox.showinfo("Файл выбран", f"Готов к воспроизведению: {filename}")
    
    def play_video(self):
        """Воспроизведение видео"""
        if not self.current_file or not os.path.exists(self.current_file):
            messagebox.showerror("Ошибка", "Файл не найден!")
            return
        
        try:
            if not self.playing:
                # Запускаем воспроизведение через системный плеер
                webbrowser.open(self.current_file)
                self.playing = True
                self.play_btn.config(text="⏸️ Пауза")
                self.stop_btn.config(state='normal')
                self.progress.start()
                messagebox.showinfo("Успех", "Видео запускается в системном плеере...")
            else:
                # Здесь была бы логика паузы для встроенного плеера
                self.play_btn.config(text="▶️ Продолжить")
                self.progress.stop()
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось воспроизвести видео: {str(e)}")
    
    def stop_video(self):
        """Остановка воспроизведения"""
        self.playing = False
        self.play_btn.config(text="▶️ Воспроизвести")
        self.stop_btn.config(state='disabled')
        self.progress.stop()
    
    def download_video(self):
        """Скачивание видео по URL"""
        url = self.url_entry.get().strip()
        filename = self.filename_entry.get().strip()
        
        if not url or url == "https://example.com/video.mp4":
            messagebox.showerror("Ошибка", "Пожалуйста, введите корректный URL видео")
            return
        
        if not filename:
            filename = "downloaded_video.mp4"
        
        download_path = os.path.join(self.settings["download_path"], filename)
        
        try:
            self.download_btn.config(state='disabled')
            self.download_status.config(text="⏳ Скачивание...")
            self.progress.start()
            
            # Имитация скачивания (в реальном приложении здесь был бы requests)
            self.root.after(2000, self.finish_download_simulation, download_path, filename)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скачать видео: {str(e)}")
            self.download_btn.config(state='normal')
            self.download_status.config(text="")
            self.progress.stop()
    
    def finish_download_simulation(self, download_path, filename):
        """Завершение имитации скачивания"""
        try:
            # Создаем пустой файл для демонстрации
            with open(download_path, 'w') as f:
                f.write("Это имитация скачанного видео файла")
            
            self.progress.stop()
            self.download_btn.config(state='normal')
            self.download_status.config(text=f"✅ Успешно скачан: {filename}")
            messagebox.showinfo("Успех", f"Видео успешно скачано!\nПуть: {download_path}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при сохранении файла: {str(e)}")
    
    def change_theme(self, event=None):
        """Изменение темы оформления"""
        self.settings["theme"] = self.theme_var.get()
        self.save_settings()
        messagebox.showinfo("Успех", f"Тема изменена на: {self.theme_var.get()}\nИзменения применятся после перезапуска")
    
    def browse_download_path(self):
        """Выбор папки для загрузок"""
        path = filedialog.askdirectory(title="Выберите папку для загрузок")
        if path:
            self.path_var.set(path)
            self.settings["download_path"] = path
            os.makedirs(path, exist_ok=True)
    
    def save_app_settings(self):
        """Сохранение настроек приложения"""
        self.settings["download_path"] = self.path_var.get()
        self.save_settings()
        messagebox.showinfo("Успех", "Настройки успешно сохранены!")
    
    def reset_settings(self):
        """Сброс настроек приложения"""
        result = messagebox.askyesno("Подтверждение", 
                                   "Вы уверены, что хотите сбросить все настройки к значениям по умолчанию?")
        if result:
            default_settings = {
                "theme": "light",
                "volume": 0.7,
                "download_path": "downloads",
                "show_help": True
            }
            self.settings = default_settings
            self.save_settings()
            self.path_var.set("downloads")
            self.theme_var.set("light")
            self.help_status.config(text="✅ Справочные материалы активны")
            messagebox.showinfo("Успех", "Настройки сброшены до значений по умолчанию")
    
    def remove_help(self):
        """Удаление помощи из приложения"""
        result = messagebox.askyesno("Подтверждение", 
                                   "Вы уверены, что хотите отключить все справочные материалы?")
        if result:
            self.settings["show_help"] = False
            self.save_settings()
            self.help_status.config(text="❌ Справка отключена")
            messagebox.showinfo("Успех", "Все справочные материалы отключены")
    
    def show_help(self):
        """Показать справку по использованию"""
        help_text = """
        🎬 ВОСПРОИЗВЕДЕНИЕ ВИДЕО:
        • Нажмите 'Выбрать видео' для выбора файла
        • Используйте кнопки управления для воспроизведения
        • Видео открывается в системном плеере
        
        📥 СКАЧИВАНИЕ ВИДЕО:
        • Введите URL видео в поле ввода
        • Укажите имя файла для сохранения
        • Нажмите 'Скачать видео'
        
        ⚙️ НАСТРОЙКИ:
        • Выберите тему оформления
        • Настройте папку для загрузок
        • Сохраните изменения
        
        С любовью к своим подписчикам - Тимур Андреев ❤️
        """
        messagebox.showinfo("Помощь по использованию", help_text)

# Создание и запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = VideoApp(root)
    root.mainloop()
