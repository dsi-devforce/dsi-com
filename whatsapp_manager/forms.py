from django import forms
from .models import WhatsappConnection, Chatbot

class ConnectionForm(forms.ModelForm):
    class Meta:
        model = WhatsappConnection
        fields = ['name', 'phone_number_id', 'access_token', 'chatbot', 'verify_token']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: WhatsApp Ventas'}),
            'phone_number_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ID del número (Meta)'}),
            'access_token': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Pegar Access Token aquí'}),
            'chatbot': forms.Select(attrs={'class': 'form-select'}),
            'verify_token': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Crea una contraseña para el Webhook'}),
            'display_phone_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ej: 52155... (con código país)'}),
        }
        labels = {
            'name': 'Nombre de la Conexión',
            'phone_number_id': 'Phone Number ID',
            'access_token': 'Token de Acceso (API)',
            'verify_token': 'Token de Verificación (Webhook)',
        }