import shutil
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

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Variable global para mantener la sesión viva (Singleton)
driver_instance = None


def iniciar_navegador():
    """
    Inicia Chromium con persistencia de datos y auto-reparación de perfil.
    """
    global driver_instance

    # 1. Reutilización de driver existente
    if driver_instance is not None:
        try:
            _ = driver_instance.current_url
            return driver_instance
        except:
            print("⚠️ Navegador desconectado. Reiniciando...")
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None

    print("🔧 Configurando Chrome (Docker)...")

    chrome_bin = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"

    # Gestión de Perfil
    root_mount = "/app/chrome_user_data"
    profile_dir = os.path.join(root_mount, "session")

    def get_options():
        opts = Options()
        opts.binary_location = chrome_bin
        opts.add_argument(f"user-data-dir={profile_dir}")
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(
            "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        return opts

    service = Service(executable_path=driver_path, log_path="/app/chromedriver.log")

    try:
        # Intento 1
        driver = webdriver.Chrome(service=service, options=get_options())
    except Exception as e:
        print(f"⚠️ Perfil corrupto detectado ({e}). Limpiando...")
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                print("✅ Perfil eliminado.")
        except Exception as delete_error:
            print(f"❌ Error borrando perfil: {delete_error}")

        print("🔄 Reintentando con perfil limpio...")
        try:
            driver = webdriver.Chrome(service=service, options=get_options())
        except Exception as final_e:
            print(f"❌ ERROR FATAL: {final_e}")
            raise final_e

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print("🌍 Cargando WhatsApp Web...")
    driver.get("https://web.whatsapp.com")

    driver_instance = driver
    return driver


# --- FUNCIÓN AGREGADA QUE FALTABA ---
def obtener_qr_screenshot():
    """
    Función usada por la VISTA WEB (views.py) para obtener el QR.
    Retorna (base64_image, status_text)
    """
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 15)

        # 1. ¿Ya estamos vinculados?
        try:
            # Buscamos el panel lateral de chats
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            return None, "YA_VINCULADO"
        except:
            pass  # Si no encuentra pane-side, sigue buscando QR

        # 2. ¿Hay QR?
        try:
            print("📸 Buscando QR para la web...")
            qr_canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
            time.sleep(1)  # Esperar renderizado
            return qr_canvas.screenshot_as_base64, "ESPERANDO_ESCANEO"
        except:
            return None, "CARGANDO"  # Aún no carga ni QR ni Chats

    except Exception as e:
        print(f"❌ Error obteniendo QR: {e}")
        return None, "ERROR"


def validar_sesion_activa():
    """
    Valida si hay sesión activa e imprime los chats.
    """
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 30)

    print("\n🕵️ VALIDANDO ESTADO DE LA SESIÓN...")
    try:
        elemento = wait.until(EC.any_of(
            EC.presence_of_element_located((By.ID, "pane-side")),
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        ))

        if elemento.tag_name == "canvas":
            print("⚠️ NO HAY SESIÓN. Se requiere escanear QR.")
            return False

        print("✅ SESIÓN ACTIVA DETECTADA.")
        print("\n📊 --- CHATS ABIERTOS ---")
        try:
            chats = driver.find_elements(By.XPATH, '//div[@id="pane-side"]//div[@role="listitem"]')
            for i, chat in enumerate(chats[:5]):
                print(f"   [{i + 1}] {chat.text.replace(chr(10), ' | ')[:60]}...")
        except:
            pass
        print("-------------------------\n")
        return True

    except Exception as e:
        print(f"❌ Error validando sesión: {e}")
        return False


def enviar_mensaje_browser(nombre_contacto, mensaje):
    driver = iniciar_navegador()
    try:
        xpath_input = '//div[@contenteditable="true"][@role="textbox"]'
        wait = WebDriverWait(driver, 10)
        caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))

        caja_texto.click()
        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)

        time.sleep(0.5)
        caja_texto.send_keys(Keys.ENTER)
        time.sleep(1)
        return True
    except Exception as e:
        print(f"⚠️ Error enviando a {nombre_contacto}: {e}")
        return False


def procesar_nuevos_mensajes(callback_inteligencia):
    try:
        driver = iniciar_navegador()

        # Buscamos indicadores de mensajes no leídos (bolitas verdes/span con unread)
        xpath_indicadores = (
            '//div[@id="pane-side"]'
            '//span[contains(@aria-label, "unread") or '
            'contains(@aria-label, "no leído") or '
            'contains(@aria-label, "mensaje")]'
        )

        posibles_indicadores = driver.find_elements(By.XPATH, xpath_indicadores)

        if not posibles_indicadores:
            return False

        print(f"\n🔔 Mensaje nuevo detectado.")

        # Click en el chat
        indicador = posibles_indicadores[0]
        chat_row = indicador.find_element(By.XPATH, './ancestor::div[@role="listitem"]')
        chat_row.click()
        time.sleep(2)

        # Leer mensaje
        msgs_in = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
        if not msgs_in:
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return False

        ultimo_mensaje = msgs_in[-1]
        try:
            texto = ultimo_mensaje.find_element(By.CSS_SELECTOR, "span.selectable-text").text
        except:
            texto = ultimo_mensaje.text.split('\n')[0]

        try:
            nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
        except:
            nombre = "Desconocido"

        print(f"📩 {nombre}: {texto}")

        if texto:
            respuesta = callback_inteligencia(texto, nombre)
            if respuesta:
                print(f"🤖 Respondiendo...")
                enviar_mensaje_browser(nombre, respuesta)

        # Salir (ESC)
        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1)
        return True

    except Exception as e:
        print(f"⚠️ Error ciclo: {e}")
        try:
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except:
            pass
        return False


def iniciar_bucle_bot(callback_ia):
    """
    Función maestra para ejecutar el bot.
    """
    print("🚀 INICIANDO BOT DE WHATSAPP...")

    if not validar_sesion_activa():
        print("❌ DETENIDO: Falta vincular. Ve a /whatsapp/browser/vincular/")
        return

    print("✅ ESCUCHANDO MENSAJES...")
    try:
        while True:
            print(".", end="", flush=True)
            procesar_nuevos_mensajes(callback_ia)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido.")