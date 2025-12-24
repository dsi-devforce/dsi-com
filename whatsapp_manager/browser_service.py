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

# Configuración de Logging para ver timestamps
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Variable global para mantener la sesión viva (Singleton)
driver_instance = None


def iniciar_navegador():
    """
    Inicia Chromium con persistencia de datos y auto-reparación de perfil.
    """
    global driver_instance

    # 1. Reutilización de driver existente
    if driver_instance is not None:
        try:
            # Check ligero para ver si sigue vivo
            _ = driver_instance.current_url
            return driver_instance
        except:
            print("⚠️ Navegador desconectado o cerrado. Reiniciando...")
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None

    print("🔧 Configurando Chrome (Docker)...")

    # --- RUTAS ---
    chrome_bin = "/usr/bin/chromium"
    driver_path = "/usr/bin/chromedriver"

    # --- GESTIÓN DE PERFIL (Evita el error 'Device busy') ---
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
        # Intento 1: Inicio Normal
        driver = webdriver.Chrome(service=service, options=get_options())
    except Exception as e:
        print(f"⚠️ Perfil corrupto o bloqueado ({e}).")
        print(f"🧹 Limpiando carpeta de sesión: {profile_dir}")

        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                print("✅ Carpeta de sesión eliminada.")
        except Exception as delete_error:
            print(f"❌ Error borrando perfil: {delete_error}")

        print("🔄 Reintentando inicio con perfil limpio...")
        try:
            driver = webdriver.Chrome(service=service, options=get_options())
        except Exception as final_e:
            print(f"❌ ERROR FATAL IRRECUPERABLE: {final_e}")
            raise final_e

    # Ocultar huella de automatización
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    print("🌍 Cargando WhatsApp Web...")
    driver.get("https://web.whatsapp.com")

    driver_instance = driver
    return driver


def validar_sesion_activa():
    """
    Bloqueante. Espera a que la sesión cargue.
    Si hay QR, espera a que el usuario escanee.
    Si hay sesión, IMPRIME LA LISTA DE CHATS para confirmar.
    """
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 60)  # Espera larga inicial

    print("\n🕵️ VALIDANDO ESTADO DE LA SESIÓN...")

    try:
        # Buscamos el panel lateral (Chats) O el Canvas (QR)
        elemento = wait.until(EC.any_of(
            EC.presence_of_element_located((By.ID, "pane-side")),
            EC.presence_of_element_located((By.TAG_NAME, "canvas"))
        ))

        # Caso A: Nos pide QR
        if elemento.tag_name == "canvas":
            print("⚠️ NO HAY SESIÓN INICIADA.")
            print("📸 Generando QR en '/app/qr_login.png'...")
            time.sleep(2)
            driver.save_screenshot("/app/qr_login.png")
            print("👉 Saca la imagen con 'docker cp', escanea y espera...")

            # Esperamos indefinidamente a que aparezca el panel tras escanear
            print("⏳ Esperando escaneo...")
            WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.ID, "pane-side")))
            print("✅ ¡LOGIN DETECTADO!")
            time.sleep(5)  # Dejar que asienten las cookies

        # Caso B: Ya estamos dentro (o acabamos de entrar)
        print("✅ SESIÓN INICIALIZADA CORRECTAMENTE.")

        # --- IMPRESIÓN DE LISTA DE CHATS (Lo que pediste) ---
        print("\n📊 --- VISTA PREVIA DE TUS CHATS ---")
        try:
            # Buscamos los items de la lista
            chats = driver.find_elements(By.XPATH, '//div[@id="pane-side"]//div[@role="listitem"]')

            if not chats:
                print("⚠️ El panel existe pero no veo chats (¿Lista vacía o cargando?)")

            for i, chat in enumerate(chats[:5]):  # Imprimimos solo los primeros 5
                texto = chat.text.replace("\n", " | ")
                print(f"   [{i + 1}] {texto[:60]}...")
        except Exception as e:
            print(f"   (Error visualizando lista: {e})")
        print("--------------------------------------\n")

        return True

    except Exception as e:
        print(f"❌ Error validando sesión: {e}")
        return False


