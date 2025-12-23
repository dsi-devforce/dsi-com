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
from .models import WhatsappConnection, WebhookLog, Message
from django.test import RequestFactory
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
    msg_id = message_data.get('id')

    # 1. EVITAR DUPLICADOS
    if Message.objects.filter(wa_id=msg_id).exists():
        logger.info(f"Mensaje duplicado ignorado: {msg_id}")
        return

    reply_payload = None

    # --- 2. PROCESAMIENTO DE TEXTO ---
    if msg_type == 'text':
        text_body = message_data['text']['body'] # Original

        # GUARDAR MENSAJE ENTRANTE (TEXTO)
        Message.objects.create(
            connection=connection,
            wa_id=msg_id,
            phone_number=sender_phone,
            body=text_body,
            msg_type='text',
            direction='inbound'
        )

        text_body_lower = text_body.strip().lower() # Para lógica
        response_text = ""

        # Lógica basada en el 'slug' del Chatbot asignado
        chatbot_slug = connection.chatbot.slug if connection.chatbot else None

        if chatbot_slug == 'bot_ventas':
            if 'precio' in text_body_lower or 'costo' in text_body_lower:
                response_text = "💰 Nuestros servicios empiezan desde $100 USD. ¿Te gustaría ver el catálogo?"
            elif 'hola' in text_body_lower:
                response_text = "¡Hola! Soy el asistente de Ventas. Escribe 'precio' para saber nuestros costos."
            else:
                response_text = "Soy el bot de ventas. Actualmente solo respondo a consultas de precios."

        elif chatbot_slug == 'bot_soporte':
            if 'ayuda' in text_body_lower or 'error' in text_body_lower:
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

    # --- 3. PROCESAMIENTO DE MULTIMEDIA ---
    elif msg_type in ['image', 'document', 'audio', 'video', 'sticker']:
        media_node = message_data[msg_type]
        media_id = media_node.get('id')
        mime_type = media_node.get('mime_type')

        # Descargar archivo
        saved_path = handle_received_media(connection, media_id, mime_type)

        # GUARDAR MENSAJE ENTRANTE (MULTIMEDIA)
        Message.objects.create(
            connection=connection,
            wa_id=msg_id,
            phone_number=sender_phone,
            body=f"Archivo recibido: {msg_type}",
            media_file=saved_path,
            msg_type=msg_type,
            direction='inbound'
        )

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

        # GUARDAR RESPUESTA DEL BOT (SALIENTE)
        if reply_payload['type'] == 'text':
            Message.objects.create(
                connection=connection,
                phone_number=sender_phone,
                body=reply_payload['text']['body'],
                direction='outbound'
            )

