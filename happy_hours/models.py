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