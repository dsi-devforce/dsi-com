from django.db import models


# ... existing code ...
class Chatbot(models.Model):
    name = models.CharField(max_length=100, help_text="Nombre interno del bot (ej: Ventas, Soporte)")
    description = models.TextField(blank=True)
    # Este campo servirá para que tu código sepa qué lógica ejecutar
    slug = models.SlugField(unique=True, help_text="Identificador único para usar en el código (ej: bot_ventas)")

    def __str__(self):
        return self.name


class WhatsappConnection(models.Model):
    name = models.CharField(max_length=100, help_text="Nombre identificativo de la conexión")
    # ... existing code ...
    access_token = models.TextField(help_text="Token de acceso permanente o de larga duración")
    phone_number_id = models.CharField(max_length=50, unique=True,
                                       help_text="ID del número en Meta/WhatsApp Business API")
    # Nueva relación: Asignamos un Chatbot a esta conexión
    chatbot = models.ForeignKey(Chatbot, on_delete=models.SET_NULL, null=True, blank=True, related_name='connections',
                                help_text="El chatbot que gestionará esta línea")
    # Campo extra de seguridad para el Webhook de Meta
    verify_token = models.CharField(max_length=100, default='token_por_defecto',
                                    help_text="Token de verificación para configurar en Meta")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    display_phone_number = models.CharField(max_length=20, blank=True, null=True,
                                            help_text="Número real con código de país (sin +) para generar el enlace wa.me")


class WebhookLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()  # Guarda el JSON completo tal cual llega
    headers = models.JSONField(default=dict, blank=True) # Opcional: para ver headers

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Log {self.id} - {self.created_at}"



