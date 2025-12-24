from django.core.management.base import BaseCommand
from whatsapp_manager.browser_service import iniciar_bucle_bot

class Command(BaseCommand):
    help = 'Disparador del Bot'

    def handle(self, *args, **options):
        # Callback simple
        def cerebro(texto, nombre):
            return f"🤖 Recibido: {texto}"

        # ESTA FUNCIÓN HACE TODO EL TRABAJO AUTOMÁTICAMENTE
        iniciar_bucle_bot(cerebro)