FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Variables para Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# 1. INSTALACIÓN DE DEPENDENCIAS
# chromium y chromium-driver instalan automáticamente casi todas sus dependencias (libs).
# Agregamos solo las esenciales extras para headless moderno.
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
RUN pip install -r requirements.txt

# 3. Copiar código
COPY . /app/

# Crear carpeta de datos con permisos
RUN mkdir -p /app/chrome_user_data && chmod -R 777 /app/chrome_user_data

EXPOSE 8017

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]