FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema para Postgres
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    chromium \
    chromium-driver \
    libnss3 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

# Instalar librerías de Python
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código fuente
COPY . /app/

EXPOSE 8017

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]