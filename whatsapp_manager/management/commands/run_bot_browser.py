import os
import time
from django.core.management.base import BaseCommand
from whatsapp_manager.models import WhatsappConnection

# Importamos las funciones del servicio que acabamos de arreglar
from whatsapp_manager.browser_service import procesar_nuevos_mensajes, iniciar_navegador

# Importamos la lógica de IA (asegúrate de que exista en views.py, si no, usa el dummy abajo)
try:
    from whatsapp_manager.views import ai_agent_logic
except ImportError:
    ai_agent_logic = None


class Command(BaseCommand):
    help = 'Bot de WhatsApp Browser Automation'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('--- 🧹 LIMPIEZA PREVENTIVA ---'))
        # 1. MATAR ZOMBIES: Forzamos el cierre de cualquier Chrome pegado
        # Esto libera el "candado" de la carpeta de sesión.
        os.system("pkill -f chrome")
        os.system("pkill -f chromium")
        time.sleep(2)  # Dar tiempo al sistema para liberar archivos

        self.stdout.write(self.style.SUCCESS('--- 🚀 BOT NAVEGADOR INICIADO ---'))

        # 2. Ahora sí, iniciamos el navegador limpio.
        # Al no haber zombies, podrá leer tu carpeta de sesión correctamente.
        try:
            driver = iniciar_navegador()
            self.stdout.write("✅ Navegador cargado. Verificando sesión...")
            # Pequeña espera para ver si carga chats o pide QR
            time.sleep(5)
            if "pane-side" in driver.page_source:
                self.stdout.write(self.style.SUCCESS("🔓 ¡SESIÓN RECUPERADA EXITOSAMENTE!"))
            else:
                self.stdout.write(self.style.ERROR("🔒 No detecto chats. Posiblemente pida QR."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Alerta: Navegador no inició ({e})'))
        def callback_ia(texto, remitente):
            print(f"📥 MENSAJE RECIBIDO DE {remitente}: {texto}")
            return f"🤖 Recibido: {texto}"
        # 4. Bucle infinito
        try:
            while True:
                # Imprimir un punto para saber que sigue vivo (heartbeat)
                self.stdout.write(".", ending="")
                self.stdout.flush()

                # Escanear
                procesar_nuevos_mensajes(callback_ia)

                # Esperar 5 segundos antes de escanear de nuevo
                time.sleep(5)

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n🛑 Bot detenido manualmente.'))