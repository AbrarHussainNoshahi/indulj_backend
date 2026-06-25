import random
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from restaurants.models import Restaurant
from deals.models import Deal
from happy_hours.models import HappyHour


def generate_order_number():
    digits = "".join(random.choices(string.digits, k=6))
    number = f"ORD-{digits}"

    while Order.objects.filter(order_number=number).exists():
        digits = "".join(random.choices(string.digits, k=6))
        number = f"ORD-{digits}"

    return number


class Order(models.Model):
    ORDER_TYPE_CHOICES = [
        ("deal", "Deal"),
        ("happy_hour", "Happy Hour"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
    ]

    order_number = models.CharField(max_length=30, unique=True, blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    deal = models.ForeignKey(
        Deal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    happy_hour = models.ForeignKey(
        HappyHour,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    items = models.JSONField(default=list, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    group_size = models.PositiveIntegerField(default=1)

    booking_date = models.DateField(null=True, blank=True)
    booking_time = models.TimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default="")
    restaurant_response = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    confirmed_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number} - {self.order_type} - {self.status}"

    def clean(self):
        if self.deal and self.happy_hour:
            raise ValidationError("Order cannot have both deal and happy hour.")

        if not self.deal and not self.happy_hour:
            raise ValidationError("Order must have either deal or happy hour.")

        if self.order_type == "deal" and not self.deal:
            raise ValidationError("Deal order must include a deal.")

        if self.order_type == "happy_hour" and not self.happy_hour:
            raise ValidationError("Happy hour order must include a happy hour.")

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = generate_order_number()

        if self.deal:
            self.order_type = "deal"
            self.restaurant = self.deal.restaurant

        if self.happy_hour:
            self.order_type = "happy_hour"
            self.restaurant = self.happy_hour.restaurant

        self.full_clean()
        super().save(*args, **kwargs)

    def mark_confirmed(self, response=""):
        self.status = "confirmed"
        self.restaurant_response = response or ""
        self.confirmed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "restaurant_response",
                "confirmed_at",
                "updated_at",
            ]
        )

    def mark_rejected(self, reason=""):
        self.status = "rejected"
        self.rejection_reason = reason or ""
        self.rejected_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "rejection_reason",
                "rejected_at",
                "updated_at",
            ]
        )

    def mark_cancelled(self):
        self.status = "cancelled"
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])

    def mark_completed(self):
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])