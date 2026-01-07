import json
import shutil
import os
import time
import logging
import re
import threading
import base64
import io
import uuid
from PIL import Image

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

# --- GESTIÓN DE SESIONES MÚLTIPLES ---
# Estructura: { connection_id: { 'driver': driver_obj, 'lock': RLock(), 'thread': thread_obj } }
active_sessions = {}
global_registry_lock = threading.RLock()  # Candado para modificar el diccionario active_sessions


def get_session_context(connection_id):
    """
    Recupera o inicializa el contexto de una conexión específica.
    Devuelve el diccionario de esa sesión.
    """
    with global_registry_lock:
        if connection_id not in active_sessions:
            active_sessions[connection_id] = {
                'driver': None,
                'lock': threading.RLock(),
                'thread': None
            }
        return active_sessions[connection_id]


def iniciar_navegador(connection_id):
    """
    Inicia el navegador para una conexión específica con su propio perfil persistente.
    """
    context = get_session_context(connection_id)
    driver = context.get('driver')

    # Verificar si el driver actual sigue vivo
    if driver is not None:
        try:
            _ = driver.current_url
            return driver
        except:
            try:
                driver.quit()
            except:
                pass
            context['driver'] = None

    print(f"[ID:{connection_id}] 🔧 Iniciando motor de Chrome...")
    chrome_bin = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"
    root_mount = "/app/chrome_user_data"

    # PERFIL AISLADO POR ID
    profile_dir = os.path.join(root_mount, f"session_{connection_id}")

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

    service = Service(executable_path=driver_path, log_path=f"/app/chromedriver_{connection_id}.log")

    try:
        driver = webdriver.Chrome(service=service, options=get_options())
    except Exception as e:
        print(f"[ID:{connection_id}] ⚠️ Perfil bloqueado o corrupto. Limpiando...")
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
        except:
            pass

        print(f"[ID:{connection_id}] 🔄 Reiniciando limpio...")
        driver = webdriver.Chrome(service=service, options=get_options())

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.get("https://web.whatsapp.com")

    # Guardamos la referencia en el contexto de la sesión
    context['driver'] = driver
    return driver


# --- LÓGICA DE SECUENCIA INTELIGENTE ---

def garantizar_sesion_activa(connection_id):
    """
    Esta función NO RETORNA hasta que el usuario esté logueado en la sesión específica.
    """
    context = get_session_context(connection_id)
    session_lock = context['lock']

    with session_lock:
        driver = iniciar_navegador(connection_id)
        wait = WebDriverWait(driver, 20)

        print(f"\n[ID:{connection_id}] 🕵️ 1. VERIFICANDO ESTADO DE SESIÓN...")

        try:
            # Esperamos a que cargue ALGO (QR o Chat)
            elemento = WebDriverWait(driver, 30).until(EC.any_of(
                EC.presence_of_element_located((By.ID, "pane-side")),
                EC.presence_of_element_located((By.TAG_NAME, "canvas")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-ref]"))
            ))

            # ESCENARIO A: YA ESTAMOS DENTRO
            if elemento.get_attribute("id") == "pane-side":
                print(f"[ID:{connection_id}] ✅ ¡ÉXITO! Panel de chats detectado.")
                return True

            # ESCENARIO B: NECESITAMOS ESCANEAR
            print(f"[ID:{connection_id}] ⚠️ No se detectó sesión activa. Generando QR...")

            qr_path = f"/app/qr_login_{connection_id}.png"
            time.sleep(1)
            driver.save_screenshot(qr_path)

            print(f"[ID:{connection_id}] 💾 Captura QR guardada en {qr_path}.")
            print(f"[ID:{connection_id}] ⏳ Esperando escaneo...")

            start_time = time.time()
            timeout = 300  # 5 minutos

            while time.time() - start_time < timeout:
                try:
                    WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, "pane-side")))
                    break
                except:
                    time.sleep(2)

            if time.time() - start_time >= timeout:
                print(f"\n[ID:{connection_id}] ❌ Timeout esperando escaneo.")
                return False

            print(f"\n[ID:{connection_id}] 🎉 ¡VINCULACIÓN DETECTADA!")

            # Estabilización
            for i in range(5, 0, -1):
                time.sleep(1)

            return True

        except Exception as e:
            print(f"\n[ID:{connection_id}] ❌ Error fatal verificando sesión: {e}")
            try:
                driver.save_screenshot(f"/app/debug_error_sesion_{connection_id}.png")
            except:
                pass
            return False


