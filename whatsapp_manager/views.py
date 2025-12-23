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

from .browser_service import obtener_qr_screenshot
from .forms import ConnectionForm
from .models import WhatsappConnection, WebhookLog, Message
from django.test import RequestFactory

logger = logging.getLogger(__name__)

# Configuración de la API de Meta
GRAPH_API_VERSION = "v18.0"


# ==============================================================================
# 1. CAPA DE HABILIDADES (HERRAMIENTAS / TOOLS)
# Aquí definimos las acciones concretas que el "Dispositivo" puede ejecutar.
# ==============================================================================

def tool_consultar_precio_servicio(servicio):
    """Simula una consulta a base de datos de precios o catálogo."""
    precios = {'web': 500, 'consultoria': 100, 'api': 300, 'ecommerce': 800}
    costo = precios.get(servicio.lower())
    if costo:
        return f"🏷️ El servicio de *{servicio.capitalize()}* tiene un costo base de ${costo} USD."
    return f"🔍 No encontré '{servicio}' en mi lista. Tenemos: Web, Consultoria, API, Ecommerce."


def tool_generar_ticket_soporte(usuario_telefono, problema):
    """Simula la creación de un ticket en un sistema externo (Jira, Zendesk, etc)."""
    # Aquí iría la lógica real de guardar en DB o llamar a una API externa
    ticket_id = abs(hash(usuario_telefono + problema)) % 10000
    return f"🎫 Ticket creado #{ticket_id}. Un agente humano revisará: '{problema}' y te contactará al {usuario_telefono}."


def tool_informacion_contacto():
    """Retorna información estática de contacto."""
    return "📍 Nos ubicamos en Av. Tecnología 123. Horario: 9am - 6pm. Correo: contacto@dsi.com"


# ==============================================================================
# 2. CAPA DEL AGENTE (CEREBRO / AI BRAIN)
# Esta función decide CÓMO responder. Aquí conectarías a OpenAI/Gemini más adelante.
# ==============================================================================

def ai_agent_logic(connection, user_text, sender_phone):
    """
    Recibe el texto del usuario y la conexión (dispositivo).
    Decide qué herramienta usar basándose en el 'Chatbot' asignado a la conexión.
    """
    text = user_text.lower().strip()

    # Obtenemos el "rol" o personalidad asignada a este número de WhatsApp
    bot_slug = connection.chatbot.slug if connection.chatbot else "default"

    # --- LÓGICA PARA BOT DE VENTAS ---
    if bot_slug == 'bot_ventas':
        if 'precio' in text or 'costo' in text or 'cuanto' in text:
            # Simulación de extracción de entidades (Entity Extraction)
            servicio_detectado = 'web'  # Por defecto
            if 'api' in text:
                servicio_detectado = 'api'
            elif 'tienda' in text or 'ecommerce' in text:
                servicio_detectado = 'ecommerce'
            elif 'consultoria' in text:
                servicio_detectado = 'consultoria'

            return tool_consultar_precio_servicio(servicio_detectado)

        if 'hola' in text or 'buenas' in text:
            return "👋 ¡Hola! Soy el Asistente de Ventas. ¿Te interesa desarrollo Web, APIs o Consultoría?"

    # --- LÓGICA PARA BOT DE SOPORTE ---
    elif bot_slug == 'bot_soporte':
        if 'error' in text or 'falla' in text or 'ayuda' in text:
            return tool_generar_ticket_soporte(sender_phone, text)

        if 'donde' in text or 'ubicacion' in text:
            return tool_informacion_contacto()

    # --- FALLBACK (RESPUESTA POR DEFECTO) ---
    return f"🤖 [Agente {bot_slug}]: Recibí tu mensaje: '{user_text}', pero no estoy entrenado para responder eso aún."


# ==============================================================================
# 3. SERVICIOS AUXILIARES (INFRAESTRUCTURA)
# ==============================================================================

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
        # logger.info(f"Mensaje enviado: {response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a WhatsApp: {e}")
        if 'response' in locals() and response is not None:
            logger.error(f"Detalle respuesta Meta: {response.text}")


