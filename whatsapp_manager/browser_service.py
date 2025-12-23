import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)

# Variable global para mantener la sesión viva
driver_instance = None


def iniciar_navegador():
    global driver_instance

    # Verificar si el driver sigue vivo
    if driver_instance is not None:
        try:
            # Hacemos un ping ligero (título o url) para ver si responde
            _ = driver_instance.current_url
            return driver_instance
        except Exception as e:
            print(f"⚠️ El navegador parece desconectado ({e}). Reiniciando...")
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None

    print("Configurando opciones de Chrome (Docker System)...")
    chrome_options = Options()

    # --- RUTAS ---
    # Usamos las variables de entorno del Dockerfile, con fallback a las rutas estándar
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    chrome_options.binary_location = chrome_bin

    # --- LIMPIEZA DE CANDADOS ---
    user_data_dir = "/app/chrome_user_data"
    lock_file = os.path.join(user_data_dir, "SingletonLock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print("🧹 SingletonLock eliminado (limpieza de crash previo).")
        except Exception:
            pass

    # --- FLAGS CRÍTICOS PARA DOCKER ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--window-size=1920,1080")

    # Perfil persistente
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # User Agent (Vital para que WhatsApp no bloquee el Headless)
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')

    # --- DRIVER SERVICE ---
    driver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    service = Service(executable_path=driver_path, log_path="/app/chromedriver.log")

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Evasión de detección básica
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("✅ Navegador iniciado. Cargando WhatsApp...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver

    except Exception as e:
        print(f"❌ ERROR FATAL AL INICIAR CHROME: {e}")
        # Si falla, intentamos leer el log del driver para dar pistas
        try:
            with open("/app/chromedriver.log", "r") as f:
                print("--- Últimas líneas de chromedriver.log ---")
                print(f.read()[-500:])
        except:
            pass
        raise e


def obtener_qr_screenshot():
    """
    Gestiona la obtención del QR o la confirmación de sesión.
    """
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 25)  # Aumentado a 25s por lentitud en Docker

        print("Verificando estado de la sesión...")

        # A. ¿Ya estamos logueados? (Buscamos panel lateral)
        try:
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            print("✅ Sesión activa detectada.")
            return None, "YA_VINCULADO"
        except:
            pass

        # B. ¿Hay QR?
        print("Buscando código QR...")
        try:
            qr_canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
            time.sleep(2)  # Espera a que el JS termine de pintar el QR
            qr_base64 = qr_canvas.screenshot_as_base64
            print("📸 QR capturado.")
            return qr_base64, "ESPERANDO_ESCANEO"
        except:
            print("⚠️ No se encontró QR ni Chat. Posible carga lenta o error de renderizado.")

            # Debug: Tomar screenshot del error para ver qué pasa
            driver.save_screenshot("/app/debug_error_carga.png")
            return None, "CARGANDO"

    except Exception as e:
        print(f"Error en obtener_qr_screenshot: {e}")
        return None, "ERROR"


def enviar_mensaje_browser(nombre_contacto, mensaje):
    driver = iniciar_navegador()
    try:
        # --- CORRECCIÓN IMPORTANTE DEL SELECTOR ---
        # Buscamos por contenteditable y role, o por la clase que usa WhatsApp para el footer
        # Opción A (Más genérica y segura):
        xpath_input = '//div[@contenteditable="true"][@role="textbox"]'

        # Opción B (Si la A falla, a veces el role cambia, usamos la estructura del footer):
        # xpath_input = '//footer//div[@contenteditable="true"]'

        wait = WebDriverWait(driver, 10)
        caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))

        # Foco y limpieza segura
        caja_texto.click()

        # Escribir mensaje
        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)

        time.sleep(0.5)
        caja_texto.send_keys(Keys.ENTER)
        time.sleep(1)  # Esperar a que salga el mensaje
        return True

    except Exception as e:
        print(f"Error enviando mensaje a {nombre_contacto}: {e}")
        return False

# El resto de tu función procesar_nuevos_mensajes se ve bien
# Solo asegúrate de llamar a las funciones corregidas arriba.