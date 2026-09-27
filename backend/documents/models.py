from django.conf import settings
from django.db import models


def user_document_path(instance, filename):
    # Files land under MEDIA_ROOT/documents/<user_id>/<filename>
    # Per-user folders make it trivial to see (and later migrate) one user's files.
    return f"documents/{instance.user_id}/{filename}"


class Workspace(models.Model):
    """
    A folder-like grouping of documents, e.g. "College", "Job Prep",
    "Company Docs". Purely organizational for now — documents in
    different workspaces are still owned by the same user and Q&A can
    still search across all of them; workspaces just make the sidebar
    navigable once someone has more than a handful of documents.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspaces")
    name = models.CharField(max_length=100)
    # Lets a user tidy their sidebar by hiding a workspace they're not
    # actively using, without losing it or its documents — a hidden
    # workspace is filtered out of the default list but never deleted.
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        TXT = "txt", "TXT"
        DOCX = "docx", "DOCX"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    # Nullable/SET_NULL on purpose: deleting a workspace should never delete
    # the documents inside it — they just become "Uncategorized" again.
    workspace = models.ForeignKey(
        Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    original_filename = models.CharField(max_length=255)
    stored_file = models.FileField(upload_to=user_document_path)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    file_size = models.PositiveIntegerField(help_text="Size in bytes")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    chunk_count = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.user_id})"


class DocumentInsights(models.Model):
    """
    Auto-generated study material for a document: a short summary, a
    glossary of key terms, and a quiz — this is what turns DocuMind from
    a generic "chat with your PDF" tool into an actual study companion.

    One-to-one with Document because each document gets exactly one set
    of study materials (regenerated in place if the user asks again,
    rather than accumulating duplicates).
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATING = "generating", "Generating"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="insights")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    summary = models.TextField(blank=True, default="")
    # key_terms: [{"term": "...", "definition": "..."}, ...]
    key_terms = models.JSONField(default=list, blank=True)
    # quiz: [{"question": "...", "options": [...], "correct_index": 0, "explanation": "..."}, ...]
    quiz = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default="")
    generated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Insights for {self.document.original_filename}"