def handle_received_media(connection, media_id, mime_type):
    """
    Descarga un archivo multimedia desde los servidores de Meta.
    """
    url_info = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    headers = {"Authorization": f"Bearer {connection.access_token}"}

    try:
        # Paso A: Obtener URL real
        resp_info = requests.get(url_info, headers=headers)
        resp_info.raise_for_status()
        media_url = resp_info.json().get('url')

        if not media_url:
            return None

        # Paso B: Descargar binario
        media_content = requests.get(media_url, headers=headers)
        media_content.raise_for_status()

        # Paso C: Guardar
        extension = mimetypes.guess_extension(mime_type) or '.bin'
        filename = f"{media_id}{extension}"
        save_dir = os.path.join(settings.MEDIA_ROOT, 'whatsapp_received')
        os.makedirs(save_dir, exist_ok=True)
        full_path = os.path.join(save_dir, filename)

        with open(full_path, 'wb') as f:
            f.write(media_content.content)

        return full_path
    except Exception as e:
        logger.error(f"Error descargando media {media_id}: {e}")
        return None


def process_message(connection, message_data):
    """
    Orquestador: Recibe el JSON de Meta, guarda en BD y llama al Agente IA.
    """
    sender_phone = message_data.get('from')
    msg_type = message_data.get('type')
    msg_id = message_data.get('id')

    # 1. EVITAR DUPLICADOS
    if Message.objects.filter(wa_id=msg_id).exists():
        logger.info(f"Mensaje duplicado ignorado: {msg_id}")
        return

    reply_payload = None

    # --- A. SI ES TEXTO ---
    if msg_type == 'text':
        text_body = message_data['text']['body']

        # Guardar Mensaje Entrante
        Message.objects.create(
            connection=connection,
            wa_id=msg_id,
            phone_number=sender_phone,
            body=text_body,
            msg_type='text',
            direction='inbound'
        )

        # >>> LLAMADA AL AGENTE INTELIGENTE <<<
        response_text = ai_agent_logic(connection, text_body, sender_phone)

        # Preparar Respuesta
        reply_payload = {
            "messaging_product": "whatsapp",
            "to": sender_phone,
            "type": "text",
            "text": {"body": response_text}
        }

    # --- B. SI ES MULTIMEDIA ---
    elif msg_type in ['image', 'document', 'audio', 'video', 'sticker']:
        media_node = message_data[msg_type]
        media_id = media_node.get('id')
        mime_type = media_node.get('mime_type')

        saved_path = handle_received_media(connection, media_id, mime_type)

        Message.objects.create(
            connection=connection,
            wa_id=msg_id,
            phone_number=sender_phone,
            body=f"Archivo recibido: {msg_type}",
            media_file=saved_path,
            msg_type=msg_type,
            direction='inbound'
        )

        # Respuesta simple para multimedia (se podría mejorar con IA visual)
        reply_text = f"✅ Archivo ({msg_type}) recibido y procesado por el sistema."
        reply_payload = {
            "messaging_product": "whatsapp",
            "to": sender_phone,
            "type": "text",
            "text": {"body": reply_text}
        }

    # --- ENVIAR RESPUESTA ---
    if reply_payload:
        send_whatsapp_message(connection, reply_payload)

        # Guardar Respuesta Saliente
        if reply_payload['type'] == 'text':
            Message.objects.create(
                connection=connection,
                phone_number=sender_phone,
                body=reply_payload['text']['body'],
                direction='outbound'
            )


# ==============================================================================
# 4. VISTAS WEB (WEBHOOK Y UI)
# ==============================================================================