@permission_classes([AllowAny])
@csrf_exempt
@require_http_methods(["GET", "POST"])
@permission_classes([AllowAny])
@csrf_exempt
@require_http_methods(["GET", "POST"])
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

            # --- GUARDAR LOG ---
            try:
                WebhookLog.objects.create(payload=body)
            except Exception as log_error:
                logger.error(f"No se pudo guardar el log: {log_error}")

            # Verificar estructura básica de WhatsApp
            if 'object' in body and body['object'] == 'whatsapp_business_account':
                entries = body.get('entry', [])

                for entry in entries:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})
                        metadata = value.get('metadata', {})
                        phone_number_id = metadata.get('phone_number_id')

                        if phone_number_id:
                            connection = WhatsappConnection.objects.filter(
                                phone_number_id=phone_number_id,
                                is_active=True
                            ).first()

                            if connection:
                                # A. PROCESAR MENSAJES (Texto, Imagen, etc.)
                                messages_list = value.get('messages', [])
                                for message in messages_list:
                                    process_message(connection, message)

                                # B. PROCESAR ESTADOS (Sent, Delivered, Read)
                                statuses_list = value.get('statuses', [])
                                for status in statuses_list:
                                    status_id = status.get('id')
                                    status_val = status.get('status')
                                    # Aquí podrías actualizar el estado en BD si quisieras
                                    logger.info(f"Estado recibido: ID={status_id}, Status={status_val}")

            return JsonResponse({'status': 'ok'}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
        except Exception as e:
            logger.error(f"Excepción en webhook: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=200)
# --- VISTAS DE INSPECCIÓN (NUEVO) ---

def webhook_inspector(request):
    """Renderiza la página del visor de logs."""
    return render(request, 'whatsapp_manager/webhook_inspector.html')


def get_latest_logs(request):
    """API JSON para obtener los logs más recientes (polling)."""
    last_id = request.GET.get('last_id', 0)

    # Obtener logs creados después del último ID que tiene el cliente
    logs = WebhookLog.objects.filter(id__gt=last_id).order_by('-id')[:20]

    data = []
    for log in logs:
        data.append({
            'id': log.id,
            'created_at': log.created_at.strftime("%H:%M:%S"),
            'payload': log.payload
        })

    # Invertimos para que el orden cronológico sea correcto en la lista (antiguo -> nuevo) al agregar
    return JsonResponse({'logs': list(reversed(data))})

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

    # 1. Obtener lista de conversaciones (agrupando por teléfono)
    # Hacemos una agrupación manual simple para obtener el último mensaje de cada teléfono
    all_messages = connection.messages.all().order_by('-timestamp')
    contacts = {}

    for msg in all_messages:
        if msg.phone_number not in contacts:
            contacts[msg.phone_number] = {
                'phone': msg.phone_number,
                'last_msg': msg.body or f"[{msg.msg_type}]",
                'timestamp': msg.timestamp
            }

    conversations = list(contacts.values())

    # 2. Si se seleccionó un teléfono, cargar sus mensajes
    active_phone = request.GET.get('phone')
    active_messages = []

    if active_phone:
        active_messages = connection.messages.filter(phone_number=active_phone).order_by('timestamp')

    context = {
        'connection': connection,
        'conversations': conversations,
        'active_phone': active_phone,
        'active_messages': active_messages,  # Asegúrate de usar esta variable en tu template chat.html
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
        # GUARDAR MENSAJE MANUAL (SALIENTE)
        Message.objects.create(
            connection=connection,
            phone_number=phone_number,
            body=message_body,
            direction='outbound'
        )
        # AQUÍ DEBERÍAS GUARDAR EL MENSAJE SALIENTE EN TU DB (MODELO MESSAGE)
        # Message.objects.create(..., direction='outbound', body=message_body)

        return JsonResponse({'status': 'ok', 'message': 'Enviado'}, status=200)

    except Exception as e:
        logger.error(f"Error enviando mensaje UI: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def webhook_simulator(request):
    """
    Herramienta para simular eventos de Webhook manualmente.
    """
    result = None
    initial_json = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "123456789",
                        "phone_number_id": "TU_ID_AQUI"
                    },
                    "messages": [{
                        "from": "5215555555555",
                        "id": "wamid.HBgLM...",
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": "Hola, prueba desde simulador"}
                    }]
                }
            }]
        }]
    }, indent=2)

    if request.method == 'POST':
        json_content = request.POST.get('json_payload')

        try:
            # 1. Validar que sea JSON válido
            payload = json.loads(json_content)

            # 2. Crear una petición POST simulada (Mock Request)
            # Usamos RequestFactory para crear un request interno idéntico al real
            factory = RequestFactory()
            mock_request = factory.post(
                '/whatsapp/webhook/',
                data=payload,
                content_type='application/json'
            )

            # Si usas validación de firma en webhook, aquí tendrías que simular el header
            # o hacer que tu webhook ignore la firma si viene de localhost o similar.
            # Por ahora asumiremos que en desarrollo no valida firma estricta o que este mock la pasa.

            # 3. Llamar a la vista webhook real
            response = webhook(mock_request)

            if response.status_code == 200:
                result = {'status': 'success',
                          'message': '✅ Webhook procesado correctamente (Status 200). Revisa el chat.'}
            else:
                result = {'status': 'error',
                          'message': f'❌ El webhook respondió con error: {response.status_code} - {response.content.decode()}'}

        except json.JSONDecodeError:
            result = {'status': 'error', 'message': '❌ El contenido no es un JSON válido.'}
        except Exception as e:
            result = {'status': 'error', 'message': f'❌ Error interno: {str(e)}'}

        # Mantenemos el JSON que envió el usuario para que no tenga que pegarlo de nuevo si falló
        initial_json = json_content

    return render(request, 'whatsapp_manager/webhook_simulator.html', {
        'initial_json': initial_json,
        'result': result
    })