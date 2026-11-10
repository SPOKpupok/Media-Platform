import pika
import json
import os
import boto3
import subprocess
from PIL import Image, ImageEnhance, ImageFilter
import psycopg2
import io
import time

# --- КОНФИГУРАЦИЯ ---
MINIO_URL = os.getenv("MINIO_URL", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://admin:admin@postgres:5432/mediadb")

s3 = boto3.client(
    's3', endpoint_url=f'http://{MINIO_URL}',
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name='us-east-1'
)

# --- ОБРАБОТКА ---
def process_image(file_data, action, params):
    img = Image.open(io.BytesIO(file_data))
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    output = io.BytesIO()
    
    if action == "shakal":
        target_height = int(params.get("quality", 720))
        ratio = target_height / img.height
        new_width = int(img.width * ratio)
        small_img = img.resize((new_width, target_height), Image.Resampling.LANCZOS)
        img = small_img.resize((img.width, img.height), Image.Resampling.NEAREST)
        img.save(output, format='JPEG', quality=25)

    elif action == "resize":
        width = int(params.get("width", 800))
        height = int(params.get("height", 600))
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        img.save(output, format='JPEG', quality=90)

    elif action == "filter":
        factor = float(params.get("brightness", 1.5))
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(factor)
        img.save(output, format='JPEG', quality=90)
        
    elif action == "sharpness":
        factor = float(params.get("factor", 1.0))
        if factor > 1.0:
            times = int((factor - 1.0) * 5) 
            for _ in range(times):
                img = img.filter(ImageFilter.SHARPEN)
        else:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(factor)
        img.save(output, format='JPEG', quality=90)

    elif action == "contrast":
        factor = float(params.get("factor", 1.0))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(factor)
        img.save(output, format='JPEG', quality=90)

    else:
        img.save(output, format='JPEG', quality=90)
        
    return output.getvalue()

def process_video(file_data, action, params):
    input_path = "/tmp/input.mp4"
    output_path = "/tmp/output.mp4"
    
    with open(input_path, "wb") as f:
        f.write(file_data)
        
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    if action == "change_res":
        height = params.get('height', 720)
        cmd.extend(["-vf", f"scale=-2:{height}"])
        cmd.extend(["-crf", "23"])
        
    elif action == "change_speed":
        speed = float(params.get("speed", 2.0))
        cmd.extend(["-filter:v", f"setpts={1/speed}*PTS", "-filter:a", f"atempo={speed}"])
        
    elif action == "compress":
        cmd.extend(["-crf", "28"])
        cmd.extend(["-preset", "fast"])
        
    elif action == "shakal_video":
        target_height = int(params.get("quality", 140))
        cmd.extend(["-vf", f"scale=-2:{target_height}:flags=neighbor"])
        cmd.extend(["-crf", "35"]) 
        cmd.extend(["-preset", "ultrafast"])
        
    cmd.append(output_path)
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        with open(output_path, "rb") as f:
            result_data = f.read()
    finally:
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
    return result_data

# --- ЗАПУСК ---
def main():
    print(" [*] Попытка подключения к RabbitMQ...")
    for i in range(10):
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue='media_tasks', durable=True)
            print(" [*] Подключение успешно!")
            break
        except Exception as e:
            print(f" [x] Ожидание {i+1}/10: {e}")
            time.sleep(3)
    else:
        print(" [!] Выход.")
        return

    def callback(ch, method, properties, body):
        task = json.loads(body)
        print(f" [x] Задача: {task['task_id']}")
        try:
            file_id = task["source_path"].replace("source/", "").split('.')[0]
            print(f" [i] Ищем файл с ID: {file_id}")
            
            response = s3.list_objects_v2(Bucket="source")
            real_key = None
            if 'Contents' in response:
                for obj in response['Contents']:
                    if file_id in obj['Key']:
                        real_key = obj['Key']
                        break
            
            if not real_key:
                raise Exception(f"Файл с ID {file_id} не найден")

            print(f" [i] Найден файл: {real_key}")
            file_data = s3.get_object(Bucket="source", Key=real_key)['Body'].read()

            if task["file_type"] == "image":
                result_data = process_image(file_data, task["action"], task["params"])
                ext = ".jpg"
            else:
                result_data = process_video(file_data, task["action"], task["params"])
                ext = ".mp4"
                
            result_key = f"processed/{task['task_id']}_result{ext}"
            s3.put_object(Bucket="processed", Key=result_key, Body=result_data)
            
            conn = psycopg2.connect(POSTGRES_URL)
            cur = conn.cursor()
            cur.execute("UPDATE tasks SET status='completed', result_path=%s WHERE id=%s", (result_key, task['task_id']))
            conn.commit()
            cur.close()
            conn.close()
            
            print(f" [x] Выполнено. Файл: {result_key}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f" [!] Ошибка: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='media_tasks', on_message_callback=callback)
    print(' [*] Ожидание задач...')
    channel.start_consuming()

if __name__ == '__main__':
    main()