def imprimir_resumen_chats(connection_id):
    """Imprime los últimos chats para confirmar visualmente al usuario"""
    context = get_session_context(connection_id)
    with context['lock']:
        driver = iniciar_navegador(connection_id)
        print(f"\n[ID:{connection_id}] 📊 --- CHATS ACTIVOS ---")
        try:
            chats = driver.find_elements(By.XPATH, '//div[@id="pane-side"]//div[@role="listitem"]')
            for i, chat in enumerate(chats[:3]):
                print(f"   [{i + 1}] {chat.text.replace(chr(10), ' | ')[:50]}...")
        except:
            print("   (No se pudieron leer los textos de los chats)")
        print("-------------------------\n")


def enviar_mensaje_browser(connection_id, nombre_contacto, mensaje):
    context = get_session_context(connection_id)

    with context['lock']:
        driver = iniciar_navegador(connection_id)
        print(f"[ID:{connection_id}] ⌨️ Intentando escribir a: {nombre_contacto}...")
        try:
            xpath_input = '//footer//div[@contenteditable="true"][@role="textbox"]'
            wait = WebDriverWait(driver, 10)

            try:
                caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))
            except:
                xpath_alt = '//div[@contenteditable="true"][@data-tab]'
                caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_alt)))

            driver.execute_script("arguments[0].focus();", caja_texto)
            time.sleep(0.2)

            script_escritura = """
                           var element = arguments[0];
                           var text = arguments[1];
                           document.execCommand('insertText', false, text);
                           if (element.textContent !== text) {
                               element.innerHTML = text.replace(/\\n/g, '<br>');
                               var eventInput = new Event('input', { bubbles: true });
                               element.dispatchEvent(eventInput);
                           }
                           """
            driver.execute_script(script_escritura, caja_texto, mensaje)

            time.sleep(1)

            try:
                boton_enviar = driver.find_element(By.XPATH, '//span[@data-icon="send"]/ancestor::button')
                boton_enviar.click()
            except:
                caja_texto.send_keys(Keys.ENTER)

            print(f"[ID:{connection_id}] 📤 ¡Mensaje enviado!")
            return True

        except Exception as e:
            print(f"[ID:{connection_id}] ❌ ERROR enviando mensaje: {e}")
            return False


