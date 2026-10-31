import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from decouple import config

logger = logging.getLogger(__name__)


def _get_app_base_url():
    url = getattr(settings, "FRONTEND_URL", None) or config("FRONTEND_URL", default="https://indulj.app")
    return str(url).rstrip("/")


def _get_from_email():
    from_email = config(
        "DEFAULT_FROM_EMAIL",
        default=getattr(settings, "DEFAULT_FROM_EMAIL", None) or config("EMAIL_HOST_USER", default="INDULJ <noreply@indulj.app>")
    )
    if not from_email or "@" not in str(from_email):
        from_email = getattr(settings, "EMAIL_HOST_USER", "INDULJ <noreply@indulj.app>")
    return from_email


# ─────────────────────────────────────────────────────────────
# 1. RESTAURANT REGISTRATION EMAIL TEMPLATE
# ─────────────────────────────────────────────────────────────

def build_restaurant_registration_email_html(restaurant_name, owner_name, email, password, login_url):
    display_name = owner_name or restaurant_name or "Restaurant Partner"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to INDULJ - Partner Account Details</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%); padding: 36px 32px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 32px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #ff4d4d;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(255, 77, 77, 0.16); border: 1px solid rgba(255, 77, 77, 0.35); color: #ff6b6b; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; padding: 6px 16px; border-radius: 999px;">
                      🍽️ Restaurant Partner Account
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Body -->
          <tr>
            <td style="padding: 38px 36px 28px;">
              <h1 style="margin: 0 0 10px; font-size: 23px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                Welcome to INDULJ! 🎉
              </h1>
              <p style="margin: 0 0 18px; font-size: 15px; color: #475569; line-height: 1.6;">
                Hi <strong style="color: #0f172a;">{display_name}</strong>,
              </p>
              <p style="margin: 0 0 24px; font-size: 15px; color: #475569; line-height: 1.6;">
                We are thrilled to welcome you! Your restaurant <strong style="color: #ff4d4d;">{restaurant_name}</strong> is now officially registered on the <strong>INDULJ</strong> dining platform.
              </p>

              <!-- Credentials Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 24px 0 28px; background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 16px; overflow: hidden;">
                <tr>
                  <td style="background-color: #0f172a; padding: 14px 22px;">
                    <span style="font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #ffffff;">
                      🔐 Your Account Credentials
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 22px;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Restaurant:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{restaurant_name}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Login Email:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{email}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Password:</td>
                        <td style="padding: 8px 0;">
                          <span style="display: inline-block; font-family: 'SF Mono', Menlo, Consolas, Monaco, monospace; font-size: 15px; font-weight: 700; color: #0f172a; background-color: #e2e8f0; padding: 5px 12px; border-radius: 6px; border: 1px solid #cbd5e1;">
                            {password}
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Portal:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #2563eb; font-weight: 600;">INDULJ Partner Dashboard</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Call to Action Button -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 28px 0 32px; text-align: center;">
                <tr>
                  <td align="center">
                    <a href="{login_url}" target="_blank" style="display: inline-block; background-color: #ff4d4d; color: #ffffff; text-decoration: none; font-size: 15px; font-weight: 700; padding: 15px 36px; border-radius: 12px; box-shadow: 0 6px 18px rgba(255, 77, 77, 0.35); transition: background-color 0.2s;">
                      Log In to Restaurant Dashboard →
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Feature Highlights -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 18px 0 24px; background-color: #ffffff; border: 1px solid #f1f5f9; border-radius: 12px; padding: 14px;">
                <tr>
                  <td style="padding: 8px 6px;">
                    <p style="margin: 0 0 10px; font-size: 13px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.8px;">
                      🚀 What you can do next:
                    </p>
                    <ul style="margin: 0; padding-left: 18px; font-size: 14px; color: #475569; line-height: 1.7;">
                      <li><strong>Post Daily Deals:</strong> Attract local foodies with exclusive food and beverage offers.</li>
                      <li><strong>Create Happy Hours:</strong> Drive customer traffic during key hours.</li>
                      <li><strong>Update Your Menu:</strong> Upload your menu photos and full menu document.</li>
                      <li><strong>Track Analytics:</strong> View customer reach, deal views, and engagement.</li>
                    </ul>
                  </td>
                </tr>
              </table>

              <!-- Security Advice Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border: 1px solid #fee2e2; border-radius: 12px; margin-top: 14px;">
                <tr>
                  <td style="padding: 14px 18px; font-size: 13px; color: #991b1b; line-height: 1.5;">
                    <strong>Security Reminder:</strong> Please keep your credentials confidential. For your protection, we recommend updating your password after logging in via <strong>Restaurant Profile & Settings</strong>.
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 24px 32px; text-align: center;">
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


