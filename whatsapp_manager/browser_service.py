import json
import shutil
import os
import time
import logging
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import threading

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Singleton del driver
driver_instance = None
driver_lock = threading.RLock()

def iniciar_navegador():
    """
    Inicia el navegador con persistencia y auto-recuperación ante fallos.
    """
    global driver_instance

    if driver_instance is not None:
        try:
            _ = driver_instance.current_url
            return driver_instance
        except:
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None

    print("🔧 Iniciando motor de Chrome...")
    chrome_bin = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"
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
        driver = webdriver.Chrome(service=service, options=get_options())
    except Exception as e:
        print(f"⚠️ Perfil bloqueado o corrupto. Limpiando...")
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
        except:
            pass

        print("🔄 Reiniciando limpio...")
        driver = webdriver.Chrome(service=service, options=get_options())

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.get("https://web.whatsapp.com")
    driver_instance = driver
    return driver


# --- LÓGICA DE SECUENCIA INTELIGENTE ---

def garantizar_sesion_activa():
    """
    Esta función NO RETORNA hasta que el usuario esté logueado.
    Si falta QR: Lo genera, espera y detecta el login automáticamente.
    Si ya hay login: Retorna de inmediato.
    """
    with driver_lock:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 20)

    print("\n🕵️ 1. VERIFICANDO ESTADO DE SESIÓN...")
    print("   ↳ Esperando a que cargue la interfaz de WhatsApp Web...")

    try:
        # Esperamos a que cargue ALGO (QR o Chat)
        # Aumentamos un poco el timeout inicial por si la red es lenta
        elemento = WebDriverWait(driver, 30).until(EC.any_of(
            EC.presence_of_element_located((By.ID, "pane-side")),  # Panel de chats (Login OK)
            EC.presence_of_element_located((By.TAG_NAME, "canvas")),  # Lienzo del QR (Falta Login)
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-ref]"))  # QR contenedor (Alternativo)
        ))

        # ESCENARIO A: YA ESTAMOS DENTRO (Detectamos el panel lateral de chats)
        if elemento.get_attribute("id") == "pane-side":
            print("   ✅ ¡ÉXITO! Panel de chats detectado.")
            print("   ✅ Sesión recuperada correctamente. Iniciando robot.")
            return True

        # ESCENARIO B: NECESITAMOS ESCANEAR (Detectamos el QR)
        print("   ⚠️ No se detectó sesión activa.")
        print("   👀 Se detectó el código QR en pantalla.")
        print("   📸 Generando captura del QR en '/app/qr_login.png'...")

        time.sleep(1)  # Pequeña pausa para asegurar renderizado completo del QR
        driver.save_screenshot("/app/qr_login.png")

        print("   💾 Captura guardada.")
        print("   👉 ACCIÓN REQUERIDA: Escanea el código QR desde tu celular.")
        print("   ⏳ El sistema está esperando a que el QR desaparezca y carguen los chats...")

        # Aquí el código SE PAUSA hasta que detecte que escaneaste
        # Usamos un bucle con feedback visual para no dejar la consola "congelada" sin saber qué pasa
        start_time = time.time()
        timeout = 300  # 5 minutos

        while time.time() - start_time < timeout:
            try:
                # Intentamos buscar el panel de chats brevemente (1 segundo)
                WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, "pane-side")))
                break  # ¡Lo encontró! Salimos del bucle
            except:
                # Si no lo encuentra, imprime un punto y sigue esperando
                print(".", end="", flush=True)
                time.sleep(2)

        # Verificamos si salió por timeout o por éxito
        if time.time() - start_time >= timeout:
            print("\n   ❌ Tiempo de espera agotado (5 min). Reinicia el proceso.")
            return False

        print("\n   🎉 ¡VINCULACIÓN DETECTADA!")
        print("   📥 Descargando base de datos de chats inicial...")
        print("   💾 Guardando cookies y sesión localmente...")

        # CRÍTICO: Esperar a que WhatsApp termine de indexar y guardar en IndexedDB
        for i in range(5, 0, -1):
            print(f"   ⏳ Estabilizando sesión en {i}s...", end="\r")
            time.sleep(1)
        print("\n   ✅ Sesión estabilizada y guardada.")

        return True

    except Exception as e:
        print(f"\n❌ Error fatal verificando sesión: {e}")
        # Intentamos sacar un screenshot del error para debug
        try:
            driver.save_screenshot("/app/debug_error_sesion.png")
            print("   📸 Se guardó una captura del error en '/app/debug_error_sesion.png'")
        except:
            pass
        return False

def imprimir_resumen_chats():
    """Imprime los últimos chats para confirmar visualmente al usuario"""
    with driver_lock:
        driver = iniciar_navegador()
        print("\n📊 --- CHATS ACTIVOS ---")
        try:
            chats = driver.find_elements(By.XPATH, '//div[@id="pane-side"]//div[@role="listitem"]')
            for i, chat in enumerate(chats[:3]):
                print(f"   [{i + 1}] {chat.text.replace(chr(10), ' | ')[:50]}...")
        except:
            print("   (No se pudieron leer los textos de los chats)")
        print("-------------------------\n")

