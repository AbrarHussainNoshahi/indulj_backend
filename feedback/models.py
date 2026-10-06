from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class PlatformFeedback(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General Feedback'),
        ('usability', 'Ease of Use & Navigation'),
        ('features', 'Feature Requests'),
        ('difficulties', 'Issues & Confusing Aspects'),
        ('deals_happy_hours', 'Deals & Happy Hours'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_feedbacks',
    )
    user_name = models.CharField(max_length=255, blank=True, default='')
    user_email = models.EmailField(blank=True, default='')

    # Ratings (1 to 5 scale)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Overall rating (1-5)",
        default=5
    )
    ease_of_use = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="How easy was the website/app to use? (1-5)",
        default=5
    )
    usefulness = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="How useful is INDULJ? (1-5)",
        default=5
    )
    smoothness = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="How smooth was the experience? (1-5)",
        default=5
    )

    # Detailed questions from requirements
    difficulties = models.TextField(
        blank=True,
        default='',
        help_text="Did they face any difficulties?"
    )
    confusing_aspects = models.TextField(
        blank=True,
        default='',
        help_text="Was anything confusing?"
    )
    feature_requests = models.TextField(
        blank=True,
        default='',
        help_text="What features would they like to see?"
    )
    comments = models.TextField(
        blank=True,
        default='',
        help_text="General suggestions or comments"
    )

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='general'
    )

    # Super Admin management
    is_liked = models.BooleanField(
        default=False,
        help_text="Super Admin can like/favorite feedback"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    admin_reply = models.TextField(
        blank=True,
        default='',
        help_text="Super Admin response to feedback"
    )
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_feedback_replies',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['is_liked']),
            models.Index(fields=['rating']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        name = self.user.full_name if self.user and self.user.full_name else (self.user_name or "Anonymous")
        return f"{name} - {self.rating}★ ({self.created_at.strftime('%Y-%m-%d')})"

    @property
    def submitter_name(self):
        if self.user:
            return self.user.full_name or self.user.display_username or self.user.email
        return self.user_name or "Anonymous User"

    @property
    def submitter_email(self):
        if self.user:
            return self.user.email
        return self.user_email or ""
