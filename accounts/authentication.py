from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        # ── Try httpOnly cookie first ─────────────────────
        access_token = request.COOKIES.get('access_token')

        if access_token:
            try:
                validated_token = self.get_validated_token(access_token)
                user            = self.get_user(validated_token)

                # ── Check if session is revoked ───────────
                session_key = validated_token.get('session_key')
                if session_key:
                    self._check_session(user, session_key, request)

                return user, validated_token

            except (InvalidToken, AuthenticationFailed):
                return None

        # ── Fallback to Authorization header ─────────────
        return super().authenticate(request)

    def _check_session(self, user, session_key, request):
        """
        Raises AuthenticationFailed if session is revoked.
        Also updates last_active silently.
        """
        from accounts.models import UserSession

        try:
            session = UserSession.objects.get(
                user=user,
                session_key=session_key,
            )

            if session.is_revoked:
                raise AuthenticationFailed(
                    'SESSION_REVOKED',
                    code='session_revoked'
                )

            # Update last_active silently
            from django.utils import timezone
            UserSession.objects.filter(
                pk=session.pk
            ).update(last_active=timezone.now())

        except UserSession.DoesNotExist:
            # Session deleted entirely — treat as revoked
            raise AuthenticationFailed(
                'SESSION_REVOKED',
                code='session_revoked'
            )