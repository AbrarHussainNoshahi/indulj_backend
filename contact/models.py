from django.db import models
from django.conf import settings


class ContactMessage(models.Model):
    INQUIRY_CHOICES = [
        ("general", "General Inquiry"),
        ("support", "Customer & Account Support"),
        ("restaurant", "Restaurant Partnership & Listing"),
        ("deals", "Deals & Happy Hours"),
        ("bug", "Report an Issue / Bug"),
        ("feedback", "Feedback & Suggestion"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
        help_text="Authenticated user who submitted this message, if any."
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, default="")
    inquiry_type = models.CharField(
        max_length=50,
        choices=INQUIRY_CHOICES,
        default="general"
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()

    # Admin handling
    is_read = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["inquiry_type"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.subject} ({self.created_at.strftime('%Y-%m-%d')})"