# ─────────────────────────────────────────────────────────────
# 2. SUB-ADMIN REGISTRATION EMAIL TEMPLATE
# ─────────────────────────────────────────────────────────────

def build_sub_admin_registration_email_html(full_name, email, password, designation, unique_id, admin_type, login_url):
    role_label = "Super Admin" if admin_type == "super_admin" else "Sub-Admin / Staff Member"
    staff_display_id = unique_id or "Assigned"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to INDULJ - Administrative Account Details</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%); padding: 36px 32px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 32px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #ff4d4d;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(59, 130, 246, 0.16); border: 1px solid rgba(59, 130, 246, 0.35); color: #60a5fa; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; padding: 6px 16px; border-radius: 999px;">
                      🛡️ Sub-Admin Staff Access
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Body -->
          <tr>
            <td style="padding: 38px 36px 28px;">
              <h1 style="margin: 0 0 10px; font-size: 23px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                Welcome to the INDULJ Team! 🛡️
              </h1>
              <p style="margin: 0 0 18px; font-size: 15px; color: #475569; line-height: 1.6;">
                Hi <strong style="color: #0f172a;">{full_name}</strong>,
              </p>
              <p style="margin: 0 0 24px; font-size: 15px; color: #475569; line-height: 1.6;">
                You have been registered as an administrative staff member (<strong style="color: #2563eb;">{role_label}</strong>) on the <strong>INDULJ</strong> management platform.
              </p>

              <!-- Credentials Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 24px 0 28px; background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 16px; overflow: hidden;">
                <tr>
                  <td style="background-color: #0f172a; padding: 14px 22px;">
                    <span style="font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #ffffff;">
                      🔐 Your Administrative Credentials
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 22px;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Staff Name:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{full_name}</td>
                      </tr>
                      {f'''<tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Designation:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{designation}</td>
                      </tr>''' if designation else ''}
                      {f'''<tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Staff ID:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{staff_display_id}</td>
                      </tr>''' if unique_id else ''}
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Login Email:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 700;">{email}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Password:</td>
                        <td style="padding: 8px 0;">
                          <span style="display: inline-block; font-family: 'SF Mono', Menlo, Consolas, Monaco, monospace; font-size: 15px; font-weight: 700; color: #0f172a; background-color: #e2e8f0; padding: 5px 12px; border-radius: 6px; border: 1px solid #cbd5e1;">
                            {password}
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 8px 0; font-size: 14px; color: #64748b; width: 140px; font-weight: 600;">Portal:</td>
                        <td style="padding: 8px 0; font-size: 14px; color: #2563eb; font-weight: 600;">INDULJ Admin Portal</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Call to Action Button -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 28px 0 32px; text-align: center;">
                <tr>
                  <td align="center">
                    <a href="{login_url}" target="_blank" style="display: inline-block; background-color: #0f172a; color: #ffffff; text-decoration: none; font-size: 15px; font-weight: 700; padding: 15px 36px; border-radius: 12px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.25); transition: background-color 0.2s;">
                      Log In to Admin Dashboard →
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Key Responsibilities -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 18px 0 24px; background-color: #ffffff; border: 1px solid #f1f5f9; border-radius: 12px; padding: 14px;">
                <tr>
                  <td style="padding: 8px 6px;">
                    <p style="margin: 0 0 10px; font-size: 13px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.8px;">
                      📋 Your Key Responsibilities:
                    </p>
                    <ul style="margin: 0; padding-left: 18px; font-size: 14px; color: #475569; line-height: 1.7;">
                      <li><strong>Restaurant Onboarding:</strong> Register and manage partner restaurants under your reference.</li>
                      <li><strong>Deals & Happy Hours:</strong> Review, track, and moderate submitted deals and events.</li>
                      <li><strong>Platform Monitoring:</strong> Assist restaurants and oversee user engagement.</li>
                    </ul>
                  </td>
                </tr>
              </table>

              <!-- Security Advice Box -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fef2f2; border: 1px solid #fee2e2; border-radius: 12px; margin-top: 14px;">
                <tr>
                  <td style="padding: 14px 18px; font-size: 13px; color: #991b1b; line-height: 1.5;">
                    <strong>Security & Confidentiality:</strong> Administrative access grants privileged controls over platform data. Never share your login credentials with anyone. Please update your password after your first login.
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 24px 32px; text-align: center;">
              <p style="margin: 0 0 6px; font-size: 12px; color: #94a3b8;">
                © 2026 INDULJ. All rights reserved.
              </p>
              <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                Administrative Operations & Partner Management.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# 3. WORKERS & DISPATCH FUNCTIONS
