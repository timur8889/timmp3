import logging
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY, DEEPSEEK_API_URL

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class WorkingDeepSeekBot:
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Добро пожаловать в DeepSeek бот!

Я AI-ассистент на основе DeepSeek. Просто напишите ваш вопрос, и я помогу!

Доступные команды:
/start - Запустить бота
/help - Получить помощь

Просто напишите сообщение, и я на него отвечу!
        """
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 Помощь по боту

Просто напишите ваш вопрос на русском или английском языке, и я постараюсь дать развернутый ответ.

Примеры вопросов:
• "Объясни квантовую физику"
• "Напиши код на Python"
• "Помоги с идеей для проекта"

Если бот не отвечает, проверьте подключение к интернету.
        """
        await update.message.reply_text(help_text)
    
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
                    "content": "Ты полезный AI ассистент. Отвечай подробно и точно на русском языке."
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
        
        # Показываем, что бот печатает
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Получаем ответ от DeepSeek
        response = await self.query_deepseek(user_message)
        
        # Разбиваем длинные сообщения (Telegram ограничение 4096 символов)
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)
    
    async def setup_commands(self):
        """Настройка команд меню"""
        commands = [
            ("start", "Запустить бота"),
            ("help", "Получить помощь"),
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
