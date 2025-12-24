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

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Singleton del driver
driver_instance = None


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
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 20)

    print("\n🕵️ 1. VERIFICANDO ESTADO DE SESIÓN...")

    try:
        # Esperamos a que cargue ALGO (QR o Chat)
        elemento = wait.until(EC.any_of(
            EC.presence_of_element_located((By.ID, "pane-side")),
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        ))

        # ESCENARIO A: YA ESTAMOS DENTRO
        if elemento.get_attribute("id") == "pane-side":
            print("✅ Sesión encontrada. Iniciando robot.")
            return True

        # ESCENARIO B: NECESITAMOS ESCANEAR (Secuencia de espera)
        print("⚠️ No se detectó sesión. Se requiere vinculación.")
        print("📸 Generando QR en '/app/qr_login.png'...")
        time.sleep(1)
        driver.save_screenshot("/app/qr_login.png")
        print("👉 EJECUTA EN OTRA TERMINAL: docker cp com-web-1:/app/qr_login.png ./qr_login.png")
        print("⏳ Esperando a que escanees el código...")

        # Aquí el código SE PAUSA hasta que detecte que escaneaste
        # Timeout largo de 5 minutos (300 segundos)
        WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.ID, "pane-side")))

        print("\n🎉 ¡VINCULACIÓN DETECTADA!")
        print("💾 Guardando cookies y sesión en disco...")
        time.sleep(5)  # CRÍTICO: Esperar a que WhatsApp guarde los datos localmente
        return True

    except Exception as e:
        print(f"❌ Error fatal verificando sesión: {e}")
        return False


def imprimir_resumen_chats():
    """Imprime los últimos chats para confirmar visualmente al usuario"""
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
    try:
        driver = iniciar_navegador()
        wait = WebDriverWait(driver, 15)

        # 1. ¿Ya estamos vinculados?
        try:
            # Buscamos el panel lateral de chats
            wait.until(EC.presence_of_element_located((By.ID, "pane-side")))
            garantizar_sesion_activa()
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
