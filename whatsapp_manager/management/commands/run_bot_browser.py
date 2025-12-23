import time
from django.core.management.base import BaseCommand
from whatsapp_manager.browser_service import procesar_nuevos_mensajes, iniciar_navegador
from whatsapp_manager.views import ai_agent_logic
from whatsapp_manager.models import WhatsappConnection


class Command(BaseCommand):
    help = 'Bot de WhatsApp con IA (Ollama) - Modo Producción'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- 🚀 BOT INICIADO (Escuchando...) ---'))

        # Configuración Dummy para que no falle la lógica si no hay DB
        conexion_activa = WhatsappConnection.objects.filter(is_active=True).first()
        if not conexion_activa:
            conexion_activa = WhatsappConnection(name="Default", display_phone_number="000")

        try:
            iniciar_navegador()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error al iniciar navegador: {e}'))
            return

        # Función puente
        def callback_ia(texto, remitente):
            # Filtro de seguridad: No responder a mensajes propios o vacíos
            if not texto or len(texto) < 2: return None

            try:
                # Llamamos a tu lógica de IA definida en views.py
                return ai_agent_logic(conexion_activa, texto, remitente)
            except Exception as e:
                return f"Error IA: {e}"

        try:
            while True:
                # El punto indica "heartbeat" (latido)
                self.stdout.write(".", ending='')
                self.stdout.flush()

                procesar_nuevos_mensajes(callback_ia)

                time.sleep(5)  # Revisar cada 5 segundos

        except KeyboardInterrupt:
            self.stdout.write('\n🛑 Detenido.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error fatal: {e}'))