import os
import time
import base64
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from django.conf import settings

# Variable global para mantener la referencia al navegador abierta
# En producción, esto debería manejarse con Celery o un servicio aparte.
driver_instance = None


def iniciar_navegador():
    global driver_instance

    if driver_instance is not None:
        try:
            # Verificar si sigue vivo
            driver_instance.title
            return driver_instance
        except:
            driver_instance = None

    # Configuración de Chrome
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Descomentar para que no se vea la ventana (luego de escanear)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # PERFIL DE USUARIO: Esto permite que la sesión se guarde y no pida QR cada vez
    user_data_dir = os.path.join(settings.BASE_DIR, 'chrome_user_data')
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get("https://web.whatsapp.com")
    driver_instance = driver
    return driver


def obtener_qr_screenshot():
    """
    Espera a que cargue el canvas del QR y toma una captura.
    """
    driver = iniciar_navegador()

    try:
        # Esperar hasta que aparezca el canvas del QR o la lista de chats (si ya está logueado)
        wait = WebDriverWait(driver, 20)

        # Intentar ver si ya estamos logueados (buscando el panel lateral)
        try:
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            return None, "YA_VINCULADO"
        except:
            pass  # No estamos logueados, seguimos buscando el QR

        # Buscar el canvas del QR
        qr_canvas = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "canvas")))

        # Tomar screenshot del QR en base64 para mostrarlo en el HTML sin guardarlo en disco
        qr_base64 = qr_canvas.screenshot_as_base64
        return qr_base64, "ESPERANDO_ESCANEO"

    except Exception as e:
        print(f"Error buscando QR: {e}")
        return None, "ERROR"