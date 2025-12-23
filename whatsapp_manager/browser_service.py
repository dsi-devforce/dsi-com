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

    print("Configurando opciones de Chrome...")
    chrome_options = Options()

    # --- RUTAS DE INSTALACIÓN (Debian/Docker estándar) ---
    chrome_options.binary_location = "/usr/bin/chromium"

    # --- FLAGS OBLIGATORIOS PARA DOCKER ---
    chrome_options.add_argument("--headless")  # Usamos el headless clásico (más estable)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--remote-debugging-port=9222")

    # --- EVITAR DETECCIÓN ---
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument("--window-size=1920,1080")

    # --- PERFIL DE USUARIO ---
    # Aseguramos que la carpeta se cree dentro de /app para evitar problemas de ruta
    user_data_dir = os.path.join(os.getcwd(), 'chrome_user_data')
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    # Configuración del Driver
    service_path = "/usr/bin/chromedriver"

    # Habilitar logs verbose para ver por qué falla si vuelve a pasar
    service = Service(executable_path=service_path, log_path="/app/chromedriver.log", verbose=True)

    try:
        print(f"Iniciando Chrome en {chrome_options.binary_location}...")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Script anti-detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("Navegador iniciado correctamente. Yendo a WhatsApp...")
        driver.get("https://web.whatsapp.com")

        driver_instance = driver
        return driver
    except Exception as e:
        print(f"ERROR AL INICIAR CHROME: {e}")
        # Si falla, lee el log generado
        if os.path.exists("/app/chromedriver.log"):
            print("--- CONTENIDO DEL LOG DE CHROMEDRIVER ---")
            with open("/app/chromedriver.log", "r") as f:
                print(f.read())
            print("---------------------------------------")
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
    Versión V2: Selectores más agresivos y robustos.
    """
    driver = iniciar_navegador()

    try:
        # Buscamos el panel lateral primero para asegurar contexto
        panel_lateral = driver.find_element(By.ID, "pane-side")

        # ESTRATEGIA MULTI-SELECTOR
        # Buscamos iconos verdes que tengan números dentro.
        # WhatsApp suele usar spans con colores específicos para las notificaciones.
        # Buscamos cualquier elemento con aria-label que diga "unread" o "no leído"
        xpath_inteligente = (
            ".//div[@role='listitem']"  # Cada fila de chat
            "//span[contains(@aria-label, 'unread') or contains(@aria-label, 'no leído')]"  # Indicador
            "/ancestor::div[@role='listitem']"  # Volvemos a subir al chat padre
        )

        chats_candidatos = panel_lateral.find_elements(By.XPATH, xpath_inteligente)

        # FILTRO EXTRA: Si la búsqueda por aria-label falla, buscamos por estructura visual (icono verde)
        if not chats_candidatos:
            # Este selector busca el circulito verde típico de notificaciones (suele ser el único span verde en la derecha)
            # Nota: Esto es más frágil, pero útil como fallback
            xpath_visual = ".//div[@role='listitem']//span[contains(@style, 'color') or @class='_1pJ9J']"
            # (La clase _1pJ9J cambia, pero la estructura suele mantenerse)
            pass

        if not chats_candidatos:
            return False  # Nada nuevo

        print(f"\n🔔 Detectados {len(chats_candidatos)} chats con actividad.")

        for chat in chats_candidatos:
            try:
                # 1. Abrir chat
                chat.click()
                time.sleep(2)  # Espera carga

                # 2. Obtener Nombre Contacto
                try:
                    # Buscamos el título en el header principal
                    header = driver.find_element(By.TAG_NAME, "header")
                    nombre_contacto = header.find_element(By.XPATH, ".//span[@dir='auto']").text
                except:
                    nombre_contacto = "Desconocido"

                # 3. Leer Último Mensaje
                try:
                    # Buscamos todos los globos de mensajes entrantes
                    # 'message-in' es una clase muy estable en WA Web
                    mensajes_entrantes = driver.find_elements(By.CSS_SELECTOR, "div.message-in")

                    if mensajes_entrantes:
                        ultimo_msg_obj = mensajes_entrantes[-1]
                        # Intentamos extraer el texto, ignorando la hora
                        texto_completo = ultimo_msg_obj.text
                        # Limpieza básica (quitar la hora que suele estar al final)
                        lines = texto_completo.split('\n')
                        texto_msg = lines[0] if lines else "[Audio/Imagen]"
                    else:
                        texto_msg = "[Nuevo chat sin historial visible]"

                except Exception as e:
                    print(f"Error leyendo texto: {e}")
                    texto_msg = "."

                print(f"📨 Procesando mensaje de {nombre_contacto}: '{texto_msg}'")

                # 4. INTELIGENCIA ARTIFICIAL (Ollama)
                # Solo respondemos si el mensaje tiene texto real
                if len(texto_msg) > 1:
                    respuesta = callback_inteligencia(texto_msg, nombre_contacto)

                    if respuesta:
                        print(f"🤖 IA Responde: {respuesta}")
                        enviar_mensaje_browser(nombre_contacto, respuesta)

                # 5. IMPORTANTE: Deseleccionar chat o marcar leído implícitamente
                # Al responder, ya cuenta como leído.
                # Hacemos una pausa para no parecer spam bot
                time.sleep(3)

            except Exception as e:
                print(f"⚠️ Error en ciclo de un chat: {e}")
                continue

        return True

    except Exception as e:
        # print(f"Error general escaneo: {e}")
        return False