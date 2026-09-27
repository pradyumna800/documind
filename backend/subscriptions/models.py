from django.conf import settings
from django.db import models


class Plan(models.Model):
    class PlanType(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"

    class PlanStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"
        PAST_DUE = "past_due", "Past due"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plan")
    plan_type = models.CharField(max_length=20, choices=PlanType.choices, default=PlanType.FREE)
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    renews_at = models.DateTimeField(null=True, blank=True)

    def limits(self):
        """Reads limits from settings.py, not hardcoded here — so changing
        a plan's limits never requires touching model/business logic."""
        from django.conf import settings as s
        if self.plan_type == self.PlanType.PRO:
            return {"max_documents": s.PRO_MAX_DOCUMENTS, "max_questions": s.PRO_MAX_QUESTIONS}
        return {"max_documents": s.FREE_MAX_DOCUMENTS, "max_questions": s.FREE_MAX_QUESTIONS}

    def __str__(self):
        return f"{self.user_id}: {self.plan_type}"
