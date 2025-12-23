import time
from django.core.management.base import BaseCommand
from whatsapp_manager.browser_service import procesar_nuevos_mensajes, iniciar_navegador
from whatsapp_manager.views import ai_agent_logic
# Necesitamos una conexión "dummy" para pasarle a ai_agent_logic o adaptarla
from whatsapp_manager.models import WhatsappConnection

import time
from django.core.management.base import BaseCommand
from whatsapp_manager.browser_service import procesar_nuevos_mensajes, iniciar_navegador
# Importamos la lógica del cerebro que creamos en views.py
from whatsapp_manager.views import ai_agent_logic
# Importamos el modelo para obtener la configuración del bot (Ventas/Soporte)
from whatsapp_manager.models import WhatsappConnection


class Command(BaseCommand):
    help = 'Ejecuta el bot de WhatsApp conectado a Ollama con Logs en vivo'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- 🤖 INICIANDO BOT CON IA (OLLAMA) ---'))

        # 1. Obtener una conexión de referencia
        # Necesitamos esto porque ai_agent_logic requiere un objeto 'connection'
        # para saber si actuar como Bot de Ventas o Soporte.
        conexion_activa = WhatsappConnection.objects.filter(is_active=True).first()

        if not conexion_activa:
            self.stdout.write(self.style.WARNING("⚠️ No hay conexiones en BD. Se usará una configuración genérica."))
            # Creamos un objeto dummy en memoria si no hay nada en BD para que no falle
            conexion_activa = WhatsappConnection(name="Dummy", display_phone_number="000")

        self.stdout.write(
            f"🧠 Cerebro configurado para: {conexion_activa.chatbot if conexion_activa.chatbot else 'Default'}")

        # 2. Iniciar Selenium
        iniciar_navegador()

        # 3. Función Wrapper para Loguear la Interacción
        def puente_con_logs(texto_usuario, nombre_remitente):
            # A) Imprimir lo que llega
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n📨 MENSAJE RECIBIDO de {nombre_remitente}:"))
            self.stdout.write(f"   \"{texto_usuario}\"")
            self.stdout.write("   Thinking... 🤔")

            try:
                # B) Llamar al Cerebro (Views.py -> Ollama/Tools)
                respuesta_ia = ai_agent_logic(conexion_activa, texto_usuario, nombre_remitente)

                # C) Imprimir lo que sale
                self.stdout.write(self.style.SUCCESS(f"🤖 RESPUESTA GENERADA:"))
                self.stdout.write(f"   \"{respuesta_ia}\"")
                self.stdout.write("-" * 40)

                return respuesta_ia

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error en el cerebro de IA: {e}"))
                return "Lo siento, tuve un error interno procesando tu mensaje."

        # 4. Bucle Infinito
        try:
            while True:
                # Feedback visual minimalista para saber que sigue vivo
                self.stdout.write(".", ending='')
                self.stdout.flush()

                # Ejecutar escaneo
                procesar_nuevos_mensajes(puente_con_logs)

                time.sleep(2)  # Espera 2 segundos

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n\n🛑 Bot detenido manualmente.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n\n❌ Error fatal en el loop: {e}'))