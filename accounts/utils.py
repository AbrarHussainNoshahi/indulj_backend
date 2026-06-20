import random
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    send_mail(
        subject='INDULJ - Your Verification Code',
        message=f'Your OTP is: {otp}\n\nExpires in 10 minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def set_auth_cookies(response, access_token, refresh_token):
    is_secure = settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', False)
    samesite  = settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax')

    response.set_cookie(
        key='access_token',
        value=access_token,
        max_age=15 * 60,  # 15 minutes
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        path='/',
    )
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        max_age=7 * 24 * 60 * 60,  # 7 days
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        path='/',
    )


def clear_auth_cookies(response):
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')