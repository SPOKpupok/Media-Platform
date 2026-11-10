from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import boto3
import pika
import psycopg2
import os
import uuid
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MINIO_URL = os.getenv("MINIO_URL", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://admin:admin@postgres:5432/mediadb")

def get_s3_client():
    return boto3.client(
        's3', endpoint_url=f'http://{MINIO_URL}',
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name='us-east-1'
    )

def get_db_connection():
    return psycopg2.connect(POSTGRES_URL)

def get_rabbitmq_channel():
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue='media_tasks', durable=True)
    return connection, channel

@app.get("/")
def read_root():
    return {"status": "Backend is running"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if "image" in content_type:
        file_type = "image"
    elif "video" in content_type:
        file_type = "video"
    else:
        raise HTTPException(status_code=400, detail="Неподдерживаемый тип файла")

    task_id = str(uuid.uuid4())
    # Берем расширение, если оно есть. Если нет — ставим пустую строку.
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    
    # ВАЖНО: Если расширение есть, добавляем точку, иначе просто ID
    if file_extension:
        source_path = f"source/{task_id}.{file_extension}"
        s3_key = f"{task_id}.{file_extension}"
    else:
        source_path = f"source/{task_id}"
        s3_key = f"{task_id}"

    s3 = get_s3_client()
    try:
        try:
            s3.create_bucket(Bucket="source")
            s3.create_bucket(Bucket="processed")
        except Exception:
            pass
        
        s3.upload_fileobj(file.file, "source", s3_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка MinIO: {str(e)}")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (id, original_filename, file_type, status, source_path) VALUES (%s, %s, %s, %s, %s)",
        (task_id, file.filename, file_type, "uploaded", source_path)
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "task_id": task_id,
        "file_type": file_type,
        "filename": file.filename,
        "status": "uploaded"
    }

@app.get("/api/status/{task_id}")
def get_status(task_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, result_path FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    status, result_path = row
    return {"status": status, "result_path": result_path}

@app.post("/api/process")
async def process_file(request: dict):
    task_id = request.get("task_id")
    action = request.get("action")
    params = request.get("params", {})
    
    if not task_id or not action:
        raise HTTPException(status_code=400, detail="Не хватает параметров")

    # Открываем ОДНО подключение к базе
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Сначала получаем данные о файле
        cur.execute("SELECT source_path, file_type FROM tasks WHERE id=%s", (task_id,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Задача не найдена")
            
        source_path, file_type = row

        # 2. Обновляем статус
        cur.execute("UPDATE tasks SET status='processing', action=%s, params=%s WHERE id=%s", (action, json.dumps(params), task_id))
        conn.commit()
        
    except Exception as e:
        print(f" [!] Ошибка БД: {e}")
        raise HTTPException(status_code=500, detail="Ошибка базы данных")
    finally:
        cur.close()
        conn.close()

    # 3. Отправляем в RabbitMQ
    try:
        connection, channel = get_rabbitmq_channel()
        task_data = {
            "task_id": task_id,
            "action": action,
            "params": params,
            "source_path": source_path,
            "file_type": file_type
        }
        
        channel.basic_publish(
            exchange='',
            routing_key='media_tasks',
            body=json.dumps(task_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        print(f" [x] Задача {task_id} УСПЕШНО отправлена в RabbitMQ")
    except Exception as e:
        print(f" [!] Ошибка отправки в RabbitMQ: {e}")
        raise HTTPException(status_code=500, detail="Ошибка очереди")

    return {"status": "processing", "task_id": task_id}


@app.get("/api/download/{task_id}")
def download_file(task_id: str):
    # 1. Получаем путь к результату из БД
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT result_path FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Результат не найден")

    result_path = row[0]

    # 2. Берем файл из MinIO и отдаем его потоком
    try:
        s3 = get_s3_client()
        file_obj = s3.get_object(Bucket="processed", Key=result_path)
        
        # Вычисляем расширение ДО вызова StreamingResponse
        ext = result_path.split('.')[-1] if '.' in result_path else 'bin'
        
        # Возвращаем поток
        return StreamingResponse(
            file_obj['Body'],
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={task_id}.{ext}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")