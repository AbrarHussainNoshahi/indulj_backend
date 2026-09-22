from rest_framework import serializers
from .models import User, NotificationPreference, UserSession, Referral, PointsTransaction, ReceiptScan, Partner


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(required=False, write_only=True, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "full_name",
            "email",
            "phone_number",
            "password",
            "confirm_password",
            "referral_code",
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")

        return value

    def validate_referral_code(self, value):
        if value:
            if not User.objects.filter(referral_code=value).exists():
                raise serializers.ValidationError("Invalid referral code. Submitter code does not exist.")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )

        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        referral_code = validated_data.pop("referral_code", None)

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            phone_number=validated_data.get("phone_number", ""),
            referred_by_code=referral_code,
        )

        NotificationPreference.objects.create(user=user)

        return user


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "display_username",
            "email",
            "phone_number",
            "role",
            "avatar",
            "avatar_url",
            "points",
            "referral_code",
            "is_email_verified",
            "is_suspended",
            "location",
            "admin_type",
            "is_super_admin",
            "is_employee_admin",
            "two_factor_enabled",
            "google_linked",
            "apple_linked",
            "designation",
            "social_links",
            "date_joined",
        ]

        read_only_fields = [
            "id",
            "email",
            "role",
            "points",
            "referral_code",
            "is_email_verified",
            "is_suspended",
            "google_linked",
            "apple_linked",
            "date_joined",
        ]

    def get_avatar_url(self, obj):
        request = self.context.get("request")

        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)

        if obj.avatar:
            return obj.avatar.url

        return None


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "full_name",
            "display_username",
            "phone_number",
            "location",
            "designation",
            "social_links",
            "avatar",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=6)
    confirm_new_password = serializers.CharField()

    def validate(self, data):
        if data["new_password"] != data["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "Passwords do not match"}
            )

        return data


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "email_deals",
            "email_happy_hours",
            "sms_deals",
            "sms_happy_hours",
        ]


class UserSessionSerializer(serializers.ModelSerializer):
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model  = UserSession
        fields = [
            'id', 'device_info', 'browser', 'os',
            'ip_address', 'location',
            'is_current', 'last_active',
            'created_at', 'time_ago',
        ]

    def get_time_ago(self, obj):
        from django.utils.timesince import timesince
        from django.utils import timezone
        try:
            return timesince(obj.last_active, timezone.now())
        except Exception:
            return "0 minutes"


class PointsTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointsTransaction
        fields = ["id", "text", "date", "status", "points", "created_at"]


class ReceiptScanSerializer(serializers.ModelSerializer):
    restaurant_name_display = serializers.SerializerMethodField()

    class Meta:
        model = ReceiptScan
        fields = [
            "id",
            "restaurant",
            "restaurant_name",
            "restaurant_name_display",
            "receipt_image",
            "amount",
            "receipt_date",
            "status",
            "uploaded_at",
        ]
        read_only_fields = ["status", "uploaded_at"]

    def get_restaurant_name_display(self, obj):
        if obj.restaurant:
            return obj.restaurant.name
        return obj.restaurant_name


class ReferralSerializer(serializers.ModelSerializer):
    referrer_name = serializers.CharField(source="referrer.full_name", read_only=True)
    referred_user_name = serializers.CharField(source="referred_user.full_name", read_only=True)

    class Meta:
        model = Referral
        fields = ["id", "referrer", "referrer_name", "referred_user", "referred_user_name", "created_at"]

# ─── ADMIN STAFF MANAGEMENT SERIALIZERS ─────────────────────
import json
import secrets
from django.utils import timezone

class AdminStaffSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    restaurants_count = serializers.SerializerMethodField()
    active_restaurants_count = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    join_date = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone_number",
            "unique_id",
            "designation",
            "assigned_roles",
            "role_display",
            "admin_type",
            "is_super_admin",
            "is_employee_admin",
            "is_suspended",
            "status",
            "avatar",
            "avatar_url",
            "social_links",
            "restaurants_count",
            "active_restaurants_count",
            "date_joined",
            "join_date",
        ]
        read_only_fields = [
            "id",
            "is_super_admin",
            "is_employee_admin",
            "restaurants_count",
            "active_restaurants_count",
            "date_joined",
            "join_date",
            "status",
            "role_display",
        ]

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        if obj.avatar:
            return obj.avatar.url
        return None

    def get_restaurants_count(self, obj):
        return getattr(obj, "restaurants_count", obj.registered_restaurants.count())

    def get_active_restaurants_count(self, obj):
        return obj.registered_restaurants.filter(status="active").count()

    def get_role_display(self, obj):
        return obj.roles_display

    def get_status(self, obj):
        if obj.is_suspended:
            return "Suspended"
        if obj.date_joined and (timezone.now() - obj.date_joined).days < 30:
            return "Newly Joined"
        return "Active"

    def get_join_date(self, obj):
        if not obj.date_joined:
            return "N/A"
        return obj.date_joined.strftime("%b %d, %Y")


class CreateAdminStaffSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    unique_id = serializers.CharField(max_length=50, required=False, allow_blank=True)
    designation = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    assigned_roles = serializers.JSONField(required=False, default=list)
    social_links = serializers.JSONField(required=False, default=dict)
    avatar = serializers.ImageField(required=False, allow_null=True)
    admin_type = serializers.ChoiceField(
        choices=[("super_admin", "Super Admin"), ("employee", "Employee")],
        default="employee"
    )

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def create(self, validated_data):
        admin_type = validated_data.get("admin_type", "employee")
        avatar = validated_data.pop("avatar", None)
        password = validated_data.get("password")
        if not password:
            password = secrets.token_urlsafe(12)

        assigned_roles = validated_data.get("assigned_roles") or []
        if isinstance(assigned_roles, str):
            try:
                assigned_roles = json.loads(assigned_roles)
            except Exception:
                assigned_roles = [r.strip() for r in assigned_roles.split(",") if r.strip()]

        user = User.objects.create_user(
            email=validated_data["email"],
            password=password,
            full_name=validated_data["full_name"],
            phone_number=validated_data.get("phone_number", ""),
            unique_id=validated_data.get("unique_id", ""),
            designation=validated_data.get("designation", ""),
            assigned_roles=assigned_roles,
            social_links=validated_data.get("social_links") or {},
            role="admin",
            admin_type=admin_type,
            is_staff=True,
            is_superuser=(admin_type == "super_admin"),
            is_email_verified=True,
        )
        if avatar:
            user.avatar = avatar
            user.save(update_fields=["avatar"])
        NotificationPreference.objects.create(user=user)
        return user


class UpdateAdminStaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "full_name",
            "phone_number",
            "unique_id",
            "designation",
            "assigned_roles",
            "social_links",
            "avatar",
            "admin_type",
            "password",
        ]

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        assigned_roles = validated_data.get("assigned_roles")
        if isinstance(assigned_roles, str):
            try:
                validated_data["assigned_roles"] = json.loads(assigned_roles)
            except Exception:
                validated_data["assigned_roles"] = [r.strip() for r in assigned_roles.split(",") if r.strip()]

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if instance.admin_type == "super_admin":
            instance.is_superuser = True
        elif instance.admin_type == "employee":
            instance.is_superuser = False

        if password:
            instance.set_password(password)

        instance.save()
        return instance


# ─── PARTNERS SERIALIZERS (FOR ABOUT US & ADMIN PROFILE) ─────
class PartnerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    full_name = serializers.CharField(source="name", read_only=True)
    avatar_url = serializers.SerializerMethodField()
    role = serializers.CharField(source="designation", read_only=True)

    class Meta:
        model = Partner
        fields = [
            "id",
            "name",
            "full_name",
            "designation",
            "role",
            "image",
            "image_url",
            "avatar_url",
            "social_links",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        if obj.image:
            return obj.image.url
        return None

    def get_avatar_url(self, obj):
        return self.get_image_url(obj)


class PartnerCreateUpdateSerializer(serializers.ModelSerializer):
    social_links = serializers.JSONField(required=False, default=dict)
    designation = serializers.CharField(required=False, allow_blank=True, default="Partner")

    class Meta:
        model = Partner
        fields = [
            "id",
            "name",
            "designation",
            "image",
            "social_links",
            "order",
            "is_active",
        ]

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        social = data.get("social_links")
        if isinstance(social, str):
            try:
                ret["social_links"] = json.loads(social)
            except Exception:
                ret["social_links"] = {}
        return ret

