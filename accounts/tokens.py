from rest_framework_simplejwt.tokens import RefreshToken


class SessionRefreshToken(RefreshToken):
    """
    Extends RefreshToken to include session_key in both
    the refresh AND access token claims.
    This lets us check session validity on every request.
    """

    @classmethod
    def for_user_with_session(cls, user, session_key):
        token = cls.for_user(user)
        # Add session_key to refresh token
        token['session_key'] = session_key
        # Add session_key to access token as well
        token.access_token['session_key'] = session_key
        return token

    @property
    def access_token(self):
        """
        Override access_token property to ensure session_key is copied
        from refresh token to the new access token.
        """
        access = super().access_token
        # Copy session_key if it exists in the refresh token claims
        if 'session_key' in self:
            access['session_key'] = self['session_key']
        return access
