from django.urls import path
from .views import (
    RegisterView,
    VerifyOTPView,
    ResendOTPView,
    LoginView,
    LogoutView,
    GoogleAuthView,
    CookieTokenRefreshView,
    ProfileView,
    ChangePasswordView,
    DeleteAccountView,
    NotificationPreferenceView,
    SessionListView,
    SessionRevokeView,
    ReferralCodeView,
    RemoveAvatarView,
    ToggleTwoFactorView,
    UserStatsView,
    AdminUsersListView,
    AdminUserDeleteView,
    AdminUserSuspendView,
    AdminUserDetailView,
    PointsRewardsSummaryView,
    PointsTransactionHistoryView,
    ReceiptScanUploadView,
    AdminReceiptScanListView,
    AdminVerifyReceiptScanView,
)

urlpatterns = [
    # Auth
    path("register/", RegisterView.as_view()),
    path("verify-otp/", VerifyOTPView.as_view()),
    path("resend-otp/", ResendOTPView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("google/", GoogleAuthView.as_view()),
    path("token/refresh/", CookieTokenRefreshView.as_view()),

    # Profile
    path("profile/", ProfileView.as_view()),
    path("profile/update/", ProfileView.as_view()),
    path("avatar/remove/", RemoveAvatarView.as_view()),
    path("stats/", UserStatsView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("delete-account/", DeleteAccountView.as_view()),
    path("referral-code/", ReferralCodeView.as_view()),

    # Rewards & Points
    path("rewards/summary/", PointsRewardsSummaryView.as_view()),
    path("rewards/history/", PointsTransactionHistoryView.as_view()),
    path("rewards/receipts/", ReceiptScanUploadView.as_view()),
    path("admin/receipts/", AdminReceiptScanListView.as_view()),
    path("admin/receipts/<int:pk>/verify/", AdminVerifyReceiptScanView.as_view()),

    # Settings
    path("2fa/toggle/", ToggleTwoFactorView.as_view()),
    path("notification-prefs/", NotificationPreferenceView.as_view()),
    path("sessions/", SessionListView.as_view()),
    path("sessions/<int:session_id>/revoke/", SessionRevokeView.as_view()),

    # Admin User Management
    path("admin/users/", AdminUsersListView.as_view()),
    path("admin/users/<int:pk>/", AdminUserDetailView.as_view()),
    path("admin/users/<int:pk>/delete/", AdminUserDeleteView.as_view()),
    path("admin/users/<int:pk>/suspend/", AdminUserSuspendView.as_view()),
]