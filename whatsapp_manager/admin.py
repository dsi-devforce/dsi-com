from django.contrib import admin
from .models import WhatsappConnection, Chatbot

@admin.register(Chatbot)
class ChatbotAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(WhatsappConnection)
class WhatsappConnectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number_id', 'chatbot', 'is_active', 'created_at')
    search_fields = ('name', 'phone_number_id')
    list_filter = ('is_active', 'chatbot')
    # Opcional: para editar el chatbot directamente en la lista
    list_editable = ('chatbot', 'is_active')