import uuid
from django.utils import timezone


def get_client_ip(request):
    """Extract real IP from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def parse_user_agent(ua_string):
    """
    Parse browser and OS from User-Agent string.
    Basic parsing without extra packages.
    """
    ua = ua_string or ''

    # ── Browser ───────────────────────────────────────────
    if 'Chrome' in ua and 'Edg' not in ua and 'OPR' not in ua:
        browser = 'Chrome'
    elif 'Firefox' in ua:
        browser = 'Firefox'
    elif 'Safari' in ua and 'Chrome' not in ua:
        browser = 'Safari'
    elif 'Edg' in ua:
        browser = 'Edge'
    elif 'OPR' in ua or 'Opera' in ua:
        browser = 'Opera'
    else:
        browser = 'Unknown Browser'

    # ── OS ────────────────────────────────────────────────
    if 'Windows' in ua:
        os_name = 'Windows'
    elif 'Mac OS X' in ua and 'iPhone' not in ua and 'iPad' not in ua:
        os_name = 'macOS'
    elif 'iPhone' in ua:
        os_name = 'iPhone'
    elif 'iPad' in ua:
        os_name = 'iPad'
    elif 'Android' in ua:
        os_name = 'Android'
    elif 'Linux' in ua:
        os_name = 'Linux'
    else:
        os_name = 'Unknown OS'

    # ── Device type ───────────────────────────────────────
    device = 'Mobile' if any(
        m in ua for m in ['Mobile', 'iPhone', 'Android', 'iPad']
    ) else 'Desktop'

    return {
        'browser':     browser,
        'os':          os_name,
        'device':      device,
        'device_info': f"{browser} on {os_name} ({device})",
    }


def create_session(user, request):
    """
    Create a new session entry.
    Returns (session, session_key) tuple.
    session_key is embedded in the JWT.
    """
    from accounts.models import UserSession

    ip          = get_client_ip(request)
    ua_string   = request.META.get('HTTP_USER_AGENT', '')
    parsed      = parse_user_agent(ua_string)
    session_key = str(uuid.uuid4())

    # Mark all previous sessions as not current (for this device/login)
    # Note: We do NOT set is_revoked=True for other sessions, only is_current=False,
    # so they remain valid sessions unless explicitly revoked.
    UserSession.objects.filter(user=user, is_current=True).update(is_current=False)

    session = UserSession.objects.create(
        user        = user,
        session_key = session_key,
        device_info = parsed['device_info'],
        browser     = parsed['browser'],
        os          = parsed['os'],
        ip_address  = ip,
        is_current  = True,
        is_revoked  = False,
    )
    return session, session_key


def update_session_activity(user, session_key):
    """Silently update last_active for the current session."""
    from accounts.models import UserSession
    try:
        UserSession.objects.filter(
            user=user,
            session_key=session_key,
        ).update(last_active=timezone.now())
    except Exception:
        pass
