from django.urls import path
from . import views

urlpatterns = [
    path('webhook/', views.webhook, name='whatsapp_webhook'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('connect/', views.create_connection, name='create_connection'),
    path('qr/<int:connection_id>/', views.generate_qr, name='connection_qr'),
    path('chat/<int:connection_id>/', views.chat_interface, name='chat_interface'),
    path('chat/<int:connection_id>/send/', views.send_message_ui, name='send_message_ui'),
    path('inspector/', views.webhook_inspector, name='webhook_inspector'),
    path('inspector/api/', views.get_latest_logs, name='api_webhook_logs'),
    path('simulator/', views.webhook_simulator, name='webhook_simulator'),
    path('browser/vincular/', views.vincular_navegador, name='vincular_navegador'),
    path('iniciar-bot/', views.iniciar_bot_background, name='start_bot'),
    path('estado-bot/', views.estado_bot, name='status_bot'),
]
