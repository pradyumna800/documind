from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "sources", "created_at"]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    document_ids = serializers.PrimaryKeyRelatedField(
        source="documents", many=True, read_only=True
    )

    class Meta:
        model = Conversation
        fields = ["id", "title", "document_ids", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "document_ids"]


class AskQuestionSerializer(serializers.Serializer):
    question = serializers.CharField()
    document_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    # "chat" (default) = normal single-answer Q&A.
    # "compare" = explicitly structure the answer as a comparison across
    # the selected documents, using per-document retrieval instead of one
    # combined top_k search.
    mode = serializers.ChoiceField(choices=["chat", "compare"], required=False, default="chat")
