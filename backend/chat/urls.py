from django.urls import path
from .views import (
    ConversationListCreateView, ConversationDetailView,
    MessageListView, AskQuestionView, AskQuestionStreamView,
)

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversation-list-create"),
    path("conversations/<int:pk>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<int:pk>/messages/", MessageListView.as_view(), name="message-list"),
    path("conversations/<int:pk>/ask/", AskQuestionView.as_view(), name="ask-question"),
    path("conversations/<int:pk>/ask-stream/", AskQuestionStreamView.as_view(), name="ask-question-stream"),
]
