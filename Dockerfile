# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем директорию приложения
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем директории для данных
RUN mkdir -p /app/data /app/logs

# Создаем непривилегированного пользователя
RUN groupadd -r bot && useradd -r -g bot bot
RUN chown -R bot:bot /app
USER bot

# Отмечаем порт (если нужно)
EXPOSE 8080

# Команда запуска
CMD ["python", "bot.py"]
