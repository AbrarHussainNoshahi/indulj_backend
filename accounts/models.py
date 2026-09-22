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

    ADMIN_TYPE_CHOICES = [
        ("super_admin", "Super Admin"),
        ("employee", "Employee"),
    ]

    username = None

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    display_username = models.CharField(max_length=50, blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    admin_type = models.CharField(
        max_length=20,
        choices=ADMIN_TYPE_CHOICES,
        default="super_admin",
        blank=True,
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    designation = models.CharField(max_length=100, blank=True, default="")
    unique_id = models.CharField(max_length=50, blank=True, default="")
    assigned_roles = models.JSONField(default=list, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    points = models.IntegerField(default=0)
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by_code = models.CharField(max_length=20, blank=True, null=True)
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

        if not self.unique_id and self.role == "admin":
            parts = (self.full_name or "SA").strip().split()
            initials = "".join([p[0].upper() for p in parts[:2]]) if parts else "SA"
            digits = "".join(random.choices(string.digits, k=4))
            self.unique_id = f"{initials}-{digits}"

        super().save(*args, **kwargs)

    @property
    def is_super_admin(self):
        return self.role == "admin" and (self.is_superuser or self.admin_type == "super_admin")

    @property
    def is_employee_admin(self):
        return self.role == "admin" and not self.is_super_admin

    @property
    def roles_display(self):
        if self.assigned_roles and isinstance(self.assigned_roles, list) and len(self.assigned_roles) > 0:
            return " & ".join(self.assigned_roles)
        if self.is_super_admin:
            return "Super Admin"
        return "Manage Deals & Happy Hours"

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
    user        = models.ForeignKey(
                      User, on_delete=models.CASCADE,
                      related_name='sessions'
                  )
    session_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True)
    browser     = models.CharField(max_length=100, blank=True)
    os          = models.CharField(max_length=100, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    location    = models.CharField(max_length=255, blank=True)
    is_current  = models.BooleanField(default=False)
    is_revoked  = models.BooleanField(default=False)
    last_active = models.DateTimeField(auto_now=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_active']

    def __str__(self):
        return f"{self.user.email} — {self.browser} on {self.os}"


class Referral(models.Model):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referrals_made")
    referred_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="referral_received")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.referrer.email} referred {self.referred_user.email}"


class PointsTransaction(models.Model):
    STATUS_CHOICES = [
        ("approved", "Approved"),
        ("pending", "Pending"),
        ("rejected", "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="points_transactions")
    text = models.CharField(max_length=255)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    points = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.points} pts ({self.status})"


class ReceiptScan(models.Model):
    STATUS_CHOICES = [
        ("approved", "Approved"),
        ("pending", "Pending"),
        ("rejected", "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="receipt_scans")
    restaurant = models.ForeignKey('restaurants.Restaurant', on_delete=models.SET_NULL, null=True, blank=True, related_name="receipt_scans")
    restaurant_name = models.CharField(max_length=255, blank=True)
    receipt_image = models.ImageField(upload_to="receipts/")
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    receipt_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        rest = self.restaurant.name if self.restaurant else self.restaurant_name
        return f"Receipt by {self.user.email} at {rest} - {self.status}"


class Partner(models.Model):
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=150, blank=True, default="Partner")
    image = models.ImageField(upload_to="partners/", null=True, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.designation})"
