import json
import base64
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from api_manager.models import ApiClient
from whatsapp_manager.models import WhatsappConnection, Message
from whatsapp_manager import browser_service


class SetupConnectionView(APIView):
    """
    Endpoint para inicializar la estructura de datos.
    Espera un JWT en el header Authorization.
    """

    def decode_jwt_payload_unsafe(self, token):
        try:
            payload_part = token.split('.')[1]
            padding = '=' * (4 - len(payload_part) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_part + padding)
            return json.loads(decoded_bytes)
        except Exception as e:
            print(f"❌ Error decodificando JWT: {e}")
            return None

    def post(self, request):
        print(f"\n🔍 [DEBUG] Iniciando solicitud POST a SetupConnectionView")
        print(f"📩 Headers recibidos: {request.headers}")
        print(f"📦 Body recibido: {request.data}")

        # 1. Obtener el Token del Header
        auth_header = request.headers.get('Authorization', '')
        print(f"🔑 Auth Header: '{auth_header}'")

        if not auth_header.startswith('Bearer '):
            print("❌ Error: Header no empieza con Bearer")
            return Response(
                {"error": "Formato de token inválido. Use 'Bearer <token>'"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token = auth_header.split(' ')[1]

        # 2. Decodificar el Token
        payload = self.decode_jwt_payload_unsafe(token)
        print(f"🔓 Payload decodificado: {payload}")

        if not payload or 'sub' not in payload:
            print("❌ Error: Payload inválido o sin 'sub'")
            return Response(
                {"error": "Token ilegible o sin 'sub' (subject)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        client_api_key = payload['sub']
        print(f"👤 Buscando ApiClient con key: {client_api_key}")

        # 3. Validar cliente
        try:
            client = ApiClient.objects.get(api_key=client_api_key, is_active=True)
            print(f"✅ Cliente encontrado: {client.name} (ID: {client.id})")
        except ApiClient.DoesNotExist:
            print(f"❌ Error: Cliente no encontrado para key {client_api_key}")
            # DEBUG EXTRA: Listar clientes disponibles para ver si hay mismatch
            all_keys = list(ApiClient.objects.values_list('api_key', flat=True))
            print(f"ℹ️ Keys disponibles en DB: {all_keys}")

            return Response(
                {"error": "Cliente no autorizado o inactivo"},
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Procesar datos
        data = request.data
        conn_name = data.get('connection_name')
        phone_id = data.get('phone_number_id')
        access_token = data.get('access_token')

        if not all([conn_name, phone_id, access_token]):
            print(
                f"❌ Error: Faltan campos. Recibido: name={conn_name}, id={phone_id}, token={access_token is not None}")
            return Response(
                {"error": "Faltan datos: connection_name, phone_number_id, access_token"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Crear/Actualizar
        print("🛠️ Intentando update_or_create en DB...")
        connection, created = WhatsappConnection.objects.update_or_create(
            phone_number_id=phone_id,
            defaults={
                'name': conn_name,
                'access_token': access_token,
                'client': client,
                'is_active': True
            }
        )

        action = "created" if created else "updated"
        print(f"🎉 Éxito: Conexión {action} con ID {connection.id}")

        return Response({
            "status": "success",
            "message": f"Estructura configurada exitosamente. Conexión {action}.",
            "client_identified": client.name,
            "connection_id": connection.id
        }, status=status.HTTP_201_CREATED)

class BrowserLinkView(APIView):
    """
    Endpoint para obtener el QR de vinculación o verificar el estado.
    GET /api/v1/browser/link/?connection_id=1
    """

    def decode_jwt_payload_unsafe(self, token):
        # ... (reutiliza la lógica de decodificación anterior) ...
        try:
            payload_part = token.split('.')[1]
            padding = '=' * (4 - len(payload_part) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_part + padding))
        except:
            return None

    def get(self, request):
        # 1. Autenticación (Reutilizable)
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return Response({"error": "Token requerido"}, status=status.HTTP_401_UNAUTHORIZED)

        payload = self.decode_jwt_payload_unsafe(auth_header.split(' ')[1])
        if not payload: return Response({"error": "Token inválido"}, status=400)

        # 2. Obtener connection_id
        conn_id = request.query_params.get('connection_id')
        if not conn_id:
            return Response({"error": "connection_id es requerido"}, status=400)

        # 3. Validar Propiedad (Seguridad)
        # Solo permitimos ver el QR si la conexión pertenece al Cliente del Token
        try:
            client = ApiClient.objects.get(api_key=payload['sub'])
            connection = WhatsappConnection.objects.get(id=conn_id, client=client)
        except (ApiClient.DoesNotExist, WhatsappConnection.DoesNotExist):
            return Response({"error": "Conexión no encontrada o no autorizada"}, status=403)

        # 4. Interactuar con el Servicio de Navegador Refactorizado
        # Llamamos a la lógica interna que ahora soporta ID
        qr_base64, estado = browser_service.obtener_qr_screenshot(connection.id)

        response_data = {
            "connection_id": connection.id,
            "status": estado,
            "qr_image": qr_base64 if estado == "ESPERANDO_ESCANEO" else None,
            "message": ""
        }

        # 5. Lógica de Respuesta
        if estado == "YA_VINCULADO":
            response_data["message"] = "✅ El bot ya está vinculado y listo."
            # Opcional: Aquí podrías disparar el hilo del bot si no está corriendo
            # browser_service.ensure_bot_running(connection.id)

        elif estado == "ESPERANDO_ESCANEO":
            response_data["message"] = "📸 Escanea el código QR proporcionado."

        elif estado == "CARGANDO":
            response_data["message"] = "⏳ Iniciando navegador, intenta de nuevo en 5 segundos."

        elif estado == "BOT_OCUPADO":
            response_data["message"] = "⚠️ El bot está ocupado procesando mensajes. Intenta luego."

        return Response(response_data, status=status.HTTP_200_OK)


class ConnectionListView(APIView):
    """
    Endpoint para listar las conexiones activas del cliente.
    GET /api/v1/connections/
    """

    def decode_jwt_payload_unsafe(self, token):
        try:
            payload_part = token.split('.')[1]
            padding = '=' * (4 - len(payload_part) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_part + padding))
        except:
            return None

    def get(self, request):
        # 1. Autenticación Manual
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return Response({"error": "Token requerido"}, status=status.HTTP_401_UNAUTHORIZED)

        payload = self.decode_jwt_payload_unsafe(auth_header.split(' ')[1])
        if not payload or 'sub' not in payload:
            return Response({"error": "Token inválido o sin 'sub'"}, status=400)

        # 2. Identificación y Auto-aprovisionamiento del Cliente
        client_api_key = payload['sub']
        print(f"👤 Buscando (o creando) ApiClient con key: {client_api_key}")

        # Intentamos obtener o crear el cliente automáticamente
        # Esto soluciona el error de "Cliente no encontrado" en el primer uso
        client_name = payload.get('name', f"Cliente {client_api_key}")

        try:
            client, created_client = ApiClient.objects.get_or_create(
                api_key=client_api_key,
                defaults={
                    'name': client_name,
                    'is_active': True
                }
            )

            if created_client:
                print(f"✨ Cliente nuevo creado automáticamente: {client.name}")
            else:
                if not client.is_active:
                    return Response(
                        {"error": "Cliente inactivo"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                print(f"✅ Cliente existente validado: {client.name}")

        except Exception as e:
            print(f"❌ Error DB gestionando cliente: {e}")
            return Response(
                {"error": f"Error interno del servidor: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 3. Obtención de Conexiones
        # Ahora que tenemos 'client' seguro, filtramos sus conexiones
        connections = WhatsappConnection.objects.filter(client=client, is_active=True)

        data = []
        for conn in connections:
            data.append({
                "id": conn.id,
                "name": conn.name,
                "phone_number_id": conn.phone_number_id,
                "display_phone_number": conn.display_phone_number,
                "chatbot": conn.chatbot.name if conn.chatbot else None,
                "created_at": conn.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })

        return Response({"connections": data}, status=status.HTTP_200_OK)

class MessageListView(APIView):
    """
    Endpoint para obtener el historial de mensajes de una conexión específica.
    GET /api/v1/messages/?connection_id=1&limit=50
    """

    def decode_jwt_payload_unsafe(self, token):
        try:
            payload_part = token.split('.')[1]
            padding = '=' * (4 - len(payload_part) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_part + padding))
        except:
            return None

    def get(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return Response({"error": "Token requerido"}, status=status.HTTP_401_UNAUTHORIZED)

        payload = self.decode_jwt_payload_unsafe(auth_header.split(' ')[1])
        conn_id = request.query_params.get('connection_id')
        limit = int(request.query_params.get('limit', 20))

        if not conn_id:
            return Response({"error": "connection_id es requerido"}, status=400)

        try:
            # 1. Validar que la conexión pertenece al cliente del token
            client = ApiClient.objects.get(api_key=payload['sub'])
            connection = WhatsappConnection.objects.get(id=conn_id, client=client)

            # 2. Obtener mensajes
            messages = Message.objects.filter(connection=connection).order_by('-timestamp')[:limit]

            data = []
            for msg in messages:  # Invertimos para orden cronológico si se desea en frontend
                data.append({
                    "id": msg.id,
                    "wa_id": msg.wa_id,
                    "phone_number": msg.phone_number,
                    "body": msg.body,
                    "direction": msg.direction,
                    "type": msg.msg_type,
                    "media_file": msg.media_file,
                    "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                })

            return Response({
                "connection": connection.name,
                "count": len(data),
                "messages": data
            }, status=status.HTTP_200_OK)

        except (ApiClient.DoesNotExist, WhatsappConnection.DoesNotExist):
            return Response({"error": "Conexión no encontrada o acceso denegado"}, status=403)