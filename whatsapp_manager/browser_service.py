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
    Si encuentra uno:
      1. Hace clic en el chat.
      2. Lee el último mensaje.
      3. Llama a 'callback_inteligencia' para obtener la respuesta.
      4. Escribe la respuesta.
    """
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 5)

    try:
        # 1. Buscar chats con indicadores verdes (burbujas de mensajes no leídos)
        # El aria-label suele contener "unread message" o similar
        chats_no_leidos = driver.find_elements(By.XPATH,
                                               '//span[@aria-label and contains(@aria-label, "unread")]/ancestor::div[@role="listitem"]')

        if not chats_no_leidos:
            return False  # No hay nada nuevo

        logger.info(f"Encontrados {len(chats_no_leidos)} chats con mensajes nuevos.")

        for chat in chats_no_leidos:
            try:
                # A. Abrir el chat
                chat.click()
                time.sleep(2)  # Esperar a que cargue la conversación

                # B. Identificar quién nos escribe (Nombre del contacto en el header)
                header_title = driver.find_element(By.XPATH, '//header//div[@role="button"]//span[@dir="auto"]')
                nombre_contacto = header_title.text

                # C. Leer el último mensaje recibido
                # Buscamos todos los mensajes que sean "message-in" (entrantes)
                mensajes_entrantes = driver.find_elements(By.XPATH,
                                                          '//div[contains(@class, "message-in")]//span[@dir="ltr"]')

                if mensajes_entrantes:
                    ultimo_mensaje = mensajes_entrantes[-1].text
                    logger.info(f"Mensaje de {nombre_contacto}: {ultimo_mensaje}")

                    # D. PROCESAR CON TU IA (Callback)
                    # Aquí llamamos a la lógica que ya tienes en views.py
                    respuesta = callback_inteligencia(ultimo_mensaje, nombre_contacto)

                    if respuesta:
                        # E. Responder
                        enviar_mensaje_browser(nombre_contacto, respuesta)
                        logger.info(f"Respuesta enviada a {nombre_contacto}")

                # F. Volver al inicio o marcar como leído (simplemente pasando al siguiente loop)

            except Exception as e:
                logger.error(f"Error procesando un chat específico: {e}")
                continue

        return True

    except Exception as e:
        # Es normal que falle si no encuentra elementos, no queremos llenar el log de errores
        return False