from django.db import models
from accounts.models import User
from restaurants.models import Restaurant


class Deal(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("draft", "Draft"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    FOOD_TYPE_CHOICES = [
        ("mexican", "Mexican"),
        ("italian", "Italian"),
        ("japanese", "Japanese"),
        ("chinese", "Chinese"),
        ("fast_food", "Fast Food"),
        ("bbq", "BBQ"),
        ("cafe", "Cafe"),
        ("desi", "Desi"),
        ("steak", "Steak"),
        ("thai", "Thai"),
        ("pizza", "Pizza"),
        ("bar", "Bar"),
        ("grill", "Grill"),
        ("american", "American"),
        ("other", "Other"),
    ]

    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
        ("everyday", "Everyday"),
        ("weekdays", "Weekdays"),
        ("weekends", "Weekends"),
    ]

    CREATED_BY_CHOICES = [
        ("user", "User"),
        ("restaurant", "Restaurant"),
        ("admin", "Admin"),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="deals",
    )

    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_deals",
    )

    created_by_role = models.CharField(
        max_length=20,
        choices=CREATED_BY_CHOICES,
        default="user",
    )

    title = models.CharField(max_length=200)
    description = models.TextField()

    price = models.DecimalField(max_digits=8, decimal_places=2)

    food_type = models.CharField(
        max_length=50,
        choices=FOOD_TYPE_CHOICES,
        default="other",
    )

    day_of_week = models.CharField(
        max_length=20,
        choices=DAY_CHOICES,
        default="everyday",
    )

    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    has_time_slots = models.BooleanField(default=False)

    location_branch = models.CharField(max_length=300, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    rejection_reason = models.TextField(blank=True)
    discount_percentage = models.CharField(max_length=20, blank=True)

    image = models.ImageField(upload_to="deals/", null=True, blank=True)

    views_count = models.IntegerField(default=0)
    redemptions_count = models.IntegerField(default=0)
    is_hot_deal = models.BooleanField(default=False)

    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} — {self.restaurant.name}"


class SavedDeal(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_deals",
    )

    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="saved_by",
    )

    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "deal"]
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.user.full_name} saved {self.deal.title}"

class DealView(models.Model):
    deal = models.ForeignKey("Deal", on_delete=models.CASCADE, related_name="deal_views")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    session_id = models.CharField(max_length=255, null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("deal", "session_id", "user")