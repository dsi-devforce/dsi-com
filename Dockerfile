FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Variables para Selenium y Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# 1. INSTALACIÓN DE DEPENDENCIAS DEL SISTEMA
# Se agregan dependencias para compilación de Python (gcc, etc) si fueran necesarias
# y todas las libs gráficas para que Chrome funcione en modo headless.
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    xdg-utils \
    wget \
    curl \
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Instalar dependencias Python
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiar código del proyecto
COPY . /app/

# 4. Crear carpetas necesarias y asignar permisos
# chrome_user_data: Para perfiles de Selenium
# media: Para archivos recibidos
# static: Para archivos estáticos recolectados
RUN mkdir -p /app/chrome_user_data /app/media /app/static \
    && chmod -R 777 /app/chrome_user_data \
    && chmod -R 777 /app/media

EXPOSE 8017

# 5. COMANDO DE ARRANQUE "TODO EN UNO"
# Ejecuta migraciones -> Recolecta estáticos (opcional pero recomendado) -> Inicia Servidor
# Usamos 'sh -c' para encadenar comandos en tiempo de ejecución
CMD sh -c "python manage.py migrate && \
           python manage.py runserver 0.0.0.0:8000"