def enviar_mensaje_browser(nombre_contacto, mensaje):
        with driver_lock:
            driver = iniciar_navegador()
            print(f"   ⌨️ Intentando escribir a: {nombre_contacto}...")
            try:
                # 1. BUSQUEDA DEL INPUT (CORREGIDO)
                # CRÍTICO: Usamos //footer para asegurarnos de que es la caja de chat
                # y NO el buscador de contactos (que está en el panel lateral).
                xpath_input = '//footer//div[@contenteditable="true"][@role="textbox"]'

                wait = WebDriverWait(driver, 10)
                try:
                    caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))
                except:
                    print("   ⚠️ No se encontró el input en el footer. Intentando selectores alternativos...")
                    # Fallback: Buscamos por atributos específicos de la caja de mensaje (data-tab suele ser 10)
                    # Esto funciona independiente del idioma (Type a message / Escribe un mensaje)
                    xpath_alt = '//div[@contenteditable="true"][@data-tab]'
                    caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_alt)))

                # --- DIAGNÓSTICO RÁPIDO ---
                label = caja_texto.get_attribute('aria-label') or "Sin label"
                print(f"   ✅ Elemento seleccionado: {caja_texto.tag_name} (Label: {label})")
                # --------------------------

                driver.execute_script("arguments[0].focus();", caja_texto)
                time.sleep(0.2)

                # 3. ESCRITURA NUCLEAR (Dispara todos los eventos posibles)
                # Esta función JS simula que el usuario escribió, disparando eventos que React escucha.
                script_escritura = """
                               var element = arguments[0];
                               var text = arguments[1];

                               // Método 1: execCommand (Legacy pero efectivo)
                               document.execCommand('insertText', false, text);

                               // Método 2: Manipulación directa + Eventos (Fallback moderno)
                               if (element.textContent !== text) {
                                   element.innerHTML = text.replace(/\\n/g, '<br>');

                                   var eventInput = new Event('input', { bubbles: true });
                                   element.dispatchEvent(eventInput);

                                   var eventChange = new Event('change', { bubbles: true });
                                   element.dispatchEvent(eventChange);
                               }
                               """
                driver.execute_script(script_escritura, caja_texto, mensaje)

                print("   ⌨️ Texto inyectado. Esperando validación de UI...")
                time.sleep(1)  # Esperamos a que el icono de Micrófono cambie a Avión

                # 4. ENVÍO (Click en el botón que APARECIÓ)
                try:
                    # Buscamos el botón SEND explícitamente.
                    # El span data-icon="send" solo aparece si hay texto valido.
                    boton_enviar = driver.find_element(By.XPATH, '//span[@data-icon="send"]/ancestor::button')
                    boton_enviar.click()
                    print(f"   👉 Click en botón 'Enviar' (Avión) realizado.")
                except:
                    # Si no aparece el avión, intentamos Enter como fallback
                    print(f"   ⚠️ No apareció el botón de enviar. Intentando Enter...")
                    caja_texto.send_keys(Keys.ENTER)

                print(f"   📤 ¡Mensaje enviado exitosamente!")
                return True

            except Exception as e:
                print(f"   ❌ ERROR enviando mensaje: {e}")
                return False



