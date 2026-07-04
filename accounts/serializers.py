from rest_framework import serializers
from .models import User, NotificationPreference, UserSession, Referral, PointsTransaction, ReceiptScan


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
            "two_factor_enabled",
            "google_linked",
            "apple_linked",
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
    class Meta:
        model = UserSession
        fields = [
            "id",
            "device_info",
            "location",
            "last_active",
            "is_current",
        ]


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