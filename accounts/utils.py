import random
from django.core.mail import send_mail
import logging
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from decouple import config


logger = logging.getLogger(__name__)

def generate_otp():
    return str(random.randint(100000, 999999))


# def send_otp_email(email, otp):
#     subject = "INDULJ - Your OTP Code"
#     message = f"""
#     Hello 👋,

#     Your OTP code is: {otp}

#     This code will expire in 10 minutes.

#     If you did not request this, ignore this email.
#     """

#     send_mail(
#         subject,
#         message,
#         settings.DEFAULT_FROM_EMAIL,
#         [email],
#         fail_silently=False,
#     )

def send_otp_email(email, otp):
    try:
        send_mail(
            subject="INDULJ OTP Code",
            message=f"Your OTP is {otp}",
            from_email=config("EMAIL_HOST_USER"),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"OTP email failed: {e}")

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def set_auth_cookies(response, access_token, refresh_token):
    is_secure = settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', True)
    samesite  = settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'None')

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