def enviar_mensaje_browser(nombre_contacto, mensaje):
    driver = iniciar_navegador()
    try:
        # Selector robusto para la caja de texto
        xpath_input = '//div[@contenteditable="true"][@role="textbox"]'
        wait = WebDriverWait(driver, 10)
        caja_texto = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))

        caja_texto.click()
        # Escribir con saltos de línea
        for linea in mensaje.split('\n'):
            caja_texto.send_keys(linea)
            caja_texto.send_keys(Keys.SHIFT + Keys.ENTER)

        time.sleep(0.5)
        caja_texto.send_keys(Keys.ENTER)
        time.sleep(1)
        return True
    except Exception as e:
        print(f"⚠️ Error enviando a {nombre_contacto}: {e}")
        return False


def procesar_nuevos_mensajes(callback_inteligencia):
    """
    Escanea indicadores de mensajes no leídos y procesa la respuesta.
    """
    try:
        driver = iniciar_navegador()

        # Estrategia: Buscar "bolitas verdes" (indicadores de unread)
        # Buscamos spans que tengan aria-label con 'unread', 'no leído', o números directos
        xpath_indicadores = (
            '//div[@id="pane-side"]'
            '//span[contains(@aria-label, "unread") or '
            'contains(@aria-label, "no leído") or '
            'contains(@aria-label, "mensaje")]'
        )

        # Filtramos visualmente (a veces WhatsApp deja elementos ocultos)
        # Buscamos elementos que sean veraces indicadores
        posibles_indicadores = driver.find_elements(By.XPATH, xpath_indicadores)

        if not posibles_indicadores:
            return False

        print(f"\n🔔 Detectados {len(posibles_indicadores)} posibles mensajes nuevos.")

        # Procesamos el primero
        indicador = posibles_indicadores[0]

        # Navegamos hacia arriba para encontrar el elemento clicable del chat
        # Usually: span -> div -> div -> div (role=button/row)
        chat_row = indicador.find_element(By.XPATH, './ancestor::div[@role="listitem"]')

        print(f"👉 Abriendo chat...")
        chat_row.click()
        time.sleep(2)  # Esperar carga de mensajes

        # --- LECTURA DEL MENSAJE ---
        # Buscamos el último mensaje entrante
        msgs_in = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
        if not msgs_in:
            print("⚠️ Chat abierto pero no veo mensajes entrantes (¿Audio/Foto?)")
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return False

        ultimo_mensaje = msgs_in[-1]

        # Extracción de texto
        try:
            # Prioridad: Span de texto seleccionable
            texto = ultimo_mensaje.find_element(By.CSS_SELECTOR, "span.selectable-text").text
        except:
            # Fallback: Texto completo burbuja
            texto = ultimo_mensaje.text.split('\n')[0]  # Primera línea suele ser el texto

        # Extracción de nombre
        try:
            nombre = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
        except:
            nombre = "Desconocido"

        print(f"📩 MENSAJE DE {nombre}: {texto}")

        # --- PROCESAMIENTO IA ---
        if texto:
            respuesta = callback_inteligencia(texto, nombre)
            if respuesta:
                print(f"🤖 Enviando respuesta...")
                enviar_mensaje_browser(nombre, respuesta)

        # Salir del chat (resetear foco)
        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1)
        return True

    except Exception as e:
        print(f"⚠️ Error en ciclo de procesamiento: {e}")
        # Intentar volver al home si algo falló
        try:
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except:
            pass
        return False


# --- FUNCIÓN PRINCIPAL DE EJECUCIÓN ---
def iniciar_bucle_bot(callback_ia):
    """
    Función maestra.
    1. Valida sesión (imprime chats).
    2. Inicia el bucle infinito.
    """
    print("🚀 INICIANDO SISTEMA DE BOT WHATSAPP...")

    # 1. Validación inicial
    if not validar_sesion_activa():
        print("❌ No se pudo iniciar la sesión. Revisa el QR.")
        return

    print("✅ SISTEMA LISTO. ESCUCHANDO MENSAJES...")
    print("----------------------------------------")

    # 2. Bucle infinito
    try:
        while True:
            # Latido
            print(".", end="", flush=True)

            # Procesar
            procesar_nuevos_mensajes(callback_ia)

            # Espera
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por usuario.")