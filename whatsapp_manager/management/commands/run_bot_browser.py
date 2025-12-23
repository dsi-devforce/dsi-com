import time
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from selenium.webdriver.common.by import By
from whatsapp_manager.browser_service import iniciar_navegador, enviar_mensaje_browser


class Command(BaseCommand):
    help = 'Modo Diagnóstico: Verifica qué ve el bot realmente'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('--- INICIANDO MODO DIAGNÓSTICO ---'))

        driver = iniciar_navegador()
        time.sleep(5)  # Esperar carga inicial

        # 1. DIAGNÓSTICO DE SESIÓN
        titulo = driver.title
        self.stdout.write(f"1. Título de la página: '{titulo}'")

        if "WhatsApp" not in titulo:
            self.stdout.write(self.style.ERROR("❌ NO parece estar en WhatsApp Web. Revisa la URL."))

        # 2. CAPTURA DE PANTALLA (DEBUG VISUAL)
        try:
            ruta_img = os.path.join(settings.BASE_DIR, 'debug_view.png')
            driver.save_screenshot(ruta_img)
            self.stdout.write(self.style.SUCCESS(f"📸 Captura guardada en: {ruta_img}"))
            self.stdout.write("   (Descarga esa imagen para ver si pide QR o si ya estás dentro)")
        except Exception as e:
            self.stdout.write(f"Error guardando imagen: {e}")

        # 3. PRUEBA DE SELECTORES (Busca panel lateral)
        try:
            panel_lateral = driver.find_element(By.ID, "pane-side")
            self.stdout.write(self.style.SUCCESS("✅ Panel lateral encontrado (Sesión iniciada correctamente)"))

            # Imprimir los primeros 200 caracteres de texto que ve en el panel
            texto_visible = panel_lateral.text[:200].replace('\n', ' | ')
            self.stdout.write(f"👀 Texto visible en lista chats: {texto_visible}...")

            # 4. PRUEBA DE ESCRITURA FORZADA
            # Vamos a intentar hacer clic en el PRIMER chat de la lista (sea cual sea) y escribir.
            self.stdout.write("\nintentando abrir el primer chat visible...")

            chats = panel_lateral.find_elements(By.XPATH, "./div/div/div/div")
            if chats:
                primer_chat = chats[0]
                primer_chat.click()
                time.sleep(2)

                self.stdout.write("💬 Intentando escribir 'Hola prueba sistema'...")
                exito = enviar_mensaje_browser("Test", "Hola prueba sistema - Diagnóstico")

                if exito:
                    self.stdout.write(self.style.SUCCESS("✅ ¡ESCRITURA EXITOSA! El bot puede escribir."))
                else:
                    self.stdout.write(self.style.ERROR("❌ Falló la escritura."))
            else:
                self.stdout.write(self.style.ERROR("❌ No encontré ningún chat en la lista."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error crítico buscando elementos: {e}"))
            self.stdout.write("   Posiblemente sigues en la pantalla de código QR.")

        self.stdout.write(self.style.WARNING('\n--- FIN DEL DIAGNÓSTICO ---'))