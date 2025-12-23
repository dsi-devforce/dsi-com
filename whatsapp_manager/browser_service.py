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

    if driver_instance is not None:
        try:
            driver_instance.title
            return driver_instance
        except:
            driver_instance = None

    chrome_options = Options()

    # --- CONFIGURACIÓN PARA EVITAR DETECCIÓN ---
    # 1. User Agent: Hacemos creer que es un Chrome normal en Windows
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')

    # 2. Tamaño de ventana: Si es muy pequeño, WhatsApp pide "ampliar ventana" y no muestra QR
    chrome_options.add_argument("--window-size=1920,1080")

    # 3. Idioma (opcional pero recomendado)
    chrome_options.add_argument("--lang=es-419")

    # --- RESTO DE TU CONFIGURACIÓN DOCKER ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")

    chrome_options.binary_location = "/usr/bin/chromium"
    user_data_dir = os.path.join(settings.BASE_DIR, 'chrome_user_data')
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    service_path = "/usr/bin/chromedriver"
    service = Service(service_path)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # TRUCO ADICIONAL: Evitar detección de webdriver mediante Script
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        driver.get("https://web.whatsapp.com")
        driver_instance = driver
        return driver
    except Exception as e:
        print(f"Error fatal: {e}")
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