# ─────────────────────────────────────────────────────────────

def _send_restaurant_email_worker(restaurant_name, owner_name, email, password):
    try:
        from_email = _get_from_email()
        base_url = _get_app_base_url()
        login_url = f"{base_url}/restaurant/login"

        subject = f"🍽️ Welcome to INDULJ! Account Details for {restaurant_name}"
        html_content = build_restaurant_registration_email_html(
            restaurant_name=restaurant_name,
            owner_name=owner_name,
            email=email,
            password=password,
            login_url=login_url,
        )
        text_content = (
            f"Welcome to INDULJ!\n\n"
            f"Your restaurant '{restaurant_name}' is now registered on INDULJ.\n\n"
            f"Here are your login credentials:\n"
            f"• Portal: INDULJ Restaurant Dashboard\n"
            f"• Email: {email}\n"
            f"• Password: {password}\n"
            f"• Login Link: {login_url}\n\n"
            f"Please keep these credentials safe and change your password upon first login.\n\n"
            f"— The INDULJ Team\n"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Restaurant registration credentials email sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send restaurant registration email to {email}: {e}")
        return False


def send_restaurant_registration_email(restaurant_name, owner_name, email, password):
    """
    Asynchronously sends registration credentials email to restaurant owner.
    """
    if not email or not password:
        logger.warning("Skipping restaurant registration email: missing email or password")
        return
    try:
        t = threading.Thread(
            target=_send_restaurant_email_worker,
            args=(restaurant_name, owner_name, email, password),
            daemon=True,
        )
        t.start()
    except Exception as e:
        logger.error(f"Failed to start restaurant registration email thread: {e}")


def _send_sub_admin_email_worker(full_name, email, password, designation, unique_id, admin_type):
    try:
        from_email = _get_from_email()
        base_url = _get_app_base_url()
        login_url = f"{base_url}/login"

        subject = f"🛡️ Welcome to INDULJ! Sub-Admin Access Credentials"
        html_content = build_sub_admin_registration_email_html(
            full_name=full_name,
            email=email,
            password=password,
            designation=designation,
            unique_id=unique_id,
            admin_type=admin_type,
            login_url=login_url,
        )
        text_content = (
            f"Welcome to the INDULJ Team!\n\n"
            f"You have been registered as an administrative staff member ({admin_type}) on INDULJ.\n\n"
            f"Here are your administrative credentials:\n"
            f"• Staff Name: {full_name}\n"
            f"• Designation: {designation or 'Sub-Admin'}\n"
            f"• Staff ID: {unique_id or 'Assigned'}\n"
            f"• Email: {email}\n"
            f"• Password: {password}\n"
            f"• Login Link: {login_url}\n\n"
            f"Please keep your credentials safe and confidential.\n\n"
            f"— The INDULJ Team\n"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Sub-admin registration credentials email sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send sub-admin registration email to {email}: {e}")
        return False


def send_sub_admin_registration_email(full_name, email, password, designation="", unique_id="", admin_type="employee"):
    """
    Asynchronously sends sub-admin registration credentials email to staff member.
    """
    if not email or not password:
        logger.warning("Skipping sub-admin registration email: missing email or password")
        return
    try:
        t = threading.Thread(
            target=_send_sub_admin_email_worker,
            args=(full_name, email, password, designation, unique_id, admin_type),
            daemon=True,
        )
        t.start()
    except Exception as e:
        logger.error(f"Failed to start sub-admin registration email thread: {e}")
