from django.urls import path
from .views import SetupConnectionView, BrowserLinkView, ConnectionListView, MessageListView

urlpatterns = [
    # Endpoint: /api/v1/setup/
    path('setup/', SetupConnectionView.as_view(), name='api_setup'),
    path('browser/link/', BrowserLinkView.as_view(), name='api_browser_link'),
    path('connections/', ConnectionListView.as_view(), name='api_connections_list'),
    path('messages/', MessageListView.as_view(), name='api_messages_list'),
]
