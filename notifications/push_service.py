import json
import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_cached_credentials = None
_cached_project_id = None

def get_firebase_credentials():
    """
    Attempts to load Firebase service account credentials using google-auth.
    Looks for:
    1. settings.FIREBASE_SERVICE_ACCOUNT_PATH or os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
    2. settings.FIREBASE_SERVICE_ACCOUNT_JSON or os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    3. File named 'firebase-service-account.json' in backend root
    """
    global _cached_credentials, _cached_project_id

    if _cached_credentials and _cached_credentials.valid:
        return _cached_credentials, _cached_project_id

    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests

        scopes = ['https://www.googleapis.com/auth/firebase.messaging']
        path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', None) or os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
        raw_json = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_JSON', None) or os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')

        creds = None
        project_id = None

        if path and os.path.exists(path):
            creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
            project_id = creds.project_id
        elif raw_json:
            info = json.loads(raw_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            project_id = creds.project_id
        else:
            default_path = os.path.join(settings.BASE_DIR, 'firebase-service-account.json')
            if os.path.exists(default_path):
                creds = service_account.Credentials.from_service_account_file(default_path, scopes=scopes)
                project_id = creds.project_id

        if creds:
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            _cached_credentials = creds
            _cached_project_id = project_id or getattr(settings, 'FIREBASE_PROJECT_ID', None) or os.environ.get('FIREBASE_PROJECT_ID')
            return _cached_credentials, _cached_project_id

    except Exception as e:
        logger.warning(f"Error initializing Firebase credentials: {e}")

    return None, getattr(settings, 'FIREBASE_PROJECT_ID', None) or os.environ.get('FIREBASE_PROJECT_ID')


def send_push_notification(notification):
    """
    Dispatches FCM HTTP v1 push notifications to all active device tokens belonging to notification.user.
    Supports both iOS and Android.
    """
    try:
        from .models import DeviceToken

        if not notification or not notification.user:
            return

        active_devices = list(DeviceToken.objects.filter(
            user=notification.user,
            is_active=True
        ))

        if not active_devices:
            return

        creds, project_id = get_firebase_credentials()
        if not creds or not project_id:
            logger.info(
                f"[PushNotification] FCM credentials not configured. "
                f"Skipping network push for notification #{notification.id} ('{notification.title}'). "
                f"Active devices found: {len(active_devices)}."
            )
            return

        unread_count = getattr(notification.user, 'notifications', None)
        if unread_count:
            unread_count = notification.user.notifications.filter(is_read=False).count()
        else:
            unread_count = 1

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json; UTF-8',
        }

        # Build cross-platform data dictionary (values must be strings)
        data_payload = {
            'notification_id': str(notification.id),
            'type': str(notification.type or ''),
            'title': str(notification.title or ''),
            'message': str(notification.message or ''),
            'action_url': str(notification.action_url or ''),
            'restaurant_id': str(notification.related_restaurant_id or ''),
            'deal_id': str(notification.related_deal_id or ''),
            'happy_hour_id': str(notification.related_happy_hour_id or ''),
            'order_id': str(notification.related_order_id or ''),
        }

        # Include metadata flags (e.g. action_type for review modals)
        if notification.metadata and isinstance(notification.metadata, dict):
            for k, v in notification.metadata.items():
                if v is not None:
                    data_payload[str(k)] = str(v)

        for device in active_devices:
            message_body = {
                "message": {
                    "token": device.registration_id,
                    "notification": {
                        "title": notification.title,
                        "body": notification.message,
                    },
                    "data": data_payload,
                    "android": {
                        "priority": "HIGH",
                        "notification": {
                            "sound": "default",
                            "click_action": "FCM_PLUGIN_ACTIVITY",
                            "channel_id": "default",
                        }
                    },
                    "apns": {
                        "payload": {
                            "aps": {
                                "sound": "default",
                                "badge": unread_count,
                                "content-available": 1,
                            }
                        }
                    }
                }
            }

            try:
                resp = requests.post(url, headers=headers, json=message_body, timeout=10)
                if resp.status_code == 200:
                    logger.debug(f"Push sent successfully to device {device.id} ({device.platform})")
                else:
                    err_text = resp.text
                    logger.warning(f"Push failed for device {device.id} [{resp.status_code}]: {err_text}")
                    # Invalidate token if unregistered / not found
                    if "UNREGISTERED" in err_text or "NOT_FOUND" in err_text or resp.status_code == 404:
                        device.is_active = False
                        device.save(update_fields=['is_active'])
            except Exception as device_err:
                logger.warning(f"Error sending push to device {device.id}: {device_err}")

    except Exception as e:
        logger.warning(f"send_push_notification error: {e}")
