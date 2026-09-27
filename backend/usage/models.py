from django.conf import settings
from django.db import models


class Usage(models.Model):
    """One row per user, holding running counters. Updated incrementally
    (incremented on each action) rather than computed live each time —
    cheap to read for dashboards."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage")
    documents_uploaded = models.PositiveIntegerField(default=0)
    questions_asked = models.PositiveIntegerField(default=0)
    storage_bytes_used = models.PositiveBigIntegerField(default=0)
    period_start = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Usage({self.user_id})"
