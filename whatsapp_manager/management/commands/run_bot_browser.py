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
        self.stdout.write(self.style.SUCCESS('--- 🚀 BOT NAVEGADOR INICIADO ---'))
        self.stdout.write('Esperando escaneo de QR o mensajes...')

        # 1. Intentar abrir navegador preventivamente
        try:
            iniciar_navegador()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Alerta: Navegador no inició aún ({e})'))

        # 2. Definir conexión activa (Dummy si no hay BD aún)
        conexion_activa = WhatsappConnection.objects.filter(is_active=True).first()
        if not conexion_activa:
            # Creamos un objeto en memoria si no hay nada en la DB para evitar errores
            conexion_activa = WhatsappConnection(name="Default", display_phone_number="000")

        # 3. Callback interno para conectar con la IA
        def callback_ia(texto, remitente):
            if not texto: return None

            self.stdout.write(f"🧠 Procesando mensaje de {remitente}...")

            if ai_agent_logic:
                try:
                    return ai_agent_logic(conexion_activa, texto, remitente)
                except Exception as e:
                    print(f"Error en IA Logic: {e}")
                    return "Lo siento, tuve un error interno."
            else:
                # Fallback si no pudimos importar views.py
                return f"Echo: {texto}"

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