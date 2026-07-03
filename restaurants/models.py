from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User


class Restaurant(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("newly_joined", "Newly Joined"),
    ]

    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="restaurant",
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    logo = models.ImageField(
        upload_to="restaurants/logos/",
        null=True,
        blank=True,
    )

    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100, blank=True)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    categories = models.JSONField(default=list, blank=True)
    operating_hours = models.JSONField(default=dict, blank=True)

    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    total_reviews = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="newly_joined",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def update_rating(self):
        from django.db.models import Avg

        reviews = self.reviews.filter(is_hidden=False)
        avg_rating = reviews.aggregate(avg=Avg("rating"))["avg"] or 0

        self.rating = round(avg_rating, 1)
        self.total_reviews = reviews.count()
        self.save(update_fields=["rating", "total_reviews"])


class RestaurantGallery(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="gallery",
    )
    image = models.ImageField(upload_to="restaurants/gallery/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.restaurant.name} - image {self.id}"


class Review(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    rating = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ]
    )

    comment = models.TextField()
    helpful_count = models.IntegerField(default=0)

    restaurant_response = models.TextField(blank=True)
    restaurant_response_date = models.DateTimeField(null=True, blank=True)
    is_hidden = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    flagged_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["restaurant", "user"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.restaurant.update_rating()

    def delete(self, *args, **kwargs):
        restaurant = self.restaurant
        super().delete(*args, **kwargs)
        restaurant.update_rating()

    def __str__(self):
        return f"{self.user.full_name} → {self.restaurant.name} ({self.rating}★)"