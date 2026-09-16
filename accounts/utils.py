import random
from django.core.mail import EmailMultiAlternatives, send_mail
import logging
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from decouple import config
import resend
import os


resend.api_key = os.getenv("RESEND_API_KEY")

logger = logging.getLogger(__name__)

def generate_otp():
    return str(random.randint(100000, 999999))


def build_otp_email_html(otp, email=None, user_name=None):
    """
    Generate a responsive, premium HTML email template for OTP verification.
    """
    display_name = user_name or (email.split('@')[0] if email and '@' in email else "Foodie")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your INDULJ Verification Code</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <!-- Main Container Card -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 540px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 30px rgba(0,0,0,0.07); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%); padding: 36px 28px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 30px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #ff4d4d;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(255, 77, 77, 0.16); border: 1px solid rgba(255, 77, 77, 0.35); color: #ff6b6b; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; padding: 5px 14px; border-radius: 999px;">
                      🔐 Security Verification
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Section -->
          <tr>
            <td style="padding: 36px 32px 28px;">
              <h1 style="margin: 0 0 12px; font-size: 22px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                Confirm Your Verification Code
              </h1>
              
              <p style="margin: 0 0 20px; font-size: 15px; color: #475569; line-height: 1.6;">
                Hi <strong style="color: #0f172a;">{display_name}</strong>,
              </p>
              
              <p style="margin: 0 0 26px; font-size: 15px; color: #64748b; line-height: 1.6;">
                Please use the one-time passcode below to verify your account and complete your sign in. This code is confidential.
              </p>

              <!-- Highlighted OTP Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 24px 0 26px;">
                <tr>
                  <td align="center">
                    <table border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; border-radius: 16px; border: 1.5px solid #334155; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.15);">
                      <tr>
                        <td align="center" style="padding: 18px 36px;">
                          <span style="font-family: 'SF Mono', 'Roboto Mono', Menlo, Consolas, Monaco, monospace; font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #ffffff; padding-left: 10px; display: block;">
                            {otp}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Expiration Note -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="text-align: center; margin-bottom: 24px;">
                <tr>
                  <td align="center">
                    <span style="display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: #64748b; background-color: #f8fafc; padding: 6px 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                      ⏱ This code is valid for <strong style="color: #0f172a; margin-left: 4px;">10 minutes</strong>
                    </span>
                  </td>
                </tr>
              </table>

              <!-- Security Advice Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border: 1px solid #fee2e2; border-radius: 12px; margin-top: 10px;">
                <tr>
                  <td style="padding: 14px 16px; font-size: 13px; color: #991b1b; line-height: 1.5;">
                    <strong>Security Notice:</strong> Never share this code with anyone. INDULJ support representatives will never ask for your verification code. If you did not request this, you can safely ignore this email.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 22px 28px; text-align: center;">
              <p style="margin: 0 0 6px; font-size: 12px; color: #94a3b8;">
                © 2026 INDULJ. All rights reserved.
              </p>
              <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                Elevating dining experiences with exclusive deals & happy hours.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_otp_email(email, otp, user_name=None):
    """
    Sends a beautifully designed HTML OTP verification email with plain text fallback.
    """
    try:
        from_email = config(
            "DEFAULT_FROM_EMAIL",
            default=getattr(settings, "DEFAULT_FROM_EMAIL", None) or config("EMAIL_HOST_USER", default="INDULJ <noreply@indulj.app>")
        )
        if not from_email or "@" not in from_email:
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "INDULJ <noreply@indulj.app>")

        subject = f"{otp} is your INDULJ verification code"
        text_content = (
            f"INDULJ Verification Code\n\n"
            f"Your verification code is: {otp}\n\n"
            f"This code will expire in 10 minutes. For security, never share this code with anyone.\n\n"
            f"If you did not request this verification code, please ignore this email.\n\n"
            f"— The INDULJ Team\n"
        )
        html_content = build_otp_email_html(otp, email=email, user_name=user_name)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"OTP email sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"OTP email failed for {email}: {e}")
        return False

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


def get_tokens_for_user_with_session(user, session_key):
    """
    Generate JWT tokens with session_key baked in.
    Use this instead of get_tokens_for_user() everywhere.
    """
    from accounts.tokens import SessionRefreshToken
    refresh = SessionRefreshToken.for_user_with_session(user, session_key)
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