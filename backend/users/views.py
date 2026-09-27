from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegisterSerializer, UserSerializer, ProfileUpdateSerializer


class RegisterView(generics.CreateAPIView):
    """Public endpoint — anyone can create an account."""
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(APIView):
    """
    GET   -> the currently authenticated user's own profile (including avatar)
    PATCH -> update name/bio/avatar

    Note: the user is identified from the JWT access token, never from
    anything the client sends — this is the pattern used everywhere to
    make sure a user can only ever see or change their own data.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # MultiPart needed for avatar file uploads

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save(request.user)
        return Response(UserSerializer(user, context={"request": request}).data)
