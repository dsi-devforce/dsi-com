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

# Variable global para mantener la sesión viva (Singleton)
driver_instance = None


def iniciar_navegador():
    """
    Inicia Chromium con la configuración específica para Docker.
    Maneja la persistencia de sesión y evita crashes de memoria.
    """
    global driver_instance

    # 1. Si ya existe y responde, lo reutilizamos
    if driver_instance is not None:
        try:
            _ = driver_instance.current_url  # Ping ligero
            return driver_instance
        except Exception:
            print("⚠️ Navegador desconectado. Reiniciando...")
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None

    print("🔧 Configurando Chrome (Docker)...")
    chrome_options = Options()

    # --- RUTAS ---
    chrome_options.binary_location = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"

    # --- PERFIL DE USUARIO (PERSISTENCIA) ---
    # Esto guarda la sesión de WhatsApp para no escanear QR siempre
    user_data_dir = "/app/chrome_user_data"

    # Limpieza preventiva de lock files (Evita error 'SingletonLock')
    lock_file = os.path.join(user_data_dir, "SingletonLock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print("🧹 SingletonLock eliminado.")
        except:
            pass

    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # --- FLAGS CRÍTICOS DOCKER ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # User Agent (Anti-bloqueo básico)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- SERVICIO ---
    service = Service(executable_path=driver_path, log_path="/app/chromedriver.log")

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Ocultar que es automatizado
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("🌍 Navegando a WhatsApp Web...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver

    except Exception as e:
        print(f"❌ ERROR AL INICIAR CHROME: {e}")
        raise e


def obtener_qr_screenshot():
    """
    Función auxiliar para la vista web (vincular).
    """
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 20)

        # Checar si ya estamos dentro
        try:
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            return None, "YA_VINCULADO"
        except:
            pass

        # Buscar QR
        qr_canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        time.sleep(1)
        return qr_canvas.screenshot_as_base64, "ESPERANDO_ESCANEO"

    except Exception:
        return None, "CARGANDO"  # O error real


def enviar_mensaje_browser(nombre_contacto, mensaje):
    """
    Escribe en el chat ACTIVO.
    """
    driver = iniciar_navegador()
    try:
        wait = WebDriverWait(driver, 10)

        # Selector robusto para la caja de texto
        xpath_input = '//div[@contenteditable="true"][@role="textbox"]'
        caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))

        caja_texto.click()

        # Escribir con saltos de línea
        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)

        time.sleep(0.5)
        caja_texto.send_keys(Keys.ENTER)
        return True

    except Exception as e:
        print(f"⚠️ Error enviando a {nombre_contacto}: {e}")
        return False


def procesar_nuevos_mensajes(callback_inteligencia):
    """
    Escanea chats no leídos, extrae el mensaje y llama al callback.
    """
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 5)

    try:
        # Verificar que estamos en la lista de chats
        try:
            panel = wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
        except:
            # Si no hay panel, quizá no hemos cargado o se perdió sesión
            return False

        # --- BUSCAR NO LEÍDOS ---
        # Buscamos iconos verdes con número o aria-label 'unread'
        xpath_unread = './/span[@aria-label and contains(@aria-label, "unread")]/ancestor::div[@role="listitem"]'
        # Alternativa por color verde (más genérica si falla el aria-label)
        # xpath_unread = './/span[contains(@aria-label, "no leído")]/ancestor::div[@role="listitem"]'

        chats_nuevos = driver.find_elements(By.XPATH, xpath_unread)

        if not chats_nuevos:
            return False

        print(f"\n🔔 {len(chats_nuevos)} chats con mensajes nuevos.")

        # Procesamos solo el primero para no perder el foco en el bucle
        # (El bucle del comando se encargará de llamar de nuevo para el siguiente)
        chat = chats_nuevos[0]

        # Click para abrir
        chat.click()
        time.sleep(2)  # Esperar carga de mensajes

        # --- LEER NOMBRE Y MENSAJE ---
        try:
            # Nombre del contacto (Header)
            header_xpath = '//header//span[@dir="auto"]'
            nombre_contacto = driver.find_element(By.XPATH, header_xpath).text
        except:
            nombre_contacto = "Desconocido"

        try:
            # Buscar burbujas de mensaje ENTRANTES (message-in)
            msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
            if msgs:
                last_msg_element = msgs[-1]

                # Intentar sacar el texto limpio
                try:
                    # WhatsApp suele poner el texto en un span con dir="ltr" o _TbF (clase cambia)
                    # Buscamos cualquier span con texto dentro de la burbuja
                    texto_msg = last_msg_element.find_element(By.CSS_SELECTOR, "span.selectable-text span").text
                except:
                    # Fallback: obtener todo el texto de la burbuja
                    texto_msg = last_msg_element.text
            else:
                texto_msg = ""

        except Exception as e:
            print(f"Error leyendo burbuja: {e}")
            texto_msg = ""

        # --- LOGICA DE RESPUESTA ---
        if texto_msg:
            print(f"📩 {nombre_contacto}: {texto_msg}")

            # Llamamos a tu IA (Ollama)
            respuesta = callback_inteligencia(texto_msg, nombre_contacto)

            if respuesta:
                print(f"🤖 Respondiendo...")
                enviar_mensaje_browser(nombre_contacto, respuesta)
                # Opcional: Archivar chat o salir para limpiar estado

        # Volvemos al inicio (presionando ESC a veces limpia la selección)
        try:
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except:
            pass

        return True

    except Exception as e:
        # print(f"Ciclo scan error: {e}") # Debug ruidoso off
        return False