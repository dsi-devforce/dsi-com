import json
import logging
import os
import mimetypes
from io import BytesIO

import requests
import qrcode
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from .forms import ConnectionForm
from .models import WhatsappConnection

logger = logging.getLogger(__name__)

# Configuración de la API de Meta
GRAPH_API_VERSION = "v18.0"


# --- FUNCIONES AUXILIARES DE LÓGICA (SERVICES) ---

def send_whatsapp_message(connection, payload):
    """
    Envía una carga útil (payload) JSON a la API de WhatsApp Business.
    """
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{connection.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {connection.access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        # logger.info(f"Mensaje enviado: {response.json()}") # Descomentar para debug detallado
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a WhatsApp: {e}")
        if response is not None:
            logger.error(f"Detalle respuesta Meta: {response.text}")


def handle_received_media(connection, media_id, mime_type):
    """
    Descarga un archivo multimedia desde los servidores de Meta.
    Retorna la ruta relativa del archivo guardado o None si falla.
    """
    # 1. Obtener la URL de descarga del objeto multimedia
    url_info = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    headers = {"Authorization": f"Bearer {connection.access_token}"}

    try:
        # Paso A: Obtener metadatos (URL real)
        resp_info = requests.get(url_info, headers=headers)
        resp_info.raise_for_status()
        media_url = resp_info.json().get('url')

        if not media_url:
            return None

        # Paso B: Descargar el contenido binario
        media_content = requests.get(media_url, headers=headers)
        media_content.raise_for_status()

        # Paso C: Determinar extensión y nombre
        extension = mimetypes.guess_extension(mime_type) or '.bin'
        filename = f"{media_id}{extension}"

        # Ruta de guardado (media/whatsapp_received/...)
        save_dir = os.path.join(settings.MEDIA_ROOT, 'whatsapp_received')
        os.makedirs(save_dir, exist_ok=True)

        full_path = os.path.join(save_dir, filename)

        with open(full_path, 'wb') as f:
            f.write(media_content.content)

        logger.info(f"Archivo multimedia guardado en: {full_path}")
        return full_path

    except Exception as e:
        logger.error(f"Error descargando media {media_id}: {e}")
        return None


def process_message(connection, message_data):
    """
    Analiza el mensaje entrante y decide qué responder según el Chatbot configurado.
    """
    sender_phone = message_data.get('from')
    msg_type = message_data.get('type')

    reply_payload = None

    # --- 1. PROCESAMIENTO DE TEXTO ---
    if msg_type == 'text':
        text_body = message_data['text']['body'].strip().lower()
        response_text = ""

        # Lógica basada en el 'slug' del Chatbot asignado
        chatbot_slug = connection.chatbot.slug if connection.chatbot else None

        if chatbot_slug == 'bot_ventas':
            if 'precio' in text_body or 'costo' in text_body:
                response_text = "💰 Nuestros servicios empiezan desde $100 USD. ¿Te gustaría ver el catálogo?"
            elif 'hola' in text_body:
                response_text = "¡Hola! Soy el asistente de Ventas. Escribe 'precio' para saber nuestros costos."
            else:
                response_text = "Soy el bot de ventas. Actualmente solo respondo a consultas de precios."

        elif chatbot_slug == 'bot_soporte':
            if 'ayuda' in text_body or 'error' in text_body:
                response_text = "⚠️ Hemos registrado tu incidencia. Un técnico la revisará pronto."
            else:
                response_text = "Soporte Técnico: Por favor describe tu error o escribe 'ayuda'."

        else:
            # Bot por defecto (si no hay chatbot asignado o slug desconocido)
            response_text = f"🤖 Recibido: {text_body}. (Sin chatbot configurado)"

        # Construir respuesta
        reply_payload = {
            "messaging_product": "whatsapp",
            "to": sender_phone,
            "type": "text",
            "text": {"body": response_text}
        }

    # --- 2. PROCESAMIENTO DE MULTIMEDIA ---
    elif msg_type in ['image', 'document', 'audio', 'video', 'sticker']:
        media_node = message_data[msg_type]
        media_id = media_node.get('id')
        mime_type = media_node.get('mime_type')

        # Descargar archivo
        saved_path = handle_received_media(connection, media_id, mime_type)

        if saved_path:
            response_text = f"✅ He recibido tu archivo ({msg_type}) correctamente."
        else:
            response_text = f"❌ Hubo un error al intentar descargar tu archivo ({msg_type})."

        reply_payload = {
            "messaging_product": "whatsapp",
            "to": sender_phone,
            "type": "text",
            "text": {"body": response_text}
        }

    # Enviar la respuesta si se generó alguna
    if reply_payload:
        send_whatsapp_message(connection, reply_payload)


# --- VISTAS PRINCIPALES ---

@permission_classes([AllowAny])
@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    """
    Endpoint principal para la API de WhatsApp.
    """
    # 1. VERIFICACIÓN (GET)
    if request.method == "GET":
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe':
                # Verifica si el token existe en alguna conexión activa
                exists = WhatsappConnection.objects.filter(verify_token=token, is_active=True).exists()
                if exists:
                    return HttpResponse(challenge, status=200)
                else:
                    return HttpResponse("Token de verificación inválido", status=403)
        return HttpResponse("Fallo en verificación", status=403)

    # 2. RECEPCIÓN DE EVENTOS (POST)
    elif request.method == "POST":
        try:
            body = json.loads(request.body.decode('utf-8'))

            # Verificar estructura básica de WhatsApp
            if 'object' in body and body['object'] == 'whatsapp_business_account':
                entries = body.get('entry', [])

                for entry in entries:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})

                        # Obtener ID del teléfono que recibe (nuestro negocio)
                        metadata = value.get('metadata', {})
                        phone_number_id = metadata.get('phone_number_id')

                        if phone_number_id:
                            connection = WhatsappConnection.objects.filter(
                                phone_number_id=phone_number_id,
                                is_active=True
                            ).first()

                            if connection:
                                # Procesar mensajes entrantes
                                messages_list = value.get('messages', [])
                                for message in messages_list:
                                    # logger.info(f"Procesando mensaje de {message.get('from')}")
                                    process_message(connection, message)
                            else:
                                logger.warning(
                                    f"Mensaje recibido en ID {phone_number_id} sin conexión activa asociada.")

            return JsonResponse({'status': 'ok'}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
        except Exception as e:
            logger.error(f"Excepción en webhook: {str(e)}")
            # Siempre devolver 200 a Meta para evitar reintentos infinitos si falla nuestro código
            return JsonResponse({'status': 'error', 'message': str(e)}, status=200)


def dashboard(request):
    """Listado de conexiones activas."""
    connections = WhatsappConnection.objects.all()
    return render(request, 'whatsapp_manager/dashboard.html', {'connections': connections})


def create_connection(request):
    """Formulario para crear nueva conexión."""
    if request.method == 'POST':
        form = ConnectionForm(request.POST)
        if form.is_valid():
            connection = form.save()
            messages.success(request, f'Conexión "{connection.name}" creada exitosamente.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        # Generar token aleatorio simple por defecto
        import secrets
        random_token = secrets.token_urlsafe(16)
        form = ConnectionForm(initial={'verify_token': random_token})

    return render(request, 'whatsapp_manager/create_connection.html', {'form': form})


def generate_qr(request, connection_id):
    """
    Genera un código QR que apunta al link wa.me del número configurado.
    """
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)

    if not connection.display_phone_number:
        return HttpResponse("Número de visualización no configurado", status=404)

    # Crear enlace (eliminar espacios o guiones si existen)
    clean_number = ''.join(filter(str.isdigit, connection.display_phone_number))
    wa_link = f"https://wa.me/{clean_number}"

    # Configuración del QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(wa_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")

    return HttpResponse(buffer.getvalue(), content_type="image/png")


def chat_interface(request, connection_id):
    """
    Renderiza la interfaz de chat para una conexión específica.
    """
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)

    # NOTA: Aquí deberías obtener los mensajes reales de tu base de datos.
    # Como no tengo acceso a tu models.py, simularé la estructura de datos
    # que el template espera. Debes reemplazar esto con una query real.
    # Ejemplo: messages_list = Message.objects.filter(connection=connection).order_by('timestamp')

    # MOCK DATA (Para demostración)
    # Debes agrupar los mensajes por número de teléfono (contactos)
    conversations = [
        {'phone': '5215555555555', 'last_msg': 'Hola, precio?', 'timestamp': '10:00'},
        {'phone': '34666666666', 'last_msg': 'Gracias', 'timestamp': '09:30'},
    ]

    context = {
        'connection': connection,
        'conversations': conversations,
        # Si seleccionas un chat específico:
        'active_phone': request.GET.get('phone'),
    }
    return render(request, 'whatsapp_manager/chat.html', context)


@require_http_methods(["POST"])
def send_message_ui(request, connection_id):
    """
    Endpoint interno para enviar mensajes desde la interfaz web (AJAX).
    """
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)

    try:
        data = json.loads(request.body)
        phone_number = data.get('phone')
        message_body = data.get('message')

        if not phone_number or not message_body:
            return JsonResponse({'status': 'error', 'message': 'Faltan datos'}, status=400)

        # Construir payload para la API de WhatsApp
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": message_body}
        }

        # Usar tu función existente para enviar
        send_whatsapp_message(connection, payload)

        # AQUÍ DEBERÍAS GUARDAR EL MENSAJE SALIENTE EN TU DB (MODELO MESSAGE)
        # Message.objects.create(..., direction='outbound', body=message_body)

        return JsonResponse({'status': 'ok', 'message': 'Enviado'}, status=200)

    except Exception as e:
        logger.error(f"Error enviando mensaje UI: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)