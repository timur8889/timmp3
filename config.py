import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN = "8313764660:AAEOFtGphxmLLz7JKSa82a179-vTvjBu1lo"
    HITMOS_API_URL = "https://hitmos.me/api"
    WEBHOOK_URL = "https://your-domain.com"
    WEBAPP_HOST = "0.0.0.0"
    WEBAPP_PORT = int(os.environ.get('PORT', 5000))
