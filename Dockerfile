FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Variables de entorno para Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# 1. INSTALACIÓN DE DEPENDENCIAS (Añadidas libgbm1, libvulkan1, etc.)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgconf-2-4 \
    libxi6 \
    libxcursor1 \
    libxss1 \
    libxrandr2 \
    libasound2 \
    libatk1.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libu2f-udev \
    libvulkan1 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    wget \
    curl \
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Instalar dependencias de Python
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 3. Copiar el código
COPY . /app/

# Crear carpeta de datos y dar permisos amplios (evita errores de escritura)
RUN mkdir -p /app/chrome_user_data && chmod -R 777 /app/chrome_user_data

EXPOSE 8017

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]