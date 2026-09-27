from django.conf import settings
from django.db import models


def user_avatar_path(instance, filename):
    return f"avatars/{instance.user_id}/{filename}"


class Profile(models.Model):
    """
    Extends the built-in User model with the extra fields a real product
    needs — avatar, bio — without touching Django's own auth tables.
    Created lazily (get_or_create) the first time a user views/edits their
    profile, rather than via a signal, to keep the users app dependency-free.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to=user_avatar_path, null=True, blank=True)
    bio = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return f"Profile({self.user_id})"
