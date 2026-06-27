from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    TYPE_CHOICES = [
        ('order', 'order'),
        ('deal', 'deal'),
        ('happy_hour', 'happy_hour'),
        ('favourite', 'favourite'),
        ('restaurant', 'restaurant'),
        ('system', 'system'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Optional links
    related_order = models.ForeignKey(
        'orders.Order',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    related_deal = models.ForeignKey(
        'deals.Deal',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    related_happy_hour = models.ForeignKey(
        'happy_hours.HappyHour',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    related_restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title} ({self.type})"

    def mark_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

    @property
    def status(self):
        return "read" if self.is_read else "unread"
