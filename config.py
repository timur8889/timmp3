import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # ID вашего канала

# Настройки DeepSeek
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
