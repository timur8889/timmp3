import logging
import aiohttp
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY, DEEPSEEK_API_URL

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
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    def create_main_menu(self):
        """Создание визуального меню"""
        keyboard = [
            [KeyboardButton("💡 Попросить идею"), KeyboardButton("📝 Написать код")],
            [KeyboardButton("🔍 Объяснить тему"), KeyboardButton("🎯 Помощь с проектом")],
            [KeyboardButton("📚 Получить справку"), KeyboardButton("🔄 Новый диалог")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Добро пожаловать в DeepSeek бот!

Я AI-ассистент на основе DeepSeek. Просто напишите ваш вопрос, и я помогу!

✨ Используйте кнопки меню ниже для быстрого доступа к функциям!

Доступные команды:
/start - Запустить бота
/help - Получить помощь
/menu - Показать меню
/clear - Очистить историю диалога

Просто напишите сообщение или выберите действие из меню!
        """
        menu = self.create_main_menu()
        await update.message.reply_text(welcome_text, reply_markup=menu)
        
        # Добавляем красивую подпись
        signature = """
        
💝 С любовью к моим подписчикам! 
От Тимура Андреева 🚀
        """
        await update.message.reply_text(signature)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню"""
        menu_text = "🎛️ Главное меню - выберите действие:"
        menu = self.create_main_menu()
        await update.message.reply_text(menu_text, reply_markup=menu)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 Помощь по боту

Просто напишите ваш вопрос на русском или английском языке, и я постараюсь дать развернутый ответ.

✨ Используйте кнопки меню для быстрого доступа:

💡 Попросить идею - генерация творческих идей
📝 Написать код - помощь с программированием
🔍 Объяснить тему - подробные объяснения
🎯 Помощь с проектом - консультации по проектам
📚 Получить справку - справочная информация
🔄 Новый диалог - начать разговор заново

Команды:
/clear - очистить историю диалога
/menu - показать меню

Примеры вопросов:
• "Объясни квантовую физику"
• "Напиши код на Python для сайта"
• "Помоги с идеей для стартапа"
        """
        await update.message.reply_text(help_text)
        
        # Подпись
        signature = """
        
💝 С любовью к моим подписчикам! 
От Тимура Андреева 🚀
        """
        await update.message.reply_text(signature)
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка истории диалога"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        await update.message.reply_text(
            "🔄 История диалога очищена! Начинаем новый разговор!",
            reply_markup=self.create_main_menu()
        )
    
    async def handle_menu_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        """Обработка действий из меню"""
        user_id = update.effective_user.id
        
        if action == "💡 Попросить идею":
            prompt = "Привет! У меня есть творческий блок. Можешь предложить несколько интересных идей для проекта? Можешь предложить идеи в разных областях: технологии, искусство, бизнес, образование и т.д."
        
        elif action == "📝 Написать код":
            prompt = "Привет! Мне нужна помощь с программированием. Можешь показать пример кода и объяснить как он работает? Укажи язык программирования и задачу."
        
        elif action == "🔍 Объяснить тему":
            prompt = "Привет! Пожалуйста, объясни сложную тему простыми словами. Выбери интересную тему из науки, технологий, истории или любой другой области и объясни её так, чтобы было понятно даже новичку."
        
        elif action == "🎯 Помощь с проектом":
            prompt = "Привет! У меня есть проект и мне нужна помощь. Можешь выступить в роли консультанта? Задай уточняющие вопросы о моём проекте и предложи пути решения проблем."
        
        elif action == "📚 Получить справку":
            prompt = "Привет! Предоставь пожалуйста полезную справочную информацию. Это может быть гайд, инструкция, чек-лист или полезные советы на любую тему."
        
        elif action == "🔄 Новый диалог":
            await self.clear_command(update, context)
            return
        
        else:
            await update.message.reply_text("Неизвестное действие. Используйте меню или напишите свой вопрос.")
            return
        
        # Показываем, что бот печатает
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Получаем ответ от DeepSeek
        response = await self.query_deepseek(prompt)
        
        # Добавляем подпись к ответу
        response_with_signature = f"{response}\n\n💝 С любовью к моим подписчикам! \nОт Тимура Андреева 🚀"
        
        # Отправляем ответ
        if len(response_with_signature) > 4000:
            part1 = response[:2000]
            part2 = response[2000:4000] + "\n\n💝 С любовью к моим подписчикам! \nОт Тимура Андреева 🚀"
            await update.message.reply_text(part1)
            await update.message.reply_text(part2)
        else:
            await update.message.reply_text(response_with_signature)
    
    async def query_deepseek(self, prompt: str) -> str:
        """Асинхронный запрос к DeepSeek API"""
        if not DEEPSEEK_API_KEY:
            return "❌ Ошибка: API ключ DeepSeek не настроен. Проверьте файл .env"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": """Ты полезный AI ассистент. Отвечай подробно и точно на русском языке. 
                    Будь креативным и дружелюбным. В конце ответа добавляй мотивационное сообщение."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2048,
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
                    else:
                        error_text = await response.text()
                        logging.error(f"DeepSeek API error: {response.status} - {error_text}")
                        return f"❌ Ошибка API: {response.status}. Проверьте API ключ и попробуйте снова."
                        
        except asyncio.TimeoutError:
            return "⏰ Таймаут запроса. Попробуйте позже."
        except Exception as e:
            logging.error(f"Ошибка при запросе к DeepSeek: {e}")
            return f"❌ Произошла ошибка: {str(e)}"
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        user_message = update.message.text
        
        # Проверяем, является ли сообщение действием из меню
        menu_actions = [
            "💡 Попросить идею", "📝 Написать код", "🔍 Объяснить тему",
            "🎯 Помощь с проектом", "📚 Получить справку", "🔄 Новый диалог"
        ]
        
        if user_message in menu_actions:
            await self.handle_menu_actions(update, context, user_message)
            return
        
        # Обычное текстовое сообщение
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Получаем ответ от DeepSeek
        response = await self.query_deepseek(user_message)
        
        # Добавляем подпись
        response_with_signature = f"{response}\n\n💝 С любовью к моим подписчикам! \nОт Тимура Андреева 🚀"
        
        # Разбиваем длинные сообщения
        if len(response_with_signature) > 4000:
            for i in range(0, len(response_with_signature), 4000):
                await update.message.reply_text(response_with_signature[i:i+4000])
        else:
            await update.message.reply_text(response_with_signature)
    
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