def procesar_nuevos_mensajes(connection_id, callback_inteligencia):
    context = get_session_context(connection_id)

    try:
        # Usamos el lock de esta sesión específica
        with context['lock']:
            driver = iniciar_navegador(connection_id)
            wait = WebDriverWait(driver, 5)

            xpath_indicadores = '//div[@id="pane-side"]//span[contains(@aria-label, "unread") or contains(@aria-label, "no leído")]'
            indicadores = driver.find_elements(By.XPATH, xpath_indicadores)

            if not indicadores:
                return False

            print(f"\n[ID:{connection_id}] 🔔 Mensaje nuevo detectado ({len(indicadores)} pendientes).")
            indicador = indicadores[0]

            try:
                chat_element = indicador.find_element(By.XPATH, './ancestor::div[@role="listitem"]')
            except:
                chat_element = indicador

            driver.execute_script("arguments[0].scrollIntoView(true);", chat_element)
            time.sleep(0.5)

            try:
                chat_element.click()
            except:
                driver.execute_script("arguments[0].click();", chat_element)

            time.sleep(2)

            # --- LECTURA DE MENSAJES ---
            msgs_containers = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
            if not msgs_containers:
                webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                return False

            last_msg_container = msgs_containers[-1]
            texto = ""
            nombre = "Desconocido"
            tipo_adjunto = None

            try:
                if last_msg_container.find_elements(By.CSS_SELECTOR, "span[data-icon='video-play']"):
                    tipo_adjunto = "VIDEO"
                elif last_msg_container.find_elements(By.CSS_SELECTOR, "span[data-icon='audio-play']"):
                    tipo_adjunto = "AUDIO"
                elif last_msg_container.find_elements(By.CSS_SELECTOR, "span[data-icon^='doc-']"):
                    tipo_adjunto = "DOCUMENTO"
                else:
                    imgs_detectadas = last_msg_container.find_elements(By.CSS_SELECTOR,
                                                                       "div[role='button'] img[src^='blob:']")
                    if imgs_detectadas:
                        tipo_adjunto = "IMAGEN"
                        try:
                            blob_url = imgs_detectadas[0].get_attribute("src")
                            script_js = """
                                var uri = arguments[0];
                                var callback = arguments[1];
                                fetch(uri).then(r => r.blob()).then(blob => {
                                    var reader = new FileReader();
                                    reader.readAsDataURL(blob);
                                    reader.onloadend = function() { callback(reader.result); }
                                }).catch(e => callback(null));
                            """
                            resultado_base64 = driver.execute_async_script(script_js, blob_url)

                            if resultado_base64:
                                header, encoded = resultado_base64.split(",", 1)
                                data_bytes = base64.b64decode(encoded)
                                imagen_pil = Image.open(io.BytesIO(data_bytes))

                                output_dir = "/app/media/whatsapp_received"
                                os.makedirs(output_dir, exist_ok=True)
                                nombre_archivo = f"img_{uuid.uuid4().hex[:8]}.webp"
                                ruta_final = os.path.join(output_dir, nombre_archivo)
                                imagen_pil.save(ruta_final, "WEBP", quality=80)

                                tipo_adjunto = ruta_final
                        except Exception as e_img:
                            print(f"   ⚠️ Error imagen: {e_img}")

            except Exception as e_media:
                print(f"⚠️ Error media: {e_media}")

            # Extracción de Texto y Nombre (Simplificada para brevedad, misma lógica original)
            try:
                nucleo_mensaje = last_msg_container.find_element(By.CSS_SELECTOR, "div[data-pre-plain-text]")
                raw_data = nucleo_mensaje.get_attribute("data-pre-plain-text")
                if raw_data:
                    match = re.search(r']\s(.*?):', raw_data)
                    if match: nombre = match.group(1).strip()

                try:
                    element_texto = nucleo_mensaje.find_element(By.CSS_SELECTOR, "span[data-testid='selectable-text']")
                    texto = element_texto.text
                except:
                    element_texto = nucleo_mensaje.find_element(By.CSS_SELECTOR, "span.selectable-text")
                    texto = element_texto.text
            except:
                try:
                    texto = last_msg_container.text.split('\n')[0]
                except:
                    pass

            if nombre == "Desconocido":
                try:
                    nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
                except:
                    nombre = "Usuario"

            print(f"[ID:{connection_id}] 📩 {nombre}: {texto} [Adj: {tipo_adjunto}]")

            if texto or tipo_adjunto:
                try:
                    # Pasamos connection_id al callback por si necesita contexto (opcional) o la lógica original
                    try:
                        respuesta = callback_inteligencia(texto, nombre, adjunto=tipo_adjunto)
                    except TypeError:
                        respuesta = callback_inteligencia(texto, nombre)

                    if respuesta:
                        print(f"[ID:{connection_id}] 🤖 Respuesta: {respuesta[:30]}...")
                        # IMPORTANTE: Llamada recursiva interna usa el ID
                        # Para evitar deadlock, enviar_mensaje_browser también adquiere el lock,
                        # pero RLock permite reentrada del mismo hilo.
                        enviar_mensaje_browser(connection_id, nombre, respuesta)
                except Exception as e:
                    print(f"❌ Error en callback IA: {e}")

            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
            return True

    except Exception as e:
        print(f"[ID:{connection_id}] ⚠️ Error leve procesando mensaje: {e}")
        return False


def iniciar_bucle_bot(connection_id, callback_ia):
    """
    Inicia el bucle para UN ID específico.
    """
    print(f"[ID:{connection_id}] 🚀 SISTEMA DE BOT INICIADO")

    if not garantizar_sesion_activa(connection_id):
        print(f"[ID:{connection_id}] ❌ Fallo crítico al iniciar sesión.")
        return

    imprimir_resumen_chats(connection_id)

    print(f"[ID:{connection_id}] ✅ ROBOT OPERATIVO Y ESCUCHANDO...")

    iteracion = 0
    try:
        while True:
            iteracion += 1
            if iteracion % 6 == 0:
                print(f"   [ID:{connection_id}] ♻️ Escaneando... ({time.strftime('%H:%M:%S')})")

            procesar_nuevos_mensajes(connection_id, callback_ia)
            time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n[ID:{connection_id}] 🛑 Detenido.")


def obtener_qr_screenshot(connection_id):
    """
    Función para API REST o Vista Web.
    Retorna (base64_image, status_text)
    """
    context = get_session_context(connection_id)
    session_lock = context['lock']

    # Intentamos adquirir el candado NO bloqueante
    if not session_lock.acquire(blocking=False):
        return None, "BOT_OCUPADO"

    try:
        driver = iniciar_navegador(connection_id)
        wait = WebDriverWait(driver, 5)

        # 1. ¿Ya estamos vinculados?
        try:
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            return None, "YA_VINCULADO"
        except:
            pass

        # 2. ¿Hay QR?
        try:
            qr_canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
            time.sleep(1)
            return qr_canvas.screenshot_as_base64, "ESPERANDO_ESCANEO"
        except:
            return None, "CARGANDO"

    except Exception as e:
        print(f"❌ Error obteniendo QR ({connection_id}): {e}")
        return None, "ERROR"
    finally:
        session_lock.release()