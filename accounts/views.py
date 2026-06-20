import requests as http_requests
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import NotificationPreference, OTPVerification, User, UserSession
from .serializers import (
    ChangePasswordSerializer, LoginSerializer,
    NotificationPreferenceSerializer, RegisterSerializer,
    ResendOTPSerializer, UpdateProfileSerializer,
    UserSerializer, UserSessionSerializer, VerifyOTPSerializer,
)
from .utils import (
    clear_auth_cookies, generate_otp, get_tokens_for_user,
    send_otp_email, set_auth_cookies,
)


def make_user_data(user, request=None):
    return {
        'success': True,
        'role':    user.role,
        'user':    UserSerializer(user, context={'request': request}).data,
    }


# ─── REGISTER ───────────────────────────────────────────────
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = serializer.save()
        otp  = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        send_otp_email(user.email, otp)
        return Response({
            'success': True,
            'message': 'OTP sent to your email.',
            'email':   user.email,
        }, status=status.HTTP_201_CREATED)


# ─── VERIFY OTP ─────────────────────────────────────────────
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=400
            )
        email = serializer.validated_data['email']
        otp   = serializer.validated_data['otp']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'message': 'User not found'}, status=404)

        otp_obj = OTPVerification.objects.filter(
            user=user, otp=otp, is_used=False
        ).last()

        if not otp_obj:
            return Response({'success': False, 'message': 'Invalid OTP'}, status=400)
        if not otp_obj.is_valid():
            return Response({'success': False, 'message': 'OTP expired'}, status=400)

        otp_obj.is_used = True
        otp_obj.save()
        user.is_email_verified = True
        user.save()

        tokens   = get_tokens_for_user(user)
        response = Response({
            **make_user_data(user, request),
            'message': 'Email verified successfully',
        })
        set_auth_cookies(response, tokens['access'], tokens['refresh'])
        return response


# ─── RESEND OTP ─────────────────────────────────────────────
class ResendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'message': 'User not found'}, status=404)

        if user.is_email_verified:
            return Response({'success': False, 'message': 'Email already verified'}, status=400)

        OTPVerification.objects.filter(user=user, is_used=False).update(is_used=True)
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        send_otp_email(user.email, otp)
        return Response({'success': True, 'message': 'New OTP sent'})


# ─── LOGIN ──────────────────────────────────────────────────
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        email    = serializer.validated_data['email']
        password = serializer.validated_data['password']
        user     = authenticate(request, username=email, password=password)

        if not user:
            return Response(
                {'success': False, 'message': 'Invalid email or password'},
                status=401
            )
        if not user.is_email_verified:
            return Response({
                'success': False,
                'message': 'Please verify your email first',
                'email':   email,
                'requires_verification': True,
            }, status=403)
        if user.is_suspended:
            return Response(
                {'success': False, 'message': 'Account suspended. Contact support.'},
                status=403
            )

        tokens   = get_tokens_for_user(user)
        response = Response({
            **make_user_data(user, request),
            'message': 'Login successful',
        })
        set_auth_cookies(response, tokens['access'], tokens['refresh'])
        return response


# ─── GOOGLE LOGIN ───────────────────────────────────────────
class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        access_token = request.data.get('token')
        if not access_token:
            return Response({'success': False, 'message': 'Token required'}, status=400)

        google_response = http_requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if google_response.status_code != 200:
            return Response({'success': False, 'message': 'Invalid Google token'}, status=400)

        info      = google_response.json()
        email     = info.get('email')
        full_name = info.get('name', '')

        if not email:
            return Response({'success': False, 'message': 'Could not get email'}, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'full_name':         full_name,
                'role':              'user',
                'is_email_verified': True,
            }
        )
        if user.is_suspended:
            return Response({'success': False, 'message': 'Account suspended'}, status=403)
        if created:
            NotificationPreference.objects.create(user=user)

        tokens   = get_tokens_for_user(user)
        response = Response({
            **make_user_data(user, request),
            'message': 'Google login successful',
        })
        set_auth_cookies(response, tokens['access'], tokens['refresh'])
        return response


# ─── LOGOUT ─────────────────────────────────────────────────
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
        response = Response({'success': True, 'message': 'Logged out'})
        clear_auth_cookies(response)
        return response


# ─── TOKEN REFRESH ──────────────────────────────────────────
class CookieTokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response({'success': False, 'message': 'No refresh token'}, status=401)
        try:
            refresh  = RefreshToken(refresh_token)
            tokens   = {'access': str(refresh.access_token), 'refresh': str(refresh)}
            response = Response({'success': True})
            set_auth_cookies(response, tokens['access'], tokens['refresh'])
            return response
        except TokenError:
            return Response({'success': False, 'message': 'Invalid refresh token'}, status=401)


# ─── PROFILE ────────────────────────────────────────────────
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'data': UserSerializer(request.user, context={'request': request}).data
        })

    def put(self, request):
        serializer = UpdateProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Profile updated',
                'data':    UserSerializer(request.user, context={'request': request}).data
            })
        return Response({'success': False, 'errors': serializer.errors}, status=400)


# ─── CHANGE PASSWORD ────────────────────────────────────────
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)
        if not request.user.check_password(serializer.validated_data['current_password']):
            return Response({'success': False, 'message': 'Current password incorrect'}, status=400)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'success': True, 'message': 'Password updated'})


# ─── DELETE ACCOUNT ─────────────────────────────────────────
class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        request.user.delete()
        response = Response({'success': True, 'message': 'Account deleted'})
        clear_auth_cookies(response)
        return response


# ─── NOTIFICATION PREFERENCES ───────────────────────────────
class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response({'success': True, 'data': NotificationPreferenceSerializer(prefs).data})

    def put(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'data': serializer.data})
        return Response({'success': False, 'errors': serializer.errors}, status=400)


# ─── SESSIONS ───────────────────────────────────────────────
class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = UserSession.objects.filter(user=request.user).order_by('-last_active')
        return Response({'success': True, 'data': UserSessionSerializer(sessions, many=True).data})


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        try:
            session = UserSession.objects.get(id=session_id, user=request.user)
            session.delete()
            return Response({'success': True, 'message': 'Session revoked'})
        except UserSession.DoesNotExist:
            return Response({'success': False, 'message': 'Session not found'}, status=404)


# ─── REFERRAL CODE ──────────────────────────────────────────
class ReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'success': True, 'data': {'referral_code': request.user.referral_code}})