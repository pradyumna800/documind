from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import Profile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.CharField(source="profile.bio", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "date_joined", "avatar_url", "bio"]

    def get_avatar_url(self, obj):
        profile = getattr(obj, "profile", None)
        if profile and profile.avatar:
            request = self.context.get("request")
            return request.build_absolute_uri(profile.avatar.url) if request else profile.avatar.url
        return None


class ProfileUpdateSerializer(serializers.Serializer):
    """
    Handles updates to fields that live on User AND fields that live on
    Profile in one request, so the frontend doesn't need to know or care
    that they're technically two separate database tables.
    """
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    bio = serializers.CharField(required=False, allow_blank=True, max_length=200)
    avatar = serializers.ImageField(required=False, allow_null=True)

    def save(self, user):
        profile, _ = Profile.objects.get_or_create(user=user)

        if "first_name" in self.validated_data:
            user.first_name = self.validated_data["first_name"]
        if "last_name" in self.validated_data:
            user.last_name = self.validated_data["last_name"]
        user.save(update_fields=["first_name", "last_name"])

        if "bio" in self.validated_data:
            profile.bio = self.validated_data["bio"]
        if "avatar" in self.validated_data:
            profile.avatar = self.validated_data["avatar"]
        profile.save()

        return user
