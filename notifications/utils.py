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
        
        now = timezone.now()
        # Find active or upcoming happy hours with specific date
        qs = HappyHour.objects.filter(
            status__in=["active", "upcoming"],
            date__isnull=False
        )
        
        for hh in qs:
            # Combine date and end_time
            end_datetime = datetime.datetime.combine(hh.date, hh.end_time)
            if timezone.is_aware(now):
                current_tz = timezone.get_current_timezone()
                end_datetime = timezone.make_aware(end_datetime, current_tz)
                
            if now > end_datetime:
                hh.status = "expired"
                hh.save(update_fields=["status", "updated_at"])
                
                # Notify user
                if hh.submitted_by:
                    create_notification(
                        user=hh.submitted_by,
                        type="happy_hour",
                        title="Happy Hour Ended",
                        message=f"Your planned happy hour '{hh.title}' at {hh.restaurant.name} has ended.",
                        related_happy_hour=hh
                    )
                # Notify restaurant owner
                if hh.restaurant.owner:
                    create_notification(
                        user=hh.restaurant.owner,
                        type="happy_hour",
                        title="Happy Hour Ended",
                        message=f"The planned happy hour '{hh.title}' has ended.",
                        related_happy_hour=hh
                    )
    except Exception:
        pass