@csrf_exempt
def webhook(request):
    """
    Endpoint principal (Puerta de entrada de Meta).
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

            # Guardar Log Crudo
            try:
                WebhookLog.objects.create(payload=body)
            except Exception:
                pass

            if 'object' in body and body['object'] == 'whatsapp_business_account':
                entries = body.get('entry', [])

                for entry in entries:
                    changes = entry.get('changes', [])
                    for change in changes:
                        value = change.get('value', {})
                        metadata = value.get('metadata', {})
                        phone_number_id = metadata.get('phone_number_id')

                        if phone_number_id:
                            # Buscamos la conexión (Dispositivo) que coincide con el ID
                            connection = WhatsappConnection.objects.filter(
                                phone_number_id=phone_number_id,
                                is_active=True
                            ).first()

                            if connection:
                                # A. Mensajes
                                messages_list = value.get('messages', [])
                                for message in messages_list:
                                    process_message(connection, message)

                                # B. Estados
                                statuses_list = value.get('statuses', [])
                                for status in statuses_list:
                                    logger.info(f"Estado recibido: {status.get('status')}")
                            else:
                                # AQUÍ ESTABA EL ERROR: AVISAMOS SI NO HAY CONEXIÓN
                                logger.warning(
                                    f"⚠️ ID Recibido desconocido: {phone_number_id}. No coincide con ninguna conexión activa.")

            return JsonResponse({'status': 'ok'}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
        except Exception as e:
            logger.error(f"Excepción en webhook: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=200)

    return HttpResponse("Método no permitido", status=405)


def webhook_simulator(request):
    """
    Simulador que pre-carga un ID real para facilitar las pruebas.
    """
    result = None

    # BÚSQUEDA INTELIGENTE DE ID PARA EL EJEMPLO
    first_conn = WhatsappConnection.objects.filter(is_active=True).first()
    demo_phone_id = first_conn.phone_number_id if first_conn else "TU_ID_AQUI_O_CREA_UNA_CONEXION"

    initial_json = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "123456789",
                        "phone_number_id": demo_phone_id  # <--- ID REAL AQUÍ
                    },
                    "messages": [{
                        "from": "5215555555555",
                        "id": "wamid.HBgLM...",
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": "Hola, prueba de precio"}
                    }]
                }
            }]
        }]
    }, indent=2)

    if request.method == 'POST':
        json_content = request.POST.get('json_payload')
        try:
            payload = json.loads(json_content)
            factory = RequestFactory()
            mock_request = factory.post(
                '/whatsapp/webhook/',
                data=payload,
                content_type='application/json'
            )
            response = webhook(mock_request)

            if response.status_code == 200:
                result = {'status': 'success',
                          'message': '✅ Webhook procesado (200 OK). Revisa el Dashboard o el Chat.'}
            else:
                result = {'status': 'error', 'message': f'❌ Error: {response.status_code}'}
        except Exception as e:
            result = {'status': 'error', 'message': f'❌ Error interno: {str(e)}'}

        initial_json = json_content

    return render(request, 'whatsapp_manager/webhook_simulator.html', {
        'initial_json': initial_json,
        'result': result
    })


# --- VISTAS STANDARD (NO MODIFICADAS EN LÓGICA, SOLO RE-INCLUIDAS) ---

def webhook_inspector(request):
    return render(request, 'whatsapp_manager/webhook_inspector.html')


def get_latest_logs(request):
    last_id = request.GET.get('last_id', 0)
    logs = WebhookLog.objects.filter(id__gt=last_id).order_by('-id')[:20]
    data = [{'id': l.id, 'created_at': l.created_at.strftime("%H:%M:%S"), 'payload': l.payload} for l in logs]
    return JsonResponse({'logs': list(reversed(data))})


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
            messages.error(request, 'Por favor corrige los errores.')
    else:
        import secrets
        form = ConnectionForm(initial={'verify_token': secrets.token_urlsafe(16)})
    return render(request, 'whatsapp_manager/create_connection.html', {'form': form})


def generate_qr(request, connection_id):
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)
    if not connection.display_phone_number: return HttpResponse("Falta número", status=404)
    clean_number = ''.join(filter(str.isdigit, connection.display_phone_number))
    wa_link = f"https://wa.me/{clean_number}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(wa_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


def chat_interface(request, connection_id):
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)
    all_messages = connection.messages.all().order_by('-timestamp')
    contacts = {}
    for msg in all_messages:
        clean_phone = msg.phone_number.replace('+', '').strip()
        if clean_phone not in contacts:
            contacts[clean_phone] = {'phone': clean_phone, 'last_msg': msg.body, 'timestamp': msg.timestamp}
    conversations = list(contacts.values())

    active_phone = request.GET.get('phone')
    active_messages = []
    if active_phone:
        clean_active = active_phone.replace('+', '').strip()
        active_messages = connection.messages.filter(phone_number__icontains=clean_active).order_by('timestamp')

    return render(request, 'whatsapp_manager/chat.html', {
        'connection': connection, 'conversations': conversations,
        'active_phone': active_phone, 'active_messages': active_messages
    })


@require_http_methods(["POST"])
def send_message_ui(request, connection_id):
    connection = get_object_or_404(WhatsappConnection, pk=connection_id)
    try:
        data = json.loads(request.body)
        phone = data.get('phone')
        msg = data.get('message')
        if not phone or not msg: return JsonResponse({'status': 'error'}, status=400)

        payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": msg}}
        send_whatsapp_message(connection, payload)

        Message.objects.create(connection=connection, phone_number=phone, body=msg, direction='outbound')
        return JsonResponse({'status': 'ok'}, status=200)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def vincular_navegador(request):
    """
    Vista que inicia el navegador backend y muestra el QR al usuario.
    """
    qr_image, estado = obtener_qr_screenshot()

    context = {
        'estado': estado,
        'qr_image': qr_image
    }
    return render(request, 'whatsapp_manager/vincular_browser.html', context)