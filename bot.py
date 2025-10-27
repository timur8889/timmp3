import logging
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY, DEEPSEEK_API_URL, CHANNEL_ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class DeepSeekBot:
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Добро пожаловать в DeepSeek бот!

Я могу:
• Отвечать на вопросы с помощью AI
• Помогать с генерацией контента
• Анализировать тексты

Просто напишите ваш вопрос!
        """
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 Доступные команды:
/start - начать работу
/help - показать эту справку

Просто напишите ваш вопрос, и я постараюсь на него ответить!
        """
        await update.message.reply_text(help_text)
    
    async def query_deepseek(self, prompt: str) -> str:
        """Запрос к DeepSeek API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты полезный AI ассистент. Отвечай подробно и точно."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.7
        }
        
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
            
        except Exception as e:
            logging.error(f"Ошибка при запросе к DeepSeek: {e}")
            return "Извините, произошла ошибка при обработке запроса."
    
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
        
        # Отправляем ответ пользователю
        await update.message.reply_text(response)
    
    async def post_to_channel(self, message: str):
        """Публикация сообщения в канал"""
        try:
            await self.application.bot.send_message(
                chat_id=CHANNEL_ID,
                text=message
            )
            return True
        except Exception as e:
            logging.error(f"Ошибка при публикации в канал: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logging.info("Бот запущен...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = DeepSeekBot()
    bot.run()
