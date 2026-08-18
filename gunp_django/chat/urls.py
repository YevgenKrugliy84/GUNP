from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_room, name='room'),
    path('messages/', views.list_messages, name='messages'),
    path('threads/', views.list_private_threads, name='threads'),
    path('send/', views.send_message, name='send'),
]
