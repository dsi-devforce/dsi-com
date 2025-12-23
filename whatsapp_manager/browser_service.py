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

    # ... (tu código de verificación de driver existente sigue igual) ...

    print("Configurando opciones de Chrome (Docker System)...")
    chrome_options = Options()

    # --- RUTAS ---
    # Usamos las rutas HARDCODED que sabemos que funcionan en tu Docker
    chrome_options.binary_location = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"

    # --- FLAGS (Limpios y minimalistas) ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # ❌ COMENTA ESTA LÍNEA TEMPORALMENTE (Culpable probable de crashes)
    # chrome_options.add_argument("--remote-debugging-port=9222")

    # ❌ COMENTA EL PERFIL TEMPORALMENTE (Para descartar corrupción)
    # user_data_dir = "/app/chrome_user_data"
    # chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # User Agent
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')

    # --- SERVICE CON LOGS ---
    # Activamos logs detallados por si vuelve a fallar
    service = Service(
        executable_path=driver_path,
        log_path="/app/chromedriver.log",
        service_args=["--verbose"]
    )

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("✅ Navegador iniciado. Cargando WhatsApp...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver

    except Exception as e:
        print(f"❌ ERROR FATAL AL INICIAR CHROME: {e}")
        # Leer el log detallado si falla
        try:
            with open("/app/chromedriver.log", "r") as f:
                print("--- LOG DEL DRIVER (Últimas líneas) ---")
                print(f.read()[-1000:])
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

def procesar_nuevos_mensajes(callback_inteligencia):
    """
    Escanea la lista de chats buscando indicadores de 'No leído'.
    Retorna True si encontró algo y lo procesó, False si no.
    """
    try:
        driver = iniciar_navegador()

        # Verificación rápida de sanidad: ¿Seguimos en WhatsApp?
        if "WhatsApp" not in driver.title:
            print("⚠️ El navegador perdió el foco de WhatsApp. Intentando recuperar...")
            driver.get("https://web.whatsapp.com")
            time.sleep(5)

        # Buscamos el panel lateral (donde están los chats)
        try:
            wait = WebDriverWait(driver, 5)
            panel_lateral = wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
        except:
            # Si no hay panel lateral, quizá se cerró la sesión o está cargando
            return False

        # --- ESTRATEGIA DE BÚSQUEDA ---
        # Buscamos iconos de mensajes no leídos.
        # WhatsApp usa aria-label="X unread message" o "X mensajes no leídos"
        xpath_unread = (
            './/span[contains(@aria-label, "unread") or contains(@aria-label, "no leído")]'
            '/ancestor::div[@role="listitem"]'
        )

        chats_activos = panel_lateral.find_elements(By.XPATH, xpath_unread)

        if not chats_activos:
            return False

        print(f"\n🔔 Actividad detectada: {len(chats_activos)} chats pendientes.")

        # Procesamos solo el primer chat encontrado por ciclo para mantener estabilidad
        # El bucle externo del comando se encargará de volver a llamar a esta función para los siguientes.
        chat = chats_activos[0]

        try:
            # A. Entrar al chat
            chat.click()
            time.sleep(2)  # Espera carga del historial de mensajes

            # B. Identificar quién escribe (Nombre del contacto)
            try:
                # Buscamos en el header del chat activo
                header_xpath = '//header//span[@dir="auto"]'
                nombre_contacto = driver.find_element(By.XPATH, header_xpath).text
            except:
                nombre_contacto = "Desconocido"

            # C. Leer lo último que nos dijeron
            try:
                # Buscamos burbujas de mensajes entrantes ('message-in')
                mensajes = driver.find_elements(By.CSS_SELECTOR, "div.message-in")

                if mensajes:
                    ultimo_burbuja = mensajes[-1]

                    # Intentamos extraer el texto limpio.
                    # A veces el texto está dentro de un span con clase 'selectable-text'
                    try:
                        texto_msg = ultimo_burbuja.find_element(By.CSS_SELECTOR, "span.selectable-text span").text
                    except:
                        # Si falla, tomamos todo el texto de la burbuja y limpiamos la hora
                        texto_bruto = ultimo_burbuja.text
                        lines = texto_bruto.split('\n')
                        # Normalmente la última línea es la hora, tomamos lo anterior
                        texto_msg = "\n".join(lines[:-1]) if len(lines) > 1 else lines[0]
                else:
                    texto_msg = ""

            except Exception as e:
                print(f"Error leyendo burbuja: {e}")
                texto_msg = ""

            # D. Procesar respuesta
            # Solo procesamos si hay texto válido (evitamos responder a audios vacíos por ahora)
            if texto_msg and len(texto_msg.strip()) > 0:
                print(f"📩 {nombre_contacto} dice: {texto_msg}")

                # Llamar al cerebro (tu función callback_ia)
                respuesta = callback_inteligencia(texto_msg, nombre_contacto)

                if respuesta:
                    print(f"🤖 Respondiendo: {respuesta[:30]}...")
                    enviar_mensaje_browser(nombre_contacto, respuesta)

            # E. Salir del chat (Opcional pero recomendado para resetear estado visual)
            # Presionamos ESC para deseleccionar mensajes o cerrar menús
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()

            # Pequeña pausa anti-ban
            time.sleep(1)
            return True

        except Exception as e:
            print(f"⚠️ Error procesando chat individual: {e}")
            return False

    except Exception as e:
        # print(f"Error ciclo escaneo: {e}") # Descomentar para debug profundo
        return False