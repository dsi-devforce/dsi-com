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
import threading

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Singleton del driver
driver_instance = None
driver_lock = threading.Lock()

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
        except:
            return False


def procesar_nuevos_mensajes(callback_inteligencia):
    try:
        with driver_lock:
            driver = iniciar_navegador()

            # Busca burbujas verdes
            xpath_indicadores = '//div[@id="pane-side"]//span[contains(@aria-label, "unread") or contains(@aria-label, "no leído")]'
            indicadores = driver.find_elements(By.XPATH, xpath_indicadores)

            if not indicadores: return False

            print(f"\n🔔 Mensaje nuevo detectado.")
            indicador = indicadores[0]
            # Click en el chat
            indicador.find_element(By.XPATH, './ancestor::div[@role="listitem"]').click()
            time.sleep(2)

            # Leer
            msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
            if not msgs: return False

            texto = msgs[-1].text.split('\n')[0]
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

            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return True

    except Exception as e:
        print(f"⚠️ Error leve: {e}")
        return False


# --- FUNCIÓN MAESTRA (LA QUE PIDE TU LÓGICA) ---
def iniciar_bucle_bot(callback_ia):
    """
    Esta función encapsula TODO el proceso:
    1. Arranca Chrome.
    2. Si no hay sesión, ESPERA a que escanees.
    3. Una vez logueado, entra al bucle infinito.
    """
    print("🚀 SISTEMA DE BOT INICIADO")

    # 1. Fase de Garantía de Sesión (Bloqueante hasta tener éxito)
    if not garantizar_sesion_activa():
        print("❌ Fallo crítico al intentar iniciar sesión.")
        return

    # 2. Confirmación visual
    imprimir_resumen_chats()

    # 3. Fase de Ejecución (Bucle Infinito)
    print("✅ ROBOT OPERATIVO Y ESCUCHANDO...")
    try:
        while True:
            print(".", end="", flush=True)
            procesar_nuevos_mensajes(callback_ia)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Detenido.")

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
