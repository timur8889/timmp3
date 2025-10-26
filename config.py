import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    HITMOS_API_URL = "https://hitmos.me/api"
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-domain.com')
    WEBAPP_HOST = os.getenv('WEBAPP_HOST', '0.0.0.0')
    WEBAPP_PORT = int(os.environ.get('PORT', 5000))
