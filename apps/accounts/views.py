import logging

from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.services import record as audit_record

from .models import User
from .serializers import RegisterSerializer, UserSerializer

logger = logging.getLogger("dataflow.accounts")


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def perform_create(self, serializer):
        user = serializer.save()
        logger.info(
            "user registered", extra={"user_id": user.id, "username": user.username}
        )
        audit_record(user, "user.registered", target=user.username)


class LoginView(TokenObtainPairView):
    """Wraps SimpleJWT's token endpoint to add an audit trail entry and the tighter "auth"
    throttle scope — login is a classic brute-force target."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            username = request.data.get("username", "")
            user = User.objects.filter(username=username).first()
            audit_record(user, "user.logged_in", target=username)
        return response


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
