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

logger = logging.getLogger(__name__)

# Variable global para mantener la sesión viva
driver_instance = None


def iniciar_navegador():
    global driver_instance

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

    # --- CAMBIO CLAVE AQUÍ ---
    # Usamos una SUBCARPETA. La carpeta raiz '/app/chrome_user_data' es el volumen (intocable).
    # La carpeta '/app/chrome_user_data/session' sí se puede borrar si se corrompe.
    root_mount = "/app/chrome_user_data"
    profile_dir = os.path.join(root_mount, "session")

    def get_options():
        opts = Options()
        opts.binary_location = chrome_bin
        opts.add_argument(f"user-data-dir={profile_dir}")  # Apuntamos a la subcarpeta
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
        print(f"⚠️ Perfil corrupto detectado ({e}).")
        print(f"Bg 🧹 Borrando subcarpeta de sesión: {profile_dir}")

        # AHORA SÍ FUNCIONARÁ EL BORRADO
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                print("✅ Perfil borrado correctamente.")
        except Exception as delete_error:
            print(f"❌ Error al borrar perfil: {delete_error}")

        # Intento 2 (Limpio)
        print("🔄 Reintentando con perfil limpio...")
        try:
            driver = webdriver.Chrome(service=service, options=get_options())
        except Exception as final_e:
            print(f"❌ ERROR FATAL: {final_e}")
            raise final_e

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print("🌍 Navegando a WhatsApp Web...")
    driver.get("https://web.whatsapp.com")

    driver_instance = driver
    return driver

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

def procesar_nuevos_mensajes(callback_inteligencia):
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 5)

    try:
        if "WhatsApp" not in driver.title:
            driver.get("https://web.whatsapp.com")
            time.sleep(5)

        # 1. Buscar Panel Lateral
        try:
            panel_lateral = wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
        except:
            return False

        # 2. ESTRATEGIA DE BÚSQUEDA MEJORADA (Busca cualquier número verde)
        # En lugar de buscar 'listitem', buscamos directamante los indicadores de mensajes
        # El aria-label 'unread' o 'no leído' suele estar en un span

        xpath_unread = (
            '//div[@id="pane-side"]'  # Dentro del panel
            '//span[contains(@aria-label, "unread") or contains(@aria-label, "no leído")]'  # Que tenga la etiqueta
        )

        # Intentamos encontrar los INDICADORES (bolitas verdes), no los chats completos primero
        indicadores = driver.find_elements(By.XPATH, xpath_unread)

        if not indicadores:
            return False

        print(f"\n🔔 ¡Encontré {len(indicadores)} indicadores de mensajes nuevos!")

        # 3. Navegar desde el indicador hacia arriba para encontrar el Chat cliqueable
        # El indicador suele estar muy profundo, subimos 4 o 5 niveles hasta encontrar el div cliqueable
        indicador = indicadores[0]
        chat_cliqueable = indicador.find_element(By.XPATH,
                                                 './ancestor::div[@tabindex="-1" or @role="button" or contains(@class, "_ak72")]')

        # Click en el chat
        chat_cliqueable.click()
        time.sleep(2)

        # --- LEER MENSAJE (Igual que antes) ---
        try:
            msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
            if msgs:
                texto_msg = msgs[-1].text.replace('\n', ' ')
            else:
                texto_msg = ""

            # Buscar nombre
            try:
                nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
            except:
                nombre = "Desconocido"

            if texto_msg:
                print(f"📩 {nombre}: {texto_msg}")
                respuesta = callback_inteligencia(texto_msg, nombre)
                if respuesta:
                    enviar_mensaje_browser(nombre, respuesta)

            # Salir para limpiar selección
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return True

        except Exception as e:
            print(f"Error leyendo contenido: {e}")
            return False

    except Exception as e:
        # print(f"Scan error: {e}")
        return False