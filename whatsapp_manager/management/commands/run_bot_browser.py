import time
from django.core.management.base import BaseCommand
from whatsapp_manager.browser_service import procesar_nuevos_mensajes, iniciar_navegador
from whatsapp_manager.views import ai_agent_logic
# Necesitamos una conexión "dummy" para pasarle a ai_agent_logic o adaptarla
from whatsapp_manager.models import WhatsappConnection


class Command(BaseCommand):
    help = 'Ejecuta el bot de WhatsApp basado en navegador (Selenium)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando navegador y bot...'))

        # Aseguramos que el navegador esté abierto
        iniciar_navegador()

        self.stdout.write("Escuchando mensajes nuevos... (Presiona Ctrl+C para detener)")

        # Obtenemos una conexión por defecto para la lógica del agente
        # (Asumimos la primera activa para sacar la configuración del Chatbot)
        conexion_dummy = WhatsappConnection.objects.filter(is_active=True).first()

        if not conexion_dummy:
            self.stdout.write(
                self.style.WARNING("No hay conexiones configuradas en BD. El bot usará configuración default."))

        # Función envoltorio para adaptar tu ai_agent_logic existente
        def adaptador_ia(texto, remitente):
            # Usamos tu función 'cerebro' existente en views.py
            # Le pasamos el objeto conexión para que sepa si actuar como Ventas o Soporte
            return ai_agent_logic(conexion_dummy, texto, remitente)

        try:
            while True:
                # El loop principal
                procesar_nuevos_mensajes(adaptador_ia)

                # Esperar 2 segundos antes de volver a mirar para no saturar CPU
                time.sleep(2)

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('Bot detenido.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fatal: {e}'))