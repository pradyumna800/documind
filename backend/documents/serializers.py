from rest_framework import serializers
from .models import Document, DocumentInsights, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "is_hidden", "created_at", "document_count"]
        read_only_fields = ["id", "created_at", "document_count"]

    def get_document_count(self, obj):
        return obj.documents.count()


class DocumentSerializer(serializers.ModelSerializer):
    has_insights = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id", "workspace", "original_filename", "file_type", "file_size", "status",
            "page_count", "chunk_count", "error_message", "uploaded_at", "processed_at",
            "has_insights",
        ]
        read_only_fields = [f for f in fields if f != "workspace"]  # workspace can be reassigned by the user

    def get_has_insights(self, obj):
        return DocumentInsights.objects.filter(document=obj, status=DocumentInsights.Status.COMPLETED).exists()


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["stored_file", "workspace"]
        extra_kwargs = {"workspace": {"required": False, "allow_null": True}}


class DocumentInsightsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentInsights
        fields = ["status", "summary", "key_terms", "quiz", "error_message", "generated_at"]
        read_only_fields = fields