def procesar_nuevos_mensajes(callback_inteligencia):
        try:
            with driver_lock:
                driver = iniciar_navegador()
                wait = WebDriverWait(driver, 5)

                # Busca burbujas verdes (indicadores de no leídos)
                # Usamos una estrategia más amplia para capturar el indicador
                xpath_indicadores = '//div[@id="pane-side"]//span[contains(@aria-label, "unread") or contains(@aria-label, "no leído")]'

                # Buscamos elementos pero sin esperar demasiado para no bloquear
                indicadores = driver.find_elements(By.XPATH, xpath_indicadores)

                if not indicadores:
                    return False

                print(f"\n🔔 Mensaje nuevo detectado ({len(indicadores)} pendientes).")
                indicador = indicadores[0]

                # --- CORRECCIÓN DE ESTABILIDAD ---
                # Intentamos subir por el árbol DOM hasta encontrar el elemento clickeable del chat
                # En lugar de asumir que es el padre directo, buscamos el ancestro con role="listitem"
                try:
                    chat_element = indicador.find_element(By.XPATH, './ancestor::div[@role="listitem"]')
                except:
                    # Fallback: Si no encuentra listitem, intenta hacer click en el indicador mismo
                    # (a veces funciona si el indicador absorbe el click)
                    print("⚠️ No se encontró el contenedor 'listitem', intentando click directo...")
                    chat_element = indicador

                # Scroll al elemento para asegurar que sea visible y clickeable
                driver.execute_script("arguments[0].scrollIntoView(true);", chat_element)
                time.sleep(0.5)  # Pequeña pausa visual

                try:
                    chat_element.click()
                except Exception as e:
                    # Si el click normal falla, usamos Javascript (infalible)
                    print(f"⚠️ Click normal falló, forzando click JS...")
                    driver.execute_script("arguments[0].click();", chat_element)

                time.sleep(2)  # Esperar a que abra el chat

                # Leer mensajes
                # Buscamos burbujas de mensaje entrante
                #msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in span.selectable-text")

                #if not msgs:
                    # Intento alternativo por si cambió la clase
                #    msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in")

                #if not msgs:
                #    print("❌ No pude leer el texto del mensaje.")
                #    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                #    return False

                # Tomamos el texto del último mensaje
                #texto = msgs[-1].text.split('\n')[0]

                # Intentamos sacar el nombre
                #try:
                #    nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
                #except:
                #    nombre = "Usuario"

                #print(f"📩 {nombre}: {texto}")

                #if texto:
                #    respuesta = callback_inteligencia(texto, nombre)
                msgs_containers = driver.find_elements(By.CSS_SELECTOR, "div.message-in")

                if not msgs_containers:
                    print("❌ No se encontraron mensajes entrantes visibles.")
                    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    return False

                # Trabajamos EXCLUSIVAMENTE sobre el último contenedor de mensaje
                last_msg_container = msgs_containers[-1]

                # 1. Extracción del TEXTO (Scoped)
                try:
                    # Buscamos el span de texto SOLO dentro del último contenedor
                    element_texto = last_msg_container.find_element(By.CSS_SELECTOR, "span.selectable-text")
                    texto = element_texto.text
                except:
                    # Fallback: Si no hay selectable-text (ej: solo emojis), tomamos el texto crudo
                    texto = last_msg_container.text.split('\n')[0]

                # 2. Extracción del NOMBRE (Soporte para Grupos)
                nombre = "Desconocido"
                try:
                    # WhatsApp incluye un atributo 'data-pre-plain-text' en el div 'copyable-text'
                    # Formato típico: "[10:30, 01/01/2024] Juan Perez: "
                    # Esto identifica al remitente real incluso en grupos.
                    elemento_meta = last_msg_container.find_element(By.CSS_SELECTOR, "div[data-pre-plain-text]")
                    raw_data = elemento_meta.get_attribute("data-pre-plain-text")

                    if raw_data:
                        # Usamos Regex para extraer lo que está entre ']' y ':'
                        match = re.search(r']\s(.*?):', raw_data)
                        if match:
                            nombre = match.group(1).strip()
                except Exception:
                    pass

                # Fallback para chat 1 a 1 (si no se pudo sacar de la metadata)
                if nombre == "Desconocido":
                    try:
                        # En chat privado, el nombre del header es válido
                        nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
                    except:
                        nombre = "Usuario"

                print(f"📩 {nombre}: {texto}")

                if texto:
                    respuesta = callback_inteligencia(texto, nombre)

                    if respuesta:
                        print(f"🤖 Respuesta generada: {respuesta[:30]}...")
                        enviar_mensaje_browser(nombre, respuesta)
                    else:
                        print("😶 El cerebro decidió no responder.")

                # Salimos del chat para volver a la lista (Tecla ESC)
                webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()

                # Pausa para que la interfaz vuelva a la lista
                time.sleep(1)
                return True

        except Exception as e:
            print(f"⚠️ Error leve procesando mensaje: {e}")
            return False


def iniciar_bucle_bot(callback_ia):
    """
    Esta función encapsula TODO el proceso:
    """
    print("🚀 SISTEMA DE BOT INICIADO")

    # 1. Fase de Garantía de Sesión
    if not garantizar_sesion_activa():
        print("❌ Fallo crítico al intentar iniciar sesión.")
        return

    # 2. Confirmación visual
    imprimir_resumen_chats()

    # 3. Fase de Ejecución (Bucle Infinito)
    print("✅ ROBOT OPERATIVO Y ESCUCHANDO...")
    print("   (Presiona Ctrl+C en la terminal para detener)")

    iteracion = 0
    try:
        while True:
            # Feedback visual de que el proceso sigue vivo
            iteracion += 1
            if iteracion % 6 == 0:  # Imprime cada ~30 segundos para no saturar
                print(f"   ♻️ Escaneando mensajes... ({time.strftime('%H:%M:%S')})")

            procesar_nuevos_mensajes(callback_ia)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Detenido por usuario.")

def obtener_qr_screenshot():
    """
    Función usada por la VISTA WEB (views.py) para obtener el QR.
    Retorna (base64_image, status_text)
    """
    # Intentamos adquirir el candado pero SIN BLOQUEAR.
    # Si el bot está trabajando (escribiendo/leyendo), le decimos a la web que espere.
    if not driver_lock.acquire(blocking=False):
       return None, "BOT_OCUPADO"

    try:
        driver = iniciar_navegador()
        # Reducimos el wait para que la web sea ágil
        wait = WebDriverWait(driver, 5)

        # 1. ¿Ya estamos vinculados?
        try:
        # Buscamos el panel lateral de chats
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))

        # --- CORRECCIÓN CRÍTICA ---
        # Eliminamos garantizar_sesion_activa() de aquí.
        # La vista web solo debe detectar el estado, NO debe ejecutar la lógica
        # de estabilización (sleeps) ni impresiones de consola del bot.
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
    finally:
         driver_lock.release()
