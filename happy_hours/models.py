from django.db import models
from accounts.models import User
from restaurants.models import Restaurant


class HappyHour(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("upcoming", "Upcoming"),
        ("draft", "Draft"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    EVENT_TYPE_CHOICES = [
        ("birthday", "Birthday"),
        ("corporate", "Corporate"),
        ("casual", "Casual"),
        ("date_night", "Date Night"),
        ("team_event", "Team Event"),
        ("family", "Family"),
        ("other", "Other"),
    ]

    VIBE_CHOICES = [
        ("casual", "Casual"),
        ("business", "Business"),
        ("fun", "Fun"),
        ("romantic", "Romantic"),
        ("family", "Family"),
    ]

    CREATED_BY_CHOICES = [
        ("user", "User"),
        ("restaurant", "Restaurant"),
        ("admin", "Admin"),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="happy_hours",
    )

    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planned_happy_hours",
    )

    created_by_role = models.CharField(
        max_length=20,
        choices=CREATED_BY_CHOICES,
        default="user",
    )

    deal = models.ForeignKey(
        "deals.Deal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_happy_hours",
    )
    is_deal = models.BooleanField(default=False)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        default="casual",
    )

    group_size = models.IntegerField(default=1)

    start_time = models.TimeField()
    end_time = models.TimeField()

    date = models.DateField(null=True, blank=True)
    days_of_week = models.JSONField(default=list, blank=True)

    vibe = models.CharField(
        max_length=20,
        choices=VIBE_CHOICES,
        default="casual",
    )

    location = models.CharField(max_length=300, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    is_public = models.BooleanField(default=True)

    discount_offer = models.CharField(max_length=100, blank=True)
    specials = models.JSONField(default=list, blank=True)

    image = models.ImageField(
        upload_to="happy_hours/",
        null=True,
        blank=True,
    )

    participants_count = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    rejection_reason = models.TextField(blank=True)
    restaurant_response = models.TextField(blank=True)

    views_count = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} @ {self.restaurant.name}"

    def is_live_now(self):
        from django.utils import timezone
        import datetime

        if self.status not in ["active", "upcoming"]:
            return False

        now = timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
        today = now.date()
        current_time = now.time()

        if self.date and self.date != today:
            return False

        if self.days_of_week and isinstance(self.days_of_week, list) and len(self.days_of_week) > 0:
            day_name = now.strftime("%A").lower()
            is_weekday = now.weekday() < 5
            is_weekend = now.weekday() >= 5

            days_lower = [str(d).lower().strip() for d in self.days_of_week]
            matches_day = (
                "everyday" in days_lower
                or "all" in days_lower
                or day_name in days_lower
                or ("weekdays" in days_lower and is_weekday)
                or ("weekends" in days_lower and is_weekend)
            )
            if not matches_day:
                return False

        if self.start_time and self.end_time:
            if self.start_time <= self.end_time:
                return self.start_time <= current_time <= self.end_time
            else:
                return current_time >= self.start_time or current_time <= self.end_time

        return self.status == "active"