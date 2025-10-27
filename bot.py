import logging
import aiohttp
import asyncio
import json
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY, DEEPSEEK_API_URL, OPENROUTER_API_URL

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class WorkingDeepSeekBot:
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
        self.user_sessions = {}
        self.current_api = "deepseek"  # deepseek или openrouter
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    def create_main_menu(self):
        """Создание визуального меню"""
        keyboard = [
            [KeyboardButton("💡 Попросить идею"), KeyboardButton("📝 Написать код")],
            [KeyboardButton("🔍 Объяснить тему"), KeyboardButton("🎯 Помощь с проектом")],
            [KeyboardButton("📚 Получить справку"), KeyboardButton("🔄 Новый диалог")],
            [KeyboardButton("📊 Статус бота")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Добро пожаловать в DeepSeek бот!

Я AI-ассистент, созданный с заботой о вас! Просто напишите вопрос или используйте меню.

✨ Используйте кнопки меню ниже для быстрого доступа к функциям!

Доступные команды:
/start - Запустить бота
/help - Получить помощь
/menu - Показать меню
/clear - Очистить историю
/status - Статус бота

Просто напишите сообщение или выберите действие из меню!
        """
        menu = self.create_main_menu()
        await update.message.reply_text(welcome_text, reply_markup=menu)
        
        # Добавляем красивую подпись
        signature = """
        
💝 *С любовью к моим подписчикам!* 
От *Тимура Андреева* 🚀

*P.S.* Если я не отвечаю, используйте команду /status для проверки
        """
        await update.message.reply_text(signature, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка статуса API"""
        status_text = "🔍 Проверяю статус API..."
        await update.message.reply_text(status_text)
        
        # Тестовый запрос
        test_response = await self.query_deepseek("Привет! Ответь коротко 'Бот работает'")
        
        if "Бот работает" in test_response:
            status = "✅ Бот работает отлично! API доступно."
        else:
            status = "⚠️ Есть проблемы с API. Используется резервный режим."
        
        status_message = f"""
📊 *Статус бота:*

{status}

*Текущий API:* {self.current_api}
*Решение проблем:*
1. Проверьте баланс API аккаунта
2. Проверьте корректность API ключа
3. Попробуйте позже

💝 *С любовью к моим подписчикам!*
От *Тимура Андреева* 🚀
        """
        await update.message.reply_text(status_message, parse_mode='Markdown')
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню"""
        menu_text = "🎛️ *Главное меню* - выберите действие:"
        menu = self.create_main_menu()
        await update.message.reply_text(menu_text, reply_markup=menu, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 *Помощь по боту*

Просто напишите ваш вопрос, и я постараюсь дать развернутый ответ!

✨ *Быстрые действия через меню:*

💡 *Попросить идею* - творческие идеи и вдохновение
📝 *Написать код* - помощь в программировании
🔍 *Объяснить тему* - простые объяснения сложных тем
🎯 *Помощь с проектом* - консультации и планирование
📚 *Получить справку* - полезные инструкции и гайды
🔄 *Новый диалог* - начать разговор заново
📊 *Статус бота* - проверить работу API

*Если возникают ошибки:*
• Используйте /status для проверки
• Проверьте интернет-соединение
• Попробуйте позже
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
        
        # Подпись
        signature = """
        
💝 *С любовью к моим подписчикам!* 
От *Тимура Андреева* 🚀
        """
        await update.message.reply_text(signature, parse_mode='Markdown')
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка истории диалога"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        await update.message.reply_text(
            "🔄 *История диалога очищена!* Начинаем новый разговор!",
            reply_markup=self.create_main_menu(),
            parse_mode='Markdown'
        )
    
    async def handle_menu_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Обработка действий из меню"""
        user_id = update.effective_user.id
        
        if action == "💡 Попросить идею":
            prompt = "Привет! У меня творческий блок. Предложи 3-5 интересных идей для проектов в разных областях (технологии, искусство, бизнес, образование). Будь креативным!"
        
        elif action == "📝 Написать код":
            prompt = "Привет! Мне нужна помощь с программированием. Предложи пример полезного кода на Python с комментариями. Объясни как он работает."
        
        elif action == "🔍 Объяснить тему":
            prompt = "Привет! Выбери интересную тему из науки или технологий и объясни её простыми словами, чтобы было понятно новичку. Добавь примеры из жизни."
        
        elif action == "🎯 Помощь с проектом":
            prompt = "Привет! Я начинаю новый проект. Задай мне 5 ключевых вопросов о проекте, а затем дай практические советы по его реализации."
        
        elif action == "📚 Получить справку":
            prompt = "Привет! Создай полезный гайд или чек-лист на актуальную тему. Сделай его структурированным и практичным."
        
        elif action == "🔄 Новый диалог":
            await self.clear_command(update, context)
            return
        
        elif action == "📊 Статус бота":
            await self.status_command(update, context)
            return
        
        else:
            await update.message.reply_text("Неизвестное действие. Используйте меню или напишите свой вопрос.")
            return
        
        # Показываем, что бот печатает
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Получаем ответ
        response = await self.query_deepseek(prompt)
        await self.send_response(update, response)
    
    async def query_deepseek(self, prompt: str) -> str:
        """Умный запрос к API с обработкой ошибок"""
        if not DEEPSEEK_API_KEY:
            return "❌ API ключ не настроен. Добавьте DEEPSEEK_API_KEY в файл .env"
        
        # Пробуем DeepSeek API
        deepseek_response = await self.try_deepseek_api(prompt)
        if deepseek_response and not any(error in deepseek_response for error in ["❌", "⏰", "402"]):
            self.current_api = "deepseek"
            return deepseek_response
        
        # Если DeepSeek не работает, пробуем альтернативы
        self.current_api = "local_fallback"
        return await self.get_fallback_response(prompt)
    
    async def try_deepseek_api(self, prompt: str) -> str:
        """Попытка запроса к DeepSeek API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": """Ты полезный AI ассистент. Отвечай на русском языке. 
                    Будь креативным, дружелюбным и подробным. Добавляй практические советы."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.7,
            "stream": False
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DEEPSEEK_API_URL, 
                    headers=headers, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content']
                    elif response.status == 402:
                        return "❌ Ошибка 402: Проблема с оплатой API. Проверьте баланс аккаунта DeepSeek."
                    else:
                        error_text = await response.text()
                        logger.error(f"DeepSeek API error: {response.status}")
                        return f"❌ Ошибка API: {response.status}"
                        
        except asyncio.TimeoutError:
            return "⏰ Таймаут запроса. Попробуйте позже."
        except Exception as e:
            logger.error(f"Ошибка при запросе к DeepSeek: {e}")
            return f"❌ Ошибка соединения: {str(e)}"
    
    async def get_fallback_response(self, prompt: str) -> str:
        """Резервные ответы когда API недоступно"""
        fallback_responses = {
            "иде": "💡 *Креативные идеи от Тимура:*\n\n1. Создайте бота для помощи в обучении\n2. Разработайте приложение для учета привычек\n3. Организуйте онлайн-сообщество по интересам\n\n🚀 *Не бойтесь экспериментировать!*",
            "код": "📝 *Пример кода на Python:*\n\n```python\n# Простой телеграм бот\nimport logging\nfrom telegram import Update\nfrom telegram.ext import Application, CommandHandler\n\nasync def start(update: Update, context):\n    await update.message.reply_text('Привет! Я бот!')\n\n# Создайте своего бота и меняйте мир! 🌟```",
            "объясн": "🔍 *Объяснение ИИ простыми словами:*\n\nИИ - это как умный помощник, который учится на примерах. Представьте, что вы учите ребенка: показываете много картинок кошек, и он начинает узнавать кошек everywhere!\n\n🎯 *Всё гениальное - просто!*",
            "проект": "🎯 *План проекта:*\n\n1. Определите цель\n2. Составьте план\n3. Соберите команду\n4. Действуйте по шагам\n5. Анализируйте результаты\n\n💪 *Вы сможете! Верьте в себя!*",
            "справк": "📚 *Полезные советы:*\n\n• Разбивайте большие задачи на маленькие\n• Учитесь каждый день по чуть-чуть\n• Не бойтесь ошибок - они учат\n• Ищите единомышленников\n\n🌟 *Развивайтесь с удовольствием!*"
        }
        
        prompt_lower = prompt.lower()
        for key, response in fallback_responses.items():
            if key in prompt_lower:
                return response
        
        return """🤖 *Я здесь, чтобы помочь!* 

В настоящее время основные AI-сервисы временно недоступны, но это не остановит нас!

💝 *С любовью к моим подписчикам,*
*Тимур Андреев* 🚀

*P.S.* Используйте команду /status для проверки работы API"""
    
    async def send_response(self, update: Update, response: str):
        """Отправка ответа с подписью"""
        signature = "\n\n💝 *С любовью к моим подписчикам!* \nОт *Тимура Андреева* 🚀"
        
        full_response = response + signature
        
        # Разбиваем длинные сообщения
        if len(full_response) > 4000:
            parts = []
            while len(full_response) > 4000:
                part = full_response[:4000]
                # Находим последний перенос строки
                last_newline = part.rfind('\n')
                if last_newline > 3500:  # Если есть разумное место для разрыва
                    parts.append(part[:last_newline])
                    full_response = full_response[last_newline+1:]
                else:
                    parts.append(part)
                    full_response = full_response[4000:]
            parts.append(full_response)
            
            for part in parts:
                await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(full_response, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        user_message = update.message.text
        
        # Проверяем, является ли сообщение действием из меню
        menu_actions = [
            "💡 Попросить идею", "📝 Написать код", "🔍 Объяснить тему",
            "🎯 Помощь с проектом", "📚 Получить справку", "🔄 Новый диалог", "📊 Статус бота"
        ]
        
        if user_message in menu_actions:
            await self.handle_menu_actions(update, context, user_message)
            return
        
        # Обычное текстовое сообщение
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Получаем ответ
        response = await self.query_deepseek(user_message)
        await self.send_response(update, response)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка: {context.error}")
        
        if update and update.effective_chat:
            error_message = "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз."
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message
            )
    
    async def setup_commands(self):
        """Настройка команд меню"""
        commands = [
            ("start", "Запустить бота"),
            ("help", "Получить помощь"),
            ("menu", "Показать меню"),
            ("clear", "Очистить историю"),
            ("status", "Статус бота"),
        ]
        await self.application.bot.set_my_commands(commands)
    
    async def post_init(self, application):
        """Инициализация после запуска"""
        await self.setup_commands()
        logging.info("Бот инициализирован и готов к работе")
    
    def run(self):
        """Запуск бота"""
        self.application.post_init = self.post_init
        logging.info("Бот запущен...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = WorkingDeepSeekBot()
    bot.run()
    
