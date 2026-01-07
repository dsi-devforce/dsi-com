from django.contrib import admin
from django.urls import path, include # Asegúrate de importar include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Las URLs de whatsapp_manager estarán bajo /whatsapp/
    # Ejemplo final: https://tu-dominio.com/whatsapp/webhook/
    path('whatsapp/', include('whatsapp_manager.urls')),
    path('api/v1/', include('api_manager.urls')),

]