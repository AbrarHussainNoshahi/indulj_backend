from accounts.models import User

def create_notification(
    user,
    type,
    title,
    message,
    related_order=None,
    related_deal=None,
    related_happy_hour=None,
    related_restaurant=None,
    metadata=None
):
    try:
        from .models import Notification
        if metadata is None:
            metadata = {}
        return Notification.objects.create(
            user=user,
            type=type,
            title=title,
            message=message,
            related_order=related_order,
            related_deal=related_deal,
            related_happy_hour=related_happy_hour,
            related_restaurant=related_restaurant,
            metadata=metadata
        )
    except Exception:
        return None

def notify_admins(
    type,
    title,
    message,
    related_order=None,
    related_deal=None,
    related_happy_hour=None,
    related_restaurant=None,
    metadata=None
):
    try:
        admins = User.objects.filter(role='admin', is_active=True)
        for admin in admins:
            create_notification(
                user=admin,
                type=type,
                title=title,
                message=message,
                related_order=related_order,
                related_deal=related_deal,
                related_happy_hour=related_happy_hour,
                related_restaurant=related_restaurant,
                metadata=metadata
            )
    except Exception:
        pass

def check_and_expire_happy_hours():
    try:
        import datetime
        from django.utils import timezone
        from happy_hours.models import HappyHour
        from .models import Notification

        now = timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
        current_tz = timezone.get_current_timezone() if timezone.is_aware(timezone.now()) else None

        # Find active or upcoming happy hours
        qs = HappyHour.objects.filter(
            status__in=["active", "upcoming"]
        ).select_related("restaurant", "submitted_by", "restaurant__owner")

        def _notif_exists(user, hh, title):
            if not user:
                return False
            return Notification.objects.filter(user=user, related_happy_hour=hh, title=title).exists()

        def _admin_notif_exists(hh, title):
            return Notification.objects.filter(user__role='admin', related_happy_hour=hh, title=title).exists()

        def _alert_all(hh, title, user_msg, rest_msg, admin_msg):
            if hh.submitted_by and not _notif_exists(hh.submitted_by, hh, title):
                create_notification(
                    user=hh.submitted_by,
                    type="happy_hour",
                    title=title,
                    message=user_msg,
                    related_happy_hour=hh,
                    metadata={"alert_type": title}
                )
            if hh.restaurant and hh.restaurant.owner and hh.restaurant.owner != hh.submitted_by and not _notif_exists(hh.restaurant.owner, hh, title):
                create_notification(
                    user=hh.restaurant.owner,
                    type="happy_hour",
                    title=title,
                    message=rest_msg,
                    related_happy_hour=hh,
                    metadata={"alert_type": title}
                )
            if not _admin_notif_exists(hh, title):
                notify_admins(
                    type="happy_hour",
                    title=title,
                    message=admin_msg,
                    related_happy_hour=hh,
                    metadata={"alert_type": title}
                )

        for hh in qs:
            target_date = hh.date or now.date()
            if not hh.start_time or not hh.end_time:
                continue

            start_datetime = datetime.datetime.combine(target_date, hh.start_time)
            end_datetime = datetime.datetime.combine(target_date, hh.end_time)

            if current_tz:
                start_datetime = timezone.make_aware(start_datetime, current_tz)
                end_datetime = timezone.make_aware(end_datetime, current_tz)

            # 1. Check if Happy Hour has Ended / Expired
            if now >= end_datetime:
                if hh.status != "expired":
                    hh.status = "expired"
                    hh.save(update_fields=["status", "updated_at"])

                _alert_all(
                    hh,
                    title="Happy Hour Ended",
                    user_msg=f"Your happy hour '{hh.title}' at {hh.restaurant.name} has ended.",
                    rest_msg=f"Happy hour '{hh.title}' at your restaurant has ended.",
                    admin_msg=f"Happy hour '{hh.title}' at {hh.restaurant.name} has ended."
                )

            # 2. Check if Happy Hour is LIVE / Currently active
            elif now >= start_datetime and now < end_datetime:
                if hh.status == "upcoming":
                    hh.status = "active"
                    hh.save(update_fields=["status", "updated_at"])

                _alert_all(
                    hh,
                    title="Happy Hour Started! 🍻",
                    user_msg=f"Your happy hour '{hh.title}' at {hh.restaurant.name} is now LIVE!",
                    rest_msg=f"Happy hour '{hh.title}' is now LIVE at your restaurant.",
                    admin_msg=f"Happy hour '{hh.title}' at {hh.restaurant.name} is now LIVE."
                )

                # Check if Ending Soon (within 30 minutes before end_datetime)
                time_to_end = (end_datetime - now).total_seconds()
                if 0 < time_to_end <= 1800:
                    _alert_all(
                        hh,
                        title="Happy Hour Ending Soon! ⏳",
                        user_msg=f"Your happy hour '{hh.title}' at {hh.restaurant.name} will end in less than 30 minutes.",
                        rest_msg=f"Happy hour '{hh.title}' will end in less than 30 minutes.",
                        admin_msg=f"Happy hour '{hh.title}' at {hh.restaurant.name} will end in less than 30 minutes."
                    )

            # 3. Check if Starting Soon (within 30 minutes before start_datetime)
            elif now < start_datetime:
                time_to_start = (start_datetime - now).total_seconds()
                if 0 < time_to_start <= 1800:
                    _alert_all(
                        hh,
                        title="Happy Hour Starting Soon! ⏰",
                        user_msg=f"Your happy hour '{hh.title}' at {hh.restaurant.name} starts in less than 30 minutes.",
                        rest_msg=f"Happy hour '{hh.title}' starts in less than 30 minutes at your restaurant.",
                        admin_msg=f"Happy hour '{hh.title}' at {hh.restaurant.name} starts in less than 30 minutes."
                    )

    except Exception:
        pass
