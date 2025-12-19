import json
import logging
from io import BytesIO

import qrcode
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import ConnectionForm
from .models import WhatsappConnection

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    """
    Webhook principal para WhatsApp.
    GET: Verificación del token con Meta.
    POST: Recepción de mensajes.
    """

    # 1. VERIFICACIÓN DEL WEBHOOK (Meta valida tu URL)
    if request.method == "GET":
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe':
                # Buscamos si existe alguna conexión con ese verify_token
                # NOTA: En un escenario real con muchos clientes, podrías necesitar una lógica más específica
                # para saber qué cliente está intentando verificar, o usar un token global.
                # Aquí validamos si el token existe en CUALQUIER conexión activa.
                exists = WhatsappConnection.objects.filter(verify_token=token, is_active=True).exists()

                if exists:
                    logger.info("Webhook verificado correctamente.")
                    return HttpResponse(challenge, status=200)
                else:
                    logger.warning("Intento de verificación con token inválido.")
                    return HttpResponse("Token inválido", status=403)
        return HttpResponse("Error de verificación", status=403)

    # 2. RECEPCIÓN DE MENSAJES (POST)
    elif request.method == "POST":
        try:
            body = json.loads(request.body.decode('utf-8'))
            logger.info(f"Payload recibido: {body}")

            # Verificar si es un evento de mensaje de WhatsApp
            if 'object' in body and body['object'] == 'whatsapp_business_account':
                entries = body.get('entry', [])
                for entry in entries:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})

                        # Extraer ID del número que recibe el mensaje (nuestro cliente)
                        metadata = value.get('metadata', {})
                        phone_number_id = metadata.get('phone_number_id')

                        if phone_number_id:
                            # Buscar la conexión correspondiente
                            connection = WhatsappConnection.objects.filter(phone_number_id=phone_number_id,
                                                                           is_active=True).first()

                            if connection:
                                messages = value.get('messages', [])
                                for message in messages:
                                    # AQUÍ ES DONDE DELEGARÍAS AL CHATBOT
                                    logger.info(f"Mensaje recibido para {connection.name}: {message}")
                                    # procesar_mensaje(connection, message) 
                            else:
                                logger.warning(f"Recibido mensaje para ID desconocido: {phone_number_id}")

            return JsonResponse({'status': 'ok'}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error procesando webhook: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def dashboard(request):
    connections = WhatsappConnection.objects.all()
    return render(request, 'whatsapp_manager/dashboard.html', {'connections': connections})


def create_connection(request):
    if request.method == 'POST':
        form = ConnectionForm(request.POST)
        if form.is_valid():
            connection = form.save()
            messages.success(request, f'Conexión "{connection.name}" creada exitosamente.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        # Sugerir un verify_token aleatorio o por defecto para facilitar
        form = ConnectionForm(initial={'verify_token': 'mi_token_seguro_123'})

    return render(request, 'whatsapp_manager/create_connection.html', {'form': form})


def generate_qr(request, connection_id):
    """
    Genera una imagen QR PNG para una conexión específica.
    El QR apunta a https://wa.me/<numero>
    """
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)

    if not connection.display_phone_number:
        return HttpResponse("Número de teléfono no configurado para esta conexión", status=404)

    # Crear el enlace de WhatsApp
    wa_link = f"https://wa.me/{connection.display_phone_number}"

    # Generar el QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(wa_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Guardar en memoria (buffer) en lugar de disco
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    return HttpResponse(buffer.getvalue(), content_type="image/png")