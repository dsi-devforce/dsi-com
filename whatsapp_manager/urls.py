from django.urls import path
from . import views

urlpatterns = [
    path('webhook/', views.webhook, name='whatsapp_webhook'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('connect/', views.create_connection, name='create_connection'),
    path('qr/<int:connection_id>/', views.generate_qr, name='connection_qr'),
]
