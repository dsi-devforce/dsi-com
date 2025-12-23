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
from selenium.webdriver.common.keys import Keys
# Asegúrate de importar esto arriba
import logging

logger = logging.getLogger(__name__)
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


def enviar_mensaje_browser(telefono, mensaje):
    """
    Escribe y envía un mensaje en el chat actualmente abierto o busca uno nuevo.
    Nota: Por simplicidad, asume que el chat ya está abierto por la función de lectura.
    """
    driver = iniciar_navegador()
    try:
        # 1. Buscar la caja de texto
        # Estrategia: Buscar el elemento editable que está en el footer principal
        caja_texto = driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')

        # 2. Escribir el mensaje
        caja_texto.click()
        # Limpiar por si acaso
        caja_texto.clear()

        # Simulamos escritura humana (a veces es necesario para que WA detecte actividad)
        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)  # Salto de línea

        # 3. Enviar
        caja_texto.send_keys(Keys.ENTER)
        time.sleep(1)  # Esperar un poco a que se envíe
        return True

    except Exception as e:
        logger.error(f"Error escribiendo mensaje: {e}")
        return False


def procesar_nuevos_mensajes(callback_inteligencia):
    """
    Escanea la lista de chats buscando indicadores de 'No leído'.
    """
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 5)

    try:
        # --- MEJORA DE SELECTORES ---
        # Buscamos en el panel lateral ('pane-side') cualquier icono que indique mensajes no leídos.
        # WhatsApp usa aria-label="X unread messages" o "X mensajes no leídos".
        xpath_busqueda = (
            "//div[@id='pane-side']"
            "//span[contains(@aria-label, 'unread') or contains(@aria-label, 'no leído') or contains(@aria-label, 'mensaje')]"
            "/ancestor::div[@role='listitem']"  # Subimos al contenedor del chat
        )

        chats_no_leidos = driver.find_elements(By.XPATH, xpath_busqueda)

        # Filtramos falsos positivos (a veces el buscador trae cosas que no son chats)
        chats_reales = [c for c in chats_no_leidos if c.is_displayed()]

        if not chats_reales:
            # logger.info("Escaneando... (Sin mensajes nuevos)") # Comentar para no saturar logs
            return False

        logger.info(f"✅ ¡BINGO! Encontrados {len(chats_reales)} chats con mensajes nuevos.")

        for chat in chats_reales:
            try:
                # A. Abrir el chat
                chat.click()
                time.sleep(1)  # Esperar a que cargue

                # B. Identificar contacto (Intentamos varios selectores por si acaso)
                try:
                    nombre_contacto = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
                except:
                    nombre_contacto = "Desconocido"

                # C. Leer último mensaje (Buscamos mensajes entrantes 'message-in')
                try:
                    mensajes = driver.find_elements(By.XPATH, '//div[contains(@class, "message-in")]//span[@dir="ltr"]')
                    if mensajes:
                        ultimo_mensaje = mensajes[-1].text
                    else:
                        ultimo_mensaje = "(Imagen o Audio)"
                except:
                    ultimo_mensaje = "Error leyendo texto"

                logger.info(f"📩 Mensaje recibido de {nombre_contacto}: {ultimo_mensaje}")

                # D. PROCESAR RESPUESTA (Callback)
                respuesta = callback_inteligencia(ultimo_mensaje, nombre_contacto)

                if respuesta:
                    enviar_mensaje_browser(nombre_contacto, respuesta)
                    logger.info(f"📤 Respuesta enviada a {nombre_contacto}: {respuesta}")

                # E. Pequeña pausa para no ir muy rápido
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error procesando chat individual: {e}")
                continue

        return True

    except Exception as e:
        # logger.error(f"Error ciclo de escaneo: {e}")
        return False