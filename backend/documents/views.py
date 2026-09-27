import logging
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Document, DocumentInsights, Workspace
from .serializers import (
    DocumentSerializer, DocumentUploadSerializer, DocumentInsightsSerializer, WorkspaceSerializer,
)
from .ai_client import trigger_document_processing, trigger_document_deletion, trigger_study_materials

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf": "pdf", "txt": "txt", "docx": "docx"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


class WorkspaceListCreateView(generics.ListCreateAPIView):
    """
    GET  -> list the authenticated user's workspaces. Hidden ones are
            excluded by default; pass ?include_hidden=true to see them too
            (used by the "show hidden workspaces" toggle in the sidebar).
    POST -> create a new workspace (folder) to organize documents into
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        queryset = Workspace.objects.filter(user=self.request.user)
        if self.request.query_params.get("include_hidden") != "true":
            queryset = queryset.filter(is_hidden=False)
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WorkspaceDetailView(APIView):
    """
    PATCH  -> rename a workspace, or toggle is_hidden to hide/unhide it
    DELETE -> delete a workspace. Documents inside it are NOT deleted —
    they fall back to "Uncategorized" (workspace=None), since a workspace
    is just an organizational folder, not a container that owns the data.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        workspace = get_object_or_404(Workspace, pk=pk, user=request.user)
        serializer = WorkspaceSerializer(workspace, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        workspace = get_object_or_404(Workspace, pk=pk, user=request.user)
        workspace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentListCreateView(generics.ListCreateAPIView):
    """
    GET  -> list only the authenticated user's documents (never anyone else's).
            Optionally filter with ?workspace=<id>, or ?workspace=none for
            documents not assigned to any workspace.
    POST -> upload a new document, then kick off async-ish processing via FastAPI
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Document.objects.filter(user=self.request.user)
        workspace_param = self.request.query_params.get("workspace")
        if workspace_param == "none":
            queryset = queryset.filter(workspace__isnull=True)
        elif workspace_param:
            queryset = queryset.filter(workspace_id=workspace_param)
        return queryset

    def get_serializer_class(self):
        return DocumentUploadSerializer if self.request.method == "POST" else DocumentSerializer

    def create(self, request, *args, **kwargs):
        upload_serializer = DocumentUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        uploaded_file = upload_serializer.validated_data["stored_file"]
        workspace = upload_serializer.validated_data.get("workspace")

        # A workspace ID can only be honored if it actually belongs to this
        # user — otherwise silently drop it rather than trusting client input.
        if workspace and workspace.user_id != request.user.id:
            return Response({"detail": "Invalid workspace."}, status=status.HTTP_400_BAD_REQUEST)

        extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            return Response(
                {"detail": f"Unsupported file type '.{extension}'. Allowed: pdf, txt, docx."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            return Response({"detail": "File exceeds 20MB limit."}, status=status.HTTP_400_BAD_REQUEST)

        document = Document.objects.create(
            user=request.user,
            workspace=workspace,
            original_filename=uploaded_file.name,
            stored_file=uploaded_file,
            file_type=ALLOWED_EXTENSIONS[extension],
            file_size=uploaded_file.size,
            status=Document.Status.PROCESSING,
        )

        # MVP: call synchronously. This blocks the request while the file is
        # processed — fine for small files/dev. Phase 23 (background
        # processing) replaces this with a Celery task so uploads return
        # instantly and processing happens off the request/response cycle.
        try:
            result = trigger_document_processing(
                document_id=document.id,
                user_id=request.user.id,
                file_path=document.stored_file.path,
                file_type=document.file_type,
                document_name=document.original_filename,
            )
            document.page_count = result.get("page_count")
            document.chunk_count = result.get("chunk_count")
            document.status = Document.Status.COMPLETED
            document.save(update_fields=["page_count", "chunk_count", "status"])
        except Exception as exc:
            document.status = Document.Status.FAILED
            document.error_message = str(exc)
            document.save(update_fields=["status", "error_message"])

        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    """
    GET    -> fetch one document
    PATCH  -> move a document into a different workspace (or unassign it)
    DELETE -> delete a document. Ownership is enforced via filtering on
    `user=request.user` — a user can never even see, let alone delete,
    another user's document (it 404s instead of 403, so existence isn't
    leaked either).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_document(self, request, pk):
        return Document.objects.filter(user=request.user, pk=pk).first()

    def get(self, request, pk):
        document = self.get_document(request, pk)
        if not document:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(DocumentSerializer(document).data)

    def patch(self, request, pk):
        document = self.get_document(request, pk)
        if not document:
            return Response(status=status.HTTP_404_NOT_FOUND)
        workspace_id = request.data.get("workspace")
        if workspace_id in (None, "", "none"):
            document.workspace = None
        else:
            workspace = Workspace.objects.filter(pk=workspace_id, user=request.user).first()
            if not workspace:
                return Response({"detail": "Invalid workspace."}, status=status.HTTP_400_BAD_REQUEST)
            document.workspace = workspace
        document.save(update_fields=["workspace"])
        return Response(DocumentSerializer(document).data)

    def delete(self, request, pk):
        document = self.get_document(request, pk)
        if not document:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            trigger_document_deletion(document_id=document.id, user_id=request.user.id)
        except Exception:
            pass  # don't block deletion of the Django record if the AI service is unreachable
        if document.stored_file:
            document.stored_file.delete(save=False)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentInsightsView(APIView):
    """
    GET   -> fetch existing study material for a document (if any)
    POST  -> (re)generate study material — summary, key terms, quiz
    Both scoped to documents the requesting user actually owns.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_document_or_404(self, request, pk):
        return Document.objects.filter(user=request.user, pk=pk).first()

    def get(self, request, pk):
        document = self.get_document_or_404(request, pk)
        if not document:
            return Response(status=status.HTTP_404_NOT_FOUND)
        insights = DocumentInsights.objects.filter(document=document).first()
        if not insights:
            return Response({"status": DocumentInsights.Status.PENDING})
        return Response(DocumentInsightsSerializer(insights).data)

    def post(self, request, pk):
        document = self.get_document_or_404(request, pk)
        if not document:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if document.status != Document.Status.COMPLETED:
            return Response(
                {"detail": "Document must finish processing before study material can be generated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        insights, _ = DocumentInsights.objects.get_or_create(document=document)
        insights.status = DocumentInsights.Status.GENERATING
        insights.save(update_fields=["status"])

        try:
            result = trigger_study_materials(document_id=document.id, user_id=request.user.id)
            insights.summary = result.get("summary", "")
            insights.key_terms = result.get("key_terms", [])
            insights.quiz = result.get("quiz", [])
            insights.status = DocumentInsights.Status.COMPLETED
            insights.error_message = ""
            insights.generated_at = timezone.now()
            insights.save()
        except Exception as exc:
            logger.exception("Study material generation failed for document %s", document.id)
            insights.status = DocumentInsights.Status.FAILED
            insights.error_message = str(exc)
            insights.save(update_fields=["status", "error_message"])
            return Response(
                {"detail": "Could not generate study material. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(DocumentInsightsSerializer(insights).data, status=status.HTTP_201_CREATED)
