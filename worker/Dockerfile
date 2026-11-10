# Берем Python
FROM python:3.11-slim

# Устанавливаем FFmpeg (нужен для обработки видео)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости и ставим их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Запускаем воркер
CMD ["python", "worker.py"]
