# 1. Usamos una imagen ligera de Python oficial
FROM python:3.11-slim

# 2. Evitamos que Python escriba archivos .pyc y bufee la salida de logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Creamos y nos movemos a la carpeta de trabajo dentro del contenedor
WORKDIR /app

# 4. Copiamos el archivo de dependencias primero (para aprovechar la caché de Docker)
COPY requirements.txt .

# 5. Instalamos las librerías chido
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiamos todo el contenido de nuestra carpeta local al contenedor
COPY . .

# 7. Exponemos el puerto por defecto (Cloud Run usa el 8080)
EXPOSE 8080

# 8. Comando para arrancar la app. Como tus scripts viven en src/, ejecutamos desde ahí
CMD ["python", "src/bot_telegram.py"]