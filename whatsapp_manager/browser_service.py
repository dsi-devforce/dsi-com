import os
import time
import base64
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from django.conf import settings
import shutil

logger = logging.getLogger(__name__)

# Variable global
driver_instance = None


def iniciar_navegador():
    global driver_instance

    if driver_instance is not None:
        try:
            _ = driver_instance.title
            return driver_instance
        except:
            print("⚠️ Reiniciando navegador...")
            driver_instance = None

    print("Configurando opciones de Chrome (Docker System)...")
    chrome_options = Options()

    # --- LIMPIEZA DE CANDADOS (NUEVO) ---
    # Esto elimina el archivo que bloquea Chrome si se cerró mal antes
    user_data_dir = "/app/chrome_user_data"
    lock_file = os.path.join(user_data_dir, "SingletonLock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print("🧹 SingletonLock eliminado (limpieza de crash previo).")
        except Exception as e:
            print(f"⚠️ No se pudo eliminar lock file: {e}")

    # --- RUTAS ---
    chrome_options.binary_location = "/usr/bin/chromium"

    # --- FLAGS ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--window-size=1920,1080")

    # User Agent
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')

    # Perfil
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # --- DRIVER ---
    service = Service(executable_path="/usr/bin/chromedriver", log_path="/app/chromedriver.log", verbose=True)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("✅ Navegador iniciado. Navegando a WhatsApp...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver

    except Exception as e:
        print(f"❌ ERROR FATAL AL INICIAR CHROME: {e}")
        # ... resto del manejo de error ...
        raise e

def obtener_qr_screenshot():
    """
    Espera a que cargue el canvas del QR y toma una captura.
    Retorna: (base64_string, estado)
    Estados: CARGANDO, YA_VINCULADO, ESPERANDO_ESCANEO, ERROR
    """
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 20)

        print("Verificando estado de la sesión...")

        # 1. Comprobar si ya estamos dentro (panel lateral visible)
        try:
            # Buscamos el panel de la izquierda o la foto de perfil
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            print("✅ Sesión activa detectada (No se requiere QR).")
            return None, "YA_VINCULADO"
        except:
            # Si no aparece en 20s (o falla antes), asumimos que no estamos logueados
            pass

        # 2. Buscar el código QR
        print("Buscando código QR en pantalla...")
        try:
            # Buscamos el elemento canvas donde WhatsApp dibuja el QR
            qr_canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))

            # Pequeña pausa para asegurar renderizado
            time.sleep(1.5)

            # Capturamos solo el canvas en base64
            qr_base64 = qr_canvas.screenshot_as_base64
            print("📸 QR capturado correctamente.")
            return qr_base64, "ESPERANDO_ESCANEO"

        except:
            # Si tampoco aparece el QR, puede que la página siga cargando
            print("⚠️ No se encontró QR ni Chat. La página podría estar cargando aún.")
            return None, "CARGANDO"

    except Exception as e:
        print(f"Error en obtener_qr_screenshot: {e}")
        return None, "ERROR"


def enviar_mensaje_browser(nombre_contacto, mensaje):
    """
    Escribe y envía un mensaje.
    IMPORTANTE: Asume que el chat con 'nombre_contacto' YA ESTÁ ABIERTO y enfocado.
    """
    driver = iniciar_navegador()
    try:
        # 1. Buscar la caja de texto editable
        # XPath busca el div editable en el footer (data-tab puede cambiar, pero contenteditable es seguro)
        caja_texto = driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')

        caja_texto.click()

        # 2. Escribir (simulando tipeo humano si fuera necesario, aquí directo por velocidad)
        # Limpiamos solo si estamos seguros que no borramos algo importante
        # caja_texto.clear()

        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)  # Salto de línea sin enviar

        # 3. Enviar
        time.sleep(0.5)
        caja_texto.send_keys(Keys.ENTER)

        # Esperar confirmación visual (opcional) o simplemente un tiempo prudente
        time.sleep(1)
        return True

    except Exception as e:
        logger.error(f"Error enviando mensaje a {nombre_contacto}: {e}")
        return False


def procesar_nuevos_mensajes(callback_inteligencia):
    """
    Escanea la lista de chats buscando indicadores de 'No leído'.
    Retorna True si encontró algo, False si no.
    """
    driver = iniciar_navegador()

    try:
        # Verificación rápida de sanidad: ¿Seguimos en WhatsApp?
        if "WhatsApp" not in driver.title:
            print("⚠️ El navegador perdió el foco de WhatsApp. Recargando...")
            driver.get("https://web.whatsapp.com")
            time.sleep(5)

        # Buscamos el panel lateral
        try:
            panel_lateral = driver.find_element(By.ID, "pane-side")
        except:
            # Si no hay panel lateral, quizá se cerró la sesión o está cargando
            return False

        # --- ESTRATEGIA DE BÚSQUEDA ---
        # Buscamos iconos de mensajes no leídos (aria-label="X unread message")
        xpath_unread = (
            ".//div[@role='listitem']"
            "//span[contains(@aria-label, 'unread') or contains(@aria-label, 'no leído')]"
            "/ancestor::div[@role='listitem']"
        )

        chats_activos = panel_lateral.find_elements(By.XPATH, xpath_unread)

        # Fallback visual: Si aria-label falla, buscamos spans verdes genéricos en la zona de meta-info
        if not chats_activos:
            # Este xpath busca spans que tengan color verde (WhatsApp usa clases dinámicas pero estilos computados a veces ayudan)
            # Por ahora, confiamos en aria-label que es lo más estable en 2024.
            pass

        if not chats_activos:
            return False

        print(f"\n🔔 Actividad detectada: {len(chats_activos)} chats pendientes.")

        for chat in chats_activos:
            try:
                # A. Entrar al chat
                chat.click()
                time.sleep(2)  # Espera carga del historial

                # B. Identificar quién escribe
                try:
                    header = driver.find_element(By.TAG_NAME, "header")
                    nombre_contacto = header.find_element(By.XPATH, ".//span[@dir='auto']").text
                except:
                    nombre_contacto = "Desconocido"

                # C. Leer lo último que nos dijeron
                try:
                    # Buscamos burbujas de mensajes entrantes ('message-in')
                    mensajes = driver.find_elements(By.CSS_SELECTOR, "div.message-in")

                    if mensajes:
                        ultimo_burbuja = mensajes[-1]
                        # Extraer texto de la burbuja (quitando la hora)
                        texto_bruto = ultimo_burbuja.text
                        lines = texto_bruto.split('\n')
                        # Normalmente la última línea es la hora, tomamos lo anterior
                        texto_msg = "\n".join(lines[:-1]) if len(lines) > 1 else lines[0]
                    else:
                        texto_msg = ""

                except Exception as e:
                    print(f"Error leyendo burbuja: {e}")
                    texto_msg = ""

                # Solo procesamos si hay texto válido (evitamos responder a audios vacíos por ahora)
                if texto_msg and len(texto_msg.strip()) > 0:
                    print(f"📩 {nombre_contacto} dice: {texto_msg}")

                    # D. Llamar al cerebro
                    respuesta = callback_inteligencia(texto_msg, nombre_contacto)

                    if respuesta:
                        print(f"🤖 Respondiendo: {respuesta[:30]}...")
                        enviar_mensaje_browser(nombre_contacto, respuesta)

                # E. Pausa anti-ban
                time.sleep(2)

            except Exception as e:
                print(f"⚠️ Error procesando un chat individual: {e}")
                continue

        return True

    except Exception as e:
        # print(f"Error ciclo escaneo: {e}")
        return False