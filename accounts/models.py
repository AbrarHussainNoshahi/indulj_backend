from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
import random
import string


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_email_verified", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("restaurant", "Restaurant"),
        ("user", "User"),
    ]

    username = None

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    display_username = models.CharField(max_length=50, blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    points = models.IntegerField(default=0)
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    is_email_verified = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    location = models.CharField(max_length=255, blank=True)

    two_factor_enabled = models.BooleanField(default=False)
    google_linked = models.BooleanField(default=False)
    apple_linked = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.referral_code:
            base = self.full_name[:4].upper() if self.full_name else "USER"
            year = timezone.now().year
            self.referral_code = f"{base}{year}"

            while User.objects.filter(referral_code=self.referral_code).exists():
                suffix = "".join(random.choices(string.digits, k=3))
                self.referral_code = f"{base}{year}{suffix}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class OTPVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=10)

        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.otp}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_prefs",
    )
    email_deals = models.BooleanField(default=True)
    email_happy_hours = models.BooleanField(default=True)
    sms_deals = models.BooleanField(default=False)
    sms_happy_hours = models.BooleanField(default=True)


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    device_info = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    last_active = models.DateTimeField(auto_now=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)