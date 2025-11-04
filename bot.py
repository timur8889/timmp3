import telebot
from telebot import types
import sqlite3
import datetime
import os

# Токен бота (получите у @BotFather)
BOT_TOKEN = "8313764660:AAEOFtGphxmLLz7JKSa82a179-vTvjBu1lo"

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Создание базы данных
def init_db():
    conn = sqlite3.connect('construction_stats.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица объектов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            start_date TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    # Таблица материалов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER,
            material_name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            price_per_unit REAL,
            total_cost REAL,
            date TEXT,
            FOREIGN KEY (object_id) REFERENCES objects (id)
        )
    ''')
    
    # Таблица зарплат
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER,
            worker_name TEXT NOT NULL,
            position TEXT,
            hours_worked REAL,
            hourly_rate REAL,
            total_salary REAL,
            date TEXT,
            FOREIGN KEY (object_id) REFERENCES objects (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Инициализация БД при запуске
init_db()

# Главное меню
def main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('🏗️ Объекты')
    btn2 = types.KeyboardButton('📦 Материалы')
    btn3 = types.KeyboardButton('💵 Зарплаты')
    btn4 = types.KeyboardButton('📊 Статистика')
    markup.add(btn1, btn2, btn3, btn4)
    bot.send_message(chat_id, "Выберите раздел:", reply_markup=markup)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_command(message):
    welcome_text = """
🏗️ Добро пожаловать в бот для учета строительной статистики!

Возможности:
• Учет объектов строительства
• Ведение расходов на материалы
• Учет зарплат сотрудников
• Полная статистика по проектам

Выберите раздел в меню ниже 👇
    """
    bot.send_message(message.chat.id, welcome_text)
    main_menu(message.chat.id)

# Обработчик текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text
    
    if text == '🏗️ Объекты':
        objects_menu(chat_id)
    elif text == '📦 Материалы':
        materials_menu(chat_id)
    elif text == '💵 Зарплаты':
        salaries_menu(chat_id)
    elif text == '📊 Статистика':
        show_statistics(chat_id)
    elif text == '⬅️ Назад':
        main_menu(chat_id)

# Меню объектов
def objects_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('➕ Добавить объект')
    btn2 = types.KeyboardButton('📋 Список объектов')
    btn3 = types.KeyboardButton('❌ Удалить объект')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "Управление объектами:", reply_markup=markup)

# Меню материалов
def materials_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('📥 Добавить материал')
    btn2 = types.KeyboardButton('📋 Расходы на материалы')
    btn3 = types.KeyboardButton('📊 Статистика материалов')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "Управление материалами:", reply_markup=markup)

# Меню зарплат
def salaries_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('👤 Добавить зарплату')
    btn2 = types.KeyboardButton('📋 Выплаты зарплат')
    btn3 = types.KeyboardButton('📊 Статистика зарплат')
    btn4 = types.KeyboardButton('⬅️ Назад')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(chat_id, "Управление зарплатами:", reply_markup=markup)

# Обработчики для объектов
@bot.message_handler(func=lambda message: message.text == '➕ Добавить объект')
def add_object_start(message):
    msg = bot.send_message(message.chat.id, "Введите название объекта:")
    bot.register_next_step_handler(msg, add_object_name)

def add_object_name(message):
    object_name = message.text
    msg = bot.send_message(message.chat.id, "Введите адрес объекта:")
    bot.register_next_step_handler(msg, add_object_address, object_name)

def add_object_address(message, object_name):
    address = message.text
    start_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO objects (name, address, start_date) VALUES (?, ?, ?)', 
                   (object_name, address, start_date))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Объект '{object_name}' успешно добавлен!")
    objects_menu(message.chat.id)

@bot.message_handler(func=lambda message: message.text == '📋 Список объектов')
def list_objects(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, address, start_date FROM objects WHERE status = "active"')
    objects = cursor.fetchall()
    conn.close()
    
    if not objects:
        bot.send_message(message.chat.id, "📭 Нет активных объектов")
        return
    
    response = "🏗️ Список объектов:\n\n"
    for obj in objects:
        response += f"ID: {obj[0]}\n"
        response += f"Название: {obj[1]}\n"
        response += f"Адрес: {obj[2]}\n"
        response += f"Дата начала: {obj[3]}\n"
        response += "─" * 20 + "\n"
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '❌ Удалить объект')
def delete_object_start(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM objects WHERE status = "active"')
    objects = cursor.fetchall()
    conn.close()
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов для удаления")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"DEL_OBJ_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    msg = bot.send_message(message.chat.id, "Выберите объект для удаления:", reply_markup=markup)
    bot.register_next_step_handler(msg, delete_object_confirm)

def delete_object_confirm(message):
    if message.text == '⬅️ Назад':
        objects_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[2])
        object_name = '_'.join(message.text.split('_')[3:])
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(types.KeyboardButton('✅ Да'), types.KeyboardButton('❌ Нет'))
        
        msg = bot.send_message(message.chat.id, 
                              f"Вы уверены, что хотите удалить объект '{object_name}'?",
                              reply_markup=markup)
        bot.register_next_step_handler(msg, delete_object_final, object_id, object_name)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def delete_object_final(message, object_id, object_name):
    if message.text == '✅ Да':
        conn = sqlite3.connect('construction_stats.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE objects SET status = "inactive" WHERE id = ?', (object_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Объект '{object_name}' удален!")
    else:
        bot.send_message(message.chat.id, "❌ Удаление отменено")
    
    objects_menu(message.chat.id)

# Обработчики для материалов
@bot.message_handler(func=lambda message: message.text == '📥 Добавить материал')
def add_material_start(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM objects WHERE status = "active"')
    objects = cursor.fetchall()
    conn.close()
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"OBJ_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    msg = bot.send_message(message.chat.id, "Выберите объект:", reply_markup=markup)
    bot.register_next_step_handler(msg, add_material_object)

def add_material_object(message):
    if message.text == '⬅️ Назад':
        materials_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[1])
        object_name = '_'.join(message.text.split('_')[2:])
        
        msg = bot.send_message(message.chat.id, "Введите название материала:")
        bot.register_next_step_handler(msg, add_material_name, object_id)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def add_material_name(message, object_id):
    material_name = message.text
    msg = bot.send_message(message.chat.id, "Введите количество:")
    bot.register_next_step_handler(msg, add_material_quantity, object_id, material_name)

def add_material_quantity(message, object_id, material_name):
    try:
        quantity = float(message.text)
        msg = bot.send_message(message.chat.id, "Введите единицу измерения (шт, кг, м и т.д.):")
        bot.register_next_step_handler(msg, add_material_unit, object_id, material_name, quantity)
    except:
        bot.send_message(message.chat.id, "❌ Введите корректное число")

def add_material_unit(message, object_id, material_name, quantity):
    unit = message.text
    msg = bot.send_message(message.chat.id, "Введите цену за единицу:")
    bot.register_next_step_handler(msg, add_material_price, object_id, material_name, quantity, unit)

def add_material_price(message, object_id, material_name, quantity, unit):
    try:
        price_per_unit = float(message.text)
        total_cost = quantity * price_per_unit
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect('construction_stats.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO materials (object_id, material_name, quantity, unit, price_per_unit, total_cost, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (object_id, material_name, quantity, unit, price_per_unit, total_cost, date))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Материал '{material_name}' добавлен!\n"
                         f"Сумма: {total_cost:.2f} руб.")
        materials_menu(message.chat.id)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка при добавлении материала")

@bot.message_handler(func=lambda message: message.text == '📋 Расходы на материалы')
def show_materials_expenses(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.name, m.material_name, m.quantity, m.unit, m.total_cost, m.date
        FROM materials m
        JOIN objects o ON m.object_id = o.id
        ORDER BY m.date DESC
        LIMIT 20
    ''')
    
    materials = cursor.fetchall()
    conn.close()
    
    if not materials:
        bot.send_message(message.chat.id, "📭 Нет данных о материалах")
        return
    
    response = "📦 ПОСЛЕДНИЕ РАСХОДЫ НА МАТЕРИАЛЫ:\n\n"
    total = 0
    for mat in materials:
        response += f"🏗️ {mat[0]}\n"
        response += f"📝 {mat[1]}: {mat[2]} {mat[3]}\n"
        response += f"💰 {mat[4]:.2f} руб.\n"
        response += f"📅 {mat[5]}\n"
        response += "─" * 20 + "\n"
        total += mat[4]
    
    response += f"\n💰 ОБЩАЯ СУММА: {total:.2f} руб."
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика материалов')
def show_materials_statistics(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT material_name, SUM(quantity), unit, SUM(total_cost)
        FROM materials 
        GROUP BY material_name, unit
        ORDER BY SUM(total_cost) DESC
    ''')
    
    stats = cursor.fetchall()
    conn.close()
    
    if not stats:
        bot.send_message(message.chat.id, "📭 Нет данных о материалах")
        return
    
    response = "📊 СТАТИСТИКА МАТЕРИАЛОВ:\n\n"
    total_cost = 0
    
    for stat in stats:
        response += f"📝 {stat[0]}\n"
        response += f"   Количество: {stat[1]} {stat[2]}\n"
        response += f"   Сумма: {stat[3]:.2f} руб.\n"
        response += "─" * 20 + "\n"
        total_cost += stat[3]
    
    response += f"\n💰 ОБЩАЯ СУММА: {total_cost:.2f} руб."
    
    bot.send_message(message.chat.id, response)

# Обработчики для зарплат
@bot.message_handler(func=lambda message: message.text == '👤 Добавить зарплату')
def add_salary_start(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM objects WHERE status = "active"')
    objects = cursor.fetchall()
    conn.close()
    
    if not objects:
        bot.send_message(message.chat.id, "❌ Нет активных объектов. Сначала создайте объект.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for obj in objects:
        markup.add(types.KeyboardButton(f"SAL_OBJ_{obj[0]}_{obj[1]}"))
    markup.add(types.KeyboardButton('⬅️ Назад'))
    
    msg = bot.send_message(message.chat.id, "Выберите объект:", reply_markup=markup)
    bot.register_next_step_handler(msg, add_salary_object)

def add_salary_object(message):
    if message.text == '⬅️ Назад':
        salaries_menu(message.chat.id)
        return
    
    try:
        object_id = int(message.text.split('_')[2])
        msg = bot.send_message(message.chat.id, "Введите ФИО работника:")
        bot.register_next_step_handler(msg, add_salary_worker, object_id)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка выбора объекта")

def add_salary_worker(message, object_id):
    worker_name = message.text
    msg = bot.send_message(message.chat.id, "Введите должность:")
    bot.register_next_step_handler(msg, add_salary_position, object_id, worker_name)

def add_salary_position(message, object_id, worker_name):
    position = message.text
    msg = bot.send_message(message.chat.id, "Введите количество отработанных часов:")
    bot.register_next_step_handler(msg, add_salary_hours, object_id, worker_name, position)

def add_salary_hours(message, object_id, worker_name, position):
    try:
        hours_worked = float(message.text)
        msg = bot.send_message(message.chat.id, "Введите ставку за час (руб.):")
        bot.register_next_step_handler(msg, add_salary_rate, object_id, worker_name, position, hours_worked)
    except:
        bot.send_message(message.chat.id, "❌ Введите корректное число часов")

def add_salary_rate(message, object_id, worker_name, position, hours_worked):
    try:
        hourly_rate = float(message.text)
        total_salary = hours_worked * hourly_rate
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect('construction_stats.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO salaries (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (object_id, worker_name, position, hours_worked, hourly_rate, total_salary, date))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Зарплата для {worker_name} добавлена!\n"
                         f"Сумма: {total_salary:.2f} руб.")
        salaries_menu(message.chat.id)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка при добавлении зарплаты")

@bot.message_handler(func=lambda message: message.text == '📋 Выплаты зарплат')
def show_salaries_expenses(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.name, s.worker_name, s.position, s.hours_worked, s.total_salary, s.date
        FROM salaries s
        JOIN objects o ON s.object_id = o.id
        ORDER BY s.date DESC
        LIMIT 20
    ''')
    
    salaries = cursor.fetchall()
    conn.close()
    
    if not salaries:
        bot.send_message(message.chat.id, "📭 Нет данных о зарплатах")
        return
    
    response = "💵 ПОСЛЕДНИЕ ВЫПЛАТЫ ЗАРПЛАТ:\n\n"
    total = 0
    for sal in salaries:
        response += f"🏗️ {sal[0]}\n"
        response += f"👤 {sal[1]} ({sal[2]})\n"
        response += f"⏱️ {sal[3]} часов\n"
        response += f"💰 {sal[4]:.2f} руб.\n"
        response += f"📅 {sal[5]}\n"
        response += "─" * 20 + "\n"
        total += sal[4]
    
    response += f"\n💰 ОБЩАЯ СУММА: {total:.2f} руб."
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика зарплат')
def show_salaries_statistics(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT worker_name, position, SUM(hours_worked), SUM(total_salary)
        FROM salaries 
        GROUP BY worker_name, position
        ORDER BY SUM(total_salary) DESC
    ''')
    
    stats = cursor.fetchall()
    conn.close()
    
    if not stats:
        bot.send_message(message.chat.id, "📭 Нет данных о зарплатах")
        return
    
    response = "📊 СТАТИСТИКА ЗАРПЛАТ:\n\n"
    total_hours = 0
    total_salary = 0
    
    for stat in stats:
        response += f"👤 {stat[0]} ({stat[1]})\n"
        response += f"   Часы: {stat[2]}\n"
        response += f"   Зарплата: {stat[3]:.2f} руб.\n"
        response += "─" * 20 + "\n"
        total_hours += stat[2]
        total_salary += stat[3]
    
    response += f"\n📈 ИТОГО:\n"
    response += f"   Общее время: {total_hours} часов\n"
    response += f"   Общая сумма: {total_salary:.2f} руб."
    
    bot.send_message(message.chat.id, response)

# Показать статистику
@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_statistics(message):
    conn = sqlite3.connect('construction_stats.db')
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute('SELECT COUNT(*) FROM objects WHERE status = "active"')
    objects_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(total_cost) FROM materials')
    total_materials = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(total_salary) FROM salaries')
    total_salaries = cursor.fetchone()[0] or 0
    
    total_expenses = total_materials + total_salaries
    
    response = "📊 ОБЩАЯ СТАТИСТИКА\n\n"
    response += f"🏗️ Активных объектов: {objects_count}\n"
    response += f"📦 Общие расходы на материалы: {total_materials:.2f} руб.\n"
    response += f"💵 Общие расходы на зарплаты: {total_salaries:.2f} руб.\n"
    response += f"💰 Общие расходы: {total_expenses:.2f} руб.\n\n"
    
    # Статистика по объектам
    cursor.execute('''
        SELECT o.name, 
               COALESCE(SUM(m.total_cost), 0) as materials_cost,
               COALESCE(SUM(s.total_salary), 0) as salaries_cost
        FROM objects o
        LEFT JOIN materials m ON o.id = m.object_id
        LEFT JOIN salaries s ON o.id = s.object_id
        WHERE o.status = 'active'
        GROUP BY o.id, o.name
    ''')
    
    objects_stats = cursor.fetchall()
    
    if objects_stats:
        response += "📈 СТАТИСТИКА ПО ОБЪЕКТАМ:\n"
        for obj in objects_stats:
            response += f"\n🏗️ {obj[0]}:\n"
            response += f"   Материалы: {obj[1]:.2f} руб.\n"
            response += f"   Зарплаты: {obj[2]:.2f} руб.\n"
            response += f"   Всего: {obj[1] + obj[2]:.2f} руб.\n"
    
    conn.close()
    
    bot.send_message(message.chat.id, response)

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)
