import os
import time
import base64
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from django.conf import settings

# Variable global para mantener la referencia al navegador
driver_instance = None


def iniciar_navegador():
    global driver_instance

    # 1. Verificar si ya existe una instancia activa
    if driver_instance is not None:
        try:
            # Hacemos una llamada ligera para ver si el proceso sigue vivo
            driver_instance.title
            return driver_instance
        except Exception:
            # Si falla, asumimos que se cerró/crasheó y reiniciamos variable
            print("El navegador anterior se cerró inesperadamente. Reiniciando...")
            driver_instance = None

    # 2. Configurar Opciones de Chrome para Docker
    chrome_options = Options()

    # --- BANDERAS CRÍTICAS PARA DOCKER ---
    chrome_options.add_argument("--headless=new")  # Ejecuta sin interfaz gráfica (Nueva sintaxis)
    chrome_options.add_argument("--no-sandbox")  # Necesario para ejecutar como root
    chrome_options.add_argument("--disable-dev-shm-usage")  # Evita errores de memoria compartida
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")  # Ayuda a la estabilidad

    # --- RUTA DEL BINARIO DEL NAVEGADOR ---
    # Esto es vital porque en Docker instalamos 'chromium', no 'google-chrome'
    chrome_options.binary_location = "/usr/bin/chromium"

    # --- PERSISTENCIA DE SESIÓN ---
    # Usamos una ruta absoluta dentro del contenedor
    user_data_dir = os.path.join(settings.BASE_DIR, 'chrome_user_data')
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # 3. Configurar el Servicio (Driver)
    # Usamos la ruta del driver instalado por sistema (apt-get install chromium-driver)
    # Esto evita el error de versión o descarga fallida de webdriver_manager
    service_path = "/usr/bin/chromedriver"

    if not os.path.exists(service_path):
        raise FileNotFoundError(
            f"No se encontró el driver en {service_path}. Asegúrate de haber instalado 'chromium-driver' en tu Dockerfile.")

    service = Service(service_path)

    try:
        print("Iniciando driver de Chrome...")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Cargar WhatsApp Web
        print("Cargando web.whatsapp.com...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver

    except Exception as e:
        print(f"Error fatal al iniciar Selenium: {e}")
        # Intentar cerrar si quedó algo colgado
        try:
            driver.quit()
        except:
            pass
        raise e


def obtener_qr_screenshot():
    """
    Espera a que cargue el canvas del QR y toma una captura.
    Retorna: (base64_string, estado)
    """
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 20)

        print("Verificando estado de sesión...")

        # A. Caso 1: Verificar si ya estamos logueados (buscando la lista de chats)
        try:
            # Buscamos el panel lateral de chats o la foto de perfil
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            print("Sesión ya iniciada detectada.")
            return None, "YA_VINCULADO"
        except:
            # Si salta timeout aquí, significa que NO estamos logueados, seguimos al paso B
            pass

            # B. Caso 2: Buscar el Canvas del código QR
        print("Buscando código QR...")
        try:
            qr_canvas = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "canvas")))

            # Pequeña pausa para asegurar que el QR se renderizó completo
            time.sleep(1)

            # Tomar screenshot del elemento Canvas únicamente
            qr_base64 = qr_canvas.screenshot_as_base64
            print("QR capturado exitosamente.")
            return qr_base64, "ESPERANDO_ESCANEO"

        except Exception as e:
            print("No se encontró ni el chat ni el QR. Posible error de carga o internet.")
            return None, "CARGANDO"

    except Exception as e:
        print(f"Error general en obtener_qr_screenshot: {e}")
        return None, "ERROR"