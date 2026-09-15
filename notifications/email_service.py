import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _get_app_base_url():
    # Can be configured via settings or environment
    return getattr(settings, "FRONTEND_URL", "https://indulj.vercel.app")


def build_deal_email_html(deal, user):
    base_url = _get_app_base_url()
    restaurant_name = deal.restaurant.name if deal.restaurant else "Partner Restaurant"
    location = deal.location_branch or (deal.restaurant.address if deal.restaurant else "") or (deal.restaurant.city if deal.restaurant else "")
    deal_url = f"{base_url}/deals/{deal.id}"
    settings_url = f"{base_url}/user_set"

    price_str = f"${deal.price}" if deal.price is not None else ""
    discount_str = f"{deal.discount_percentage}% OFF" if deal.discount_percentage else ""
    user_name = user.full_name or user.display_username or "Foodie"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New Deal Alert: {deal.title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 12px;">
    <tr>
      <td align="center">
        <!-- Main Container -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #111827 0%, #1f2937 100%); padding: 32px 28px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 28px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #ff4d4d;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(255, 77, 77, 0.18); border: 1px solid rgba(255, 77, 77, 0.35); color: #ff6b6b; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; padding: 5px 14px; border-radius: 999px;">
                      🔥 Fresh Deal Alert
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 28px 20px;">
              <h1 style="margin: 0 0 10px; font-size: 22px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                Hey {user_name}! A new deal was just published!
              </h1>
              <p style="margin: 0 0 24px; font-size: 15px; color: #64748b; line-height: 1.6;">
                Great food at great prices. Check out the latest exclusive deal available for you on INDULJ:
              </p>

              <!-- Deal Showcase Card -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fffaf0; border: 1.5px solid #fed7aa; border-radius: 16px; overflow: hidden; margin-bottom: 26px;">
                <tr>
                  <td style="padding: 24px;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td>
                          <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #ea580c; letter-spacing: 0.5px;">
                            📍 {restaurant_name}
                          </span>
                          <h2 style="margin: 6px 0 12px; font-size: 20px; font-weight: 800; color: #1e293b; line-height: 1.3;">
                            {deal.title}
                          </h2>
                          <p style="margin: 0 0 16px; font-size: 14px; color: #475569; line-height: 1.5;">
                            {deal.description}
                          </p>
                        </td>
                      </tr>
                      <tr>
                        <td>
                          <table border="0" cellspacing="0" cellpadding="0">
                            <tr>
                              {f'<td style="background-color: #ff4d4d; color: #ffffff; font-weight: 800; font-size: 16px; padding: 6px 14px; border-radius: 10px; margin-right: 8px;">{price_str}</td>' if price_str else ''}
                              {f'<td style="padding-left: 8px;"><span style="background-color: #dcfce7; color: #166534; font-weight: 800; font-size: 13px; padding: 6px 12px; border-radius: 8px; border: 1px solid #bbf7d0;">{discount_str}</span></td>' if discount_str else ''}
                            </tr>
                          </table>
                        </td>
                      </tr>
                      {f'<tr><td style="padding-top: 14px; font-size: 13px; color: #64748b;">📍 {location}</td></tr>' if location else ''}
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Call to Action Button -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center" style="padding: 10px 0 24px;">
                    <a href="{deal_url}" target="_blank" style="display: inline-block; background-color: #ff4d4d; color: #ffffff; font-size: 16px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 12px; box-shadow: 0 4px 14px rgba(255, 77, 77, 0.4); text-align: center;">
                      Claim & View Deal
                    </a>
                  </td>
                </tr>
              </table>

              <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 10px 0 20px;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; padding: 22px 28px; text-align: center; border-top: 1px solid #e2e8f0;">
              <p style="margin: 0 0 8px; font-size: 12px; color: #94a3b8; line-height: 1.5;">
                You received this email because <strong>Email notifications for deals</strong> is enabled in your INDULJ account settings.
              </p>
              <p style="margin: 0; font-size: 12px; color: #64748b;">
                <a href="{settings_url}" target="_blank" style="color: #ff4d4d; text-decoration: none; font-weight: 600;">
                  Manage Notification Preferences
                </a>
                &nbsp;•&nbsp;
                <a href="{base_url}" target="_blank" style="color: #64748b; text-decoration: none;">
                  INDULJ
                </a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_happy_hour_email_html(happy_hour, user):
    base_url = _get_app_base_url()
    restaurant_name = happy_hour.restaurant.name if happy_hour.restaurant else "Partner Venue"
    location = happy_hour.location or (happy_hour.restaurant.address if happy_hour.restaurant else "") or (happy_hour.restaurant.city if happy_hour.restaurant else "")
    hh_url = f"{base_url}/happy-hours/{happy_hour.id}"
    settings_url = f"{base_url}/user_set"

    time_str = ""
    if happy_hour.start_time and happy_hour.end_time:
        time_str = f"{str(happy_hour.start_time)[:5]} - {str(happy_hour.end_time)[:5]}"
    date_str = str(happy_hour.date) if happy_hour.date else "Recurring / Scheduled"

    discount_str = happy_hour.discount_offer or "Happy Hour Specials Available"
    user_name = user.full_name or user.display_username or "Friend"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Happy Hour Alert: {happy_hour.title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 12px;">
    <tr>
      <td align="center">
        <!-- Main Container -->
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #064e3b 0%, #0f766e 100%); padding: 32px 28px; text-align: center;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center">
                    <span style="font-size: 28px; font-weight: 900; letter-spacing: -1px; color: #ffffff;">INDULJ<span style="color: #34d399;">.</span></span>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-top: 14px;">
                    <span style="display: inline-block; background-color: rgba(52, 211, 153, 0.2); border: 1px solid rgba(52, 211, 153, 0.4); color: #6ee7b7; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; padding: 5px 14px; border-radius: 999px;">
                      🍸 New Happy Hour Announced
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 28px 20px;">
              <h1 style="margin: 0 0 10px; font-size: 22px; font-weight: 800; color: #0f172a; line-height: 1.3;">
                Hey {user_name}! A new Happy Hour is coming up!
              </h1>
              <p style="margin: 0 0 24px; font-size: 15px; color: #64748b; line-height: 1.6;">
                Get your friends together. Check out this new Happy Hour event on INDULJ:
              </p>

              <!-- Happy Hour Showcase Card -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 16px; overflow: hidden; margin-bottom: 26px;">
                <tr>
                  <td style="padding: 24px;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td>
                          <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #059669; letter-spacing: 0.5px;">
                            📍 {restaurant_name}
                          </span>
                          <h2 style="margin: 6px 0 12px; font-size: 20px; font-weight: 800; color: #1e293b; line-height: 1.3;">
                            {happy_hour.title}
                          </h2>
                          <p style="margin: 0 0 16px; font-size: 14px; color: #475569; line-height: 1.5;">
                            {happy_hour.description}
                          </p>
                        </td>
                      </tr>
                      <tr>
                        <td>
                          <table border="0" cellspacing="0" cellpadding="0">
                            <tr>
                              <td style="background-color: #059669; color: #ffffff; font-weight: 800; font-size: 13px; padding: 6px 14px; border-radius: 10px;">
                                {discount_str}
                              </td>
                              {f'<td style="padding-left: 8px; font-size: 13px; font-weight: 700; color: #065f46;">⏰ {time_str}</td>' if time_str else ''}
                            </tr>
                          </table>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding-top: 14px; font-size: 13px; color: #64748b;">
                          📅 Date: <strong>{date_str}</strong> {f'• 📍 {location}' if location else ''}
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Call to Action Button -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="center" style="padding: 10px 0 24px;">
                    <a href="{hh_url}" target="_blank" style="display: inline-block; background-color: #059669; color: #ffffff; font-size: 16px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 12px; box-shadow: 0 4px 14px rgba(5, 150, 105, 0.35); text-align: center;">
                      View Happy Hour Details
                    </a>
                  </td>
                </tr>
              </table>

              <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 10px 0 20px;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; padding: 22px 28px; text-align: center; border-top: 1px solid #e2e8f0;">
              <p style="margin: 0 0 8px; font-size: 12px; color: #94a3b8; line-height: 1.5;">
                You received this email because <strong>Email notifications for Happy Hours</strong> is enabled in your INDULJ account settings.
              </p>
              <p style="margin: 0; font-size: 12px; color: #64748b;">
                <a href="{settings_url}" target="_blank" style="color: #059669; text-decoration: none; font-weight: 600;">
                  Manage Notification Preferences
                </a>
                &nbsp;•&nbsp;
                <a href="{base_url}" target="_blank" style="color: #64748b; text-decoration: none;">
                  INDULJ
                </a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_deal_emails_worker(deal_id):
    try:
        from deals.models import Deal
        from accounts.models import NotificationPreference

        deal = Deal.objects.select_related("restaurant", "submitted_by").get(pk=deal_id)
        if deal.status != "active":
            return

        # Query all users where email_deals is enabled
        prefs = NotificationPreference.objects.filter(
            email_deals=True,
            user__is_active=True,
        ).select_related("user")

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@indulj.com")

        for pref in prefs:
            user = pref.user
            if not user.email:
                continue

            try:
                subject = f"🔥 New Deal Alert: {deal.title} at {deal.restaurant.name if deal.restaurant else 'INDULJ'}"
                html_content = build_deal_email_html(deal, user)
                text_content = strip_tags(html_content)

                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=from_email,
                    to=[user.email],
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=True)
            except Exception as e:
                logger.error(f"Failed to send deal email to {user.email}: {e}")

    except Exception as exc:
        logger.error(f"Error in deal email worker: {exc}")


def send_deal_notification_emails(deal):
    """
    Asynchronously dispatches emails for an active deal to all opted-in users.
    """
    try:
        if not deal or deal.status != "active":
            return
        t = threading.Thread(target=_send_deal_emails_worker, args=(deal.id,), daemon=True)
        t.start()
    except Exception as e:
        logger.error(f"Failed to start deal notification thread: {e}")


def _send_happy_hour_emails_worker(happy_hour_id):
    try:
        from happy_hours.models import HappyHour
        from accounts.models import NotificationPreference

        happy_hour = HappyHour.objects.select_related("restaurant", "submitted_by").get(pk=happy_hour_id)
        if happy_hour.status not in ["active", "upcoming"]:
            return

        # Query all users where email_happy_hours is enabled
        prefs = NotificationPreference.objects.filter(
            email_happy_hours=True,
            user__is_active=True,
        ).select_related("user")

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@indulj.com")

        for pref in prefs:
            user = pref.user
            if not user.email:
                continue

            try:
                subject = f"🍸 Happy Hour Alert: {happy_hour.title} at {happy_hour.restaurant.name if happy_hour.restaurant else 'INDULJ'}"
                html_content = build_happy_hour_email_html(happy_hour, user)
                text_content = strip_tags(html_content)

                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=from_email,
                    to=[user.email],
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=True)
            except Exception as e:
                logger.error(f"Failed to send happy hour email to {user.email}: {e}")

    except Exception as exc:
        logger.error(f"Error in happy hour email worker: {exc}")


def send_happy_hour_notification_emails(happy_hour):
    """
    Asynchronously dispatches emails for an active/upcoming happy hour to all opted-in users.
    """
    try:
        if not happy_hour or happy_hour.status not in ["active", "upcoming"]:
            return
        t = threading.Thread(target=_send_happy_hour_emails_worker, args=(happy_hour.id,), daemon=True)
        t.start()
    except Exception as e:
        logger.error(f"Failed to start happy hour notification thread: {e}")
