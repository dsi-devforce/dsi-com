from django.db import models

# Create your models here.
class ApiClient(models.Model):
    """
    Representa al cliente externo o sistema que consume la API.
    Este modelo servirá para validar el 'iss' (issuer) o 'sub' (subject) del JWT.
    """
    name = models.CharField(max_length=100, help_text="Nombre del cliente (ej: CRM Externo, App Móvil)")
    api_key = models.CharField(max_length=255, unique=True, help_text="Identificador único (Subject) esperado en el JWT")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name