import logging
import html
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from decouple import config

logger = logging.getLogger(__name__)


def get_superadmin_contact_recipients():
    """
    Get recipient email list for contact inquiries.
    Configured via SUPERADMIN_CONTACT_EMAIL in settings or .env.
    """
    admin_email_setting = getattr(settings, "SUPERADMIN_CONTACT_EMAIL", None)
    if not admin_email_setting:
        admin_email_setting = config(
            "SUPERADMIN_CONTACT_EMAIL",
            default=config("EMAIL_HOST_USER", default="admin@indulj.com")
        )

    if isinstance(admin_email_setting, str):
        recipients = [e.strip() for e in admin_email_setting.split(",") if e.strip()]
    elif isinstance(admin_email_setting, (list, tuple)):
        recipients = [str(e).strip() for e in admin_email_setting if str(e).strip()]
    else:
        recipients = ["admin@indulj.com"]

    return recipients if recipients else ["admin@indulj.com"]


def build_contact_email_html(contact_message, admin_recipient=""):
    """
    Generates a high-quality, modern, responsive HTML email template for the SuperAdmin.
    """
    name = html.escape(contact_message.name or "Guest")
    email = html.escape(contact_message.email or "")
    phone = html.escape(contact_message.phone or "Not provided")
    inquiry_label = html.escape(contact_message.get_inquiry_type_display())
    subject = html.escape(contact_message.subject or "No Subject")
    safe_message = html.escape(contact_message.message or "").replace("\n", "<br>")
    submitted_at = contact_message.created_at.strftime("%B %d, %Y at %I:%M %p UTC") if contact_message.created_at else "Just now"

    user_status = "Registered User" if contact_message.user else "Guest Visitor"
    user_status_color = "#059669" if contact_message.user else "#64748b"
    user_status_bg = "#ecfdf5" if contact_message.user else "#f1f5f9"

    # Category color badge
    cat_badge_bg = "rgba(255, 77, 77, 0.12)"
    cat_badge_color = "#ff4d4d"
    if contact_message.inquiry_type in ["support", "bug"]:
        cat_badge_bg = "rgba(239, 68, 68, 0.12)"
        cat_badge_color = "#dc2626"
    elif contact_message.inquiry_type == "restaurant":
        cat_badge_bg = "rgba(38, 174, 96, 0.12)"
        cat_badge_color = "#26ae60"

    mail_to_link = f"mailto:{email}?subject=Re:%20{html.escape(subject)}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New Contact Inquiry: {subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; -webkit-font-smoothing: antialiased; line-height: 1.5;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 18px; overflow: hidden; box-shadow: 0 12px 36px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%); padding: 36px 32px 30px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 30px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #ff4d4d;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(255, 77, 77, 0.16); border: 1px solid rgba(255, 77, 77, 0.35); color: #ff6b6b; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; padding: 5px 14px; border-radius: 999px;">
                      📬 New Contact Inquiry
                    </span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 10px;">
                    <span style="color: #94a3b8; font-size: 13px;">SuperAdmin Notification Portal</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Section -->
          <tr>
            <td style="padding: 32px 32px 28px;">
              <h1 style="margin: 0 0 8px; font-size: 20px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                You have received a new contact message
              </h1>
              <p style="margin: 0 0 24px; font-size: 14px; color: #64748b;">
                Received on <strong style="color: #334155;">{submitted_at}</strong>
              </p>

              <!-- Sender Details Grid Card -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 24px;">
                <tr>
                  <td style="padding: 18px 20px;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="6">
                      <tr>
                        <td width="35%" style="font-size: 13px; font-weight: 600; color: #64748b;">Sender Name:</td>
                        <td width="65%" style="font-size: 14px; font-weight: 700; color: #0f172a;">{name}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; font-weight: 600; color: #64748b;">Email Address:</td>
                        <td style="font-size: 14px; font-weight: 600; color: #2563eb;">
                          <a href="mailto:{email}" style="color: #2563eb; text-decoration: underline;">{email}</a>
                        </td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; font-weight: 600; color: #64748b;">Phone Number:</td>
                        <td style="font-size: 14px; color: #334155;">{phone}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; font-weight: 600; color: #64748b;">Category:</td>
                        <td>
                          <span style="display: inline-block; background-color: {cat_badge_bg}; color: {cat_badge_color}; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px;">
                            {inquiry_label}
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; font-weight: 600; color: #64748b;">User Status:</td>
                        <td>
                          <span style="display: inline-block; background-color: {user_status_bg}; color: {user_status_color}; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 4px;">
                            {user_status}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Subject Card -->
              <div style="margin-bottom: 16px;">
                <span style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: #64748b; display: block; margin-bottom: 6px;">
                  Subject
                </span>
                <div style="background-color: #f1f5f9; padding: 12px 16px; border-radius: 8px; font-size: 16px; font-weight: 700; color: #0f172a; border-left: 4px solid #ff4d4d;">
                  {subject}
                </div>
              </div>

              <!-- Message Body -->
              <div style="margin-bottom: 28px;">
                <span style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: #64748b; display: block; margin-bottom: 6px;">
                  Message Content
                </span>
                <div style="background-color: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 18px 20px; font-size: 15px; color: #334155; line-height: 1.7;">
                  {safe_message}
                </div>
              </div>

              <!-- Quick Action Button -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                <tr>
                  <td align="center">
                    <a href="{mail_to_link}" style="display: inline-block; background-color: #ff4d4d; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 700; padding: 14px 28px; border-radius: 10px; box-shadow: 0 4px 14px rgba(255, 77, 77, 0.35);">
                      ✉️ Reply to {name}
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Configuration Notice for User -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-radius: 8px; border: 1px dashed #cbd5e1;">
                <tr>
                  <td style="padding: 12px 16px; font-size: 12px; color: #64748b; line-height: 1.5;">
                    ⚙️ <strong>Admin Notice:</strong> Delivered to: <span style="color: #0f172a; font-weight: 600;">{admin_recipient}</span>. You can change this destination email anytime by setting <code style="background-color: #e2e8f0; padding: 2px 4px; border-radius: 4px; color: #0f172a;">SUPERADMIN_CONTACT_EMAIL</code> in your backend <code style="background-color: #e2e8f0; padding: 2px 4px; border-radius: 4px; color: #0f172a;">.env</code>.
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
                Automated SuperAdmin Notification System • Website Contact Page
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_contact_email_to_admin(contact_message):
    """
    Sends an email to the configured SuperAdmin email with contact message details.
    Returns (success: bool, info: str).
    """
    recipients = get_superadmin_contact_recipients()
    recipient_display = ", ".join(recipients)

    subject = f"[INDULJ Contact] {contact_message.subject} (from {contact_message.name})"
    text_content = (
        f"NEW CONTACT INQUIRY - INDULJ\n"
        f"=========================================\n\n"
        f"From: {contact_message.name} <{contact_message.email}>\n"
        f"Phone: {contact_message.phone or 'Not provided'}\n"
        f"Category: {contact_message.get_inquiry_type_display()}\n"
        f"User Status: {'Registered User' if contact_message.user else 'Guest Visitor'}\n"
        f"Date: {contact_message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if contact_message.created_at else 'N/A'}\n\n"
        f"Subject: {contact_message.subject}\n"
        f"-----------------------------------------\n"
        f"Message:\n{contact_message.message}\n"
        f"-----------------------------------------\n\n"
        f"Reply directly to: {contact_message.email}\n"
        f"Sent to configured SuperAdmin: {recipient_display}\n"
    )

    html_content = build_contact_email_html(contact_message, admin_recipient=recipient_display)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or config(
        "DEFAULT_FROM_EMAIL",
        default=config("EMAIL_HOST_USER", default="noreply@indulj.app")
    )
    if not from_email or "@" not in from_email:
        from_email = "INDULJ Contact <noreply@indulj.app>"

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients,
            reply_to=[contact_message.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Contact email sent successfully to {recipient_display} for message ID {contact_message.id}")
        return True, "Email sent successfully"
    except Exception as e:
        logger.error(f"Failed to send contact email to {recipient_display}: {e}")
        return False, str(e)
