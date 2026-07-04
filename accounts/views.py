import requests as http_requests
from django.contrib.auth import authenticate
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Count, Sum, Q
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import NotificationPreference, OTPVerification, User, UserSession
from .serializers import (
    ChangePasswordSerializer, LoginSerializer,
    NotificationPreferenceSerializer, RegisterSerializer,
    ResendOTPSerializer, UpdateProfileSerializer,
    UserSerializer, UserSessionSerializer, VerifyOTPSerializer,
)
from .utils import (
    clear_auth_cookies, generate_otp, get_tokens_for_user,
    send_otp_email, set_auth_cookies,
)


def make_user_data(user, request=None):
    return {
        'success': True,
        'role':    user.role,
        'user':    UserSerializer(user, context={'request': request}).data,
    }


# ─── REGISTER ───────────────────────────────────────────────
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = serializer.save()
        otp  = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        
        send_otp_email(user.email, otp)
        response_data = {
            "success": True,
            "message": "OTP sent to your email.",
            "email": user.email,
        }
        response_data["dev_otp"] = otp
        # if settings.DEBUG:
        #     response_data["dev_otp"] = otp
        return Response(response_data, status=status.HTTP_201_CREATED)
        # return Response({
        #     'success': True,
        #     'message': 'OTP sent to your email.',
        #     'email':   user.email,
        # }, status=status.HTTP_201_CREATED)


# ─── VERIFY OTP ─────────────────────────────────────────────
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=400
            )
        email = serializer.validated_data['email']
        otp   = serializer.validated_data['otp']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'message': 'User not found'}, status=404)

        otp_obj = OTPVerification.objects.filter(
            user=user, otp=otp, is_used=False
        ).last()

        if not otp_obj:
            return Response({'success': False, 'message': 'Invalid OTP'}, status=400)
        if not otp_obj.is_valid():
            return Response({'success': False, 'message': 'OTP expired'}, status=400)

        otp_obj.is_used = True
        otp_obj.save()

        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

            if user.referred_by_code:
                from .models import Referral, PointsTransaction
                try:
                    referrer = User.objects.get(referral_code=user.referred_by_code)
                    if not Referral.objects.filter(referred_user=user).exists():
                        Referral.objects.create(referrer=referrer, referred_user=user)
                        referrer.points += 100
                        referrer.save(update_fields=["points"])
                        PointsTransaction.objects.create(
                            user=referrer,
                            text=f"Referral bonus - {user.full_name or user.email} joined",
                            status="approved",
                            points=100
                        )
                        # Notify referrer
                        try:
                            from notifications.utils import create_notification
                            create_notification(
                                user=referrer,
                                type="system",
                                title="New Referral Signup! 🎉",
                                message=f"{user.full_name or user.email} joined Indulj using your referral code! You earned 100 points.",
                            )
                        except Exception:
                            pass
                except User.DoesNotExist:
                    pass
        else:
            user.save()

        tokens   = get_tokens_for_user(user)
        response = Response({
            **make_user_data(user, request),
            'message': 'Email verified successfully',
        })
        set_auth_cookies(response, tokens['access'], tokens['refresh'])
        return response


# ─── RESEND OTP ─────────────────────────────────────────────
class ResendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'message': 'User not found'}, status=404)

        if user.is_email_verified:
            return Response({'success': False, 'message': 'Email already verified'}, status=400)

        OTPVerification.objects.filter(user=user, is_used=False).update(is_used=True)
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        send_otp_email(user.email, otp)
        response_data = {
            "success": True,
            "message": "New OTP sent",
        }
        response_data["dev_otp"] = otp
        # if settings.DEBUG:
        #     response_data["dev_otp"] = otp

        return Response(response_data)
        # return Response({'success': True, 'message': 'New OTP sent'})


# ─── LOGIN ──────────────────────────────────────────────────
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        email    = serializer.validated_data['email']
        password = serializer.validated_data['password']
        user     = authenticate(request, username=email, password=password)

        if not user:
            return Response(
                {'success': False, 'message': 'Invalid email or password'},
                status=401
            )
        if not user.is_email_verified:
            return Response({
                'success': False,
                'message': 'Please verify your email first',
                'email':   email,
                'requires_verification': True,
            }, status=403)
        if user.is_suspended:
            return Response(
                {'success': False, 'message': 'Account suspended. Contact support.'},
                status=403
            )

        tokens   = get_tokens_for_user(user)
        response = Response({
            **make_user_data(user, request),
            'message': 'Login successful',
        })
        set_auth_cookies(response, tokens['access'], tokens['refresh'])
        return response


# ─── GOOGLE LOGIN ───────────────────────────────────────────
class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        access_token = request.data.get("token")

        if not access_token:
            return Response({
                "success": False,
                "message": "Token required",
            }, status=400)

        google_response = http_requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if google_response.status_code != 200:
            return Response({
                "success": False,
                "message": "Invalid Google token",
            }, status=400)

        info = google_response.json()
        email = info.get("email")
        full_name = info.get("name", "")

        if not email:
            return Response({
                "success": False,
                "message": "Could not get email",
            }, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": full_name,
                "role": "user",
                "is_email_verified": True,
                "google_linked": True,
            },
        )

        if user.is_suspended:
            return Response({
                "success": False,
                "message": "Account suspended",
            }, status=403)

        update_fields = []

        if not user.is_email_verified:
            user.is_email_verified = True
            update_fields.append("is_email_verified")

        if not user.google_linked:
            user.google_linked = True
            update_fields.append("google_linked")

        if not user.full_name and full_name:
            user.full_name = full_name
            update_fields.append("full_name")

        if update_fields:
            user.save(update_fields=update_fields)

        if created:
            NotificationPreference.objects.create(user=user)

        tokens = get_tokens_for_user(user)

        response = Response({
            **make_user_data(user, request),
            "message": "Google login successful",
        })

        set_auth_cookies(response, tokens["access"], tokens["refresh"])

        return response

# ─── LOGOUT ─────────────────────────────────────────────────
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
        response = Response({'success': True, 'message': 'Logged out'})
        clear_auth_cookies(response)
        return response


# ─── TOKEN REFRESH ──────────────────────────────────────────
class CookieTokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response({'success': False, 'message': 'No refresh token'}, status=401)
        try:
            refresh  = RefreshToken(refresh_token)
            tokens   = {'access': str(refresh.access_token), 'refresh': str(refresh)}
            response = Response({'success': True})
            set_auth_cookies(response, tokens['access'], tokens['refresh'])
            return response
        except TokenError:
            return Response({'success': False, 'message': 'Invalid refresh token'}, status=401)


# ─── PROFILE ────────────────────────────────────────────────
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response({
            "success": True,
            "data": UserSerializer(
                request.user,
                context={"request": request},
            ).data,
        })

    def put(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response({
                "success": True,
                "message": "Profile updated",
                "data": UserSerializer(
                    request.user,
                    context={"request": request},
                ).data,
            })

        return Response({
            "success": False,
            "errors": serializer.errors,
        }, status=400)

    def patch(self, request):
        return self.put(request)

# ─── CHANGE PASSWORD ────────────────────────────────────────
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)
        if not request.user.check_password(serializer.validated_data['current_password']):
            return Response({'success': False, 'message': 'Current password incorrect'}, status=400)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'success': True, 'message': 'Password updated'})


# ─── DELETE ACCOUNT ─────────────────────────────────────────
class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        request.user.delete()
        response = Response({'success': True, 'message': 'Account deleted'})
        clear_auth_cookies(response)
        return response


# ─── NOTIFICATION PREFERENCES ───────────────────────────────
class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response({'success': True, 'data': NotificationPreferenceSerializer(prefs).data})

    def put(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'data': serializer.data})
        return Response({'success': False, 'errors': serializer.errors}, status=400)


# ─── SESSIONS ───────────────────────────────────────────────
class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = UserSession.objects.filter(user=request.user).order_by('-last_active')
        return Response({'success': True, 'data': UserSessionSerializer(sessions, many=True).data})


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        try:
            session = UserSession.objects.get(id=session_id, user=request.user)
            session.delete()
            return Response({'success': True, 'message': 'Session revoked'})
        except UserSession.DoesNotExist:
            return Response({'success': False, 'message': 'Session not found'}, status=404)


# ─── REFERRAL CODE ──────────────────────────────────────────
class ReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'success': True, 'data': {'referral_code': request.user.referral_code}})


class RemoveAvatarView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user

        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save(update_fields=["avatar"])

        return Response({
            "success": True,
            "message": "Avatar removed successfully.",
        })


class ToggleTwoFactorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.two_factor_enabled = not user.two_factor_enabled
        user.save(update_fields=["two_factor_enabled"])

        status_text = "enabled" if user.two_factor_enabled else "disabled"

        return Response({
            "success": True,
            "message": f"Two-factor authentication {status_text}.",
            "two_factor_enabled": user.two_factor_enabled,
        })


class UserStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from deals.models import Deal, SavedDeal
        from happy_hours.models import HappyHour
        from orders.models import Order

        user = request.user

        # submitted_deals = Deal.objects.filter(submitted_by=user).count()
        submitted_deals = Deal.objects.filter(
            Q(submitted_by=user) |
            Q(restaurant__owner=user)
        ).distinct().count()
        
        user_created_deals = Deal.objects.filter(submitted_by=user).count()

        restaurant_created_deals = Deal.objects.filter(
            restaurant__owner=user,
            submitted_by__isnull=True
        ).count()
        
        planned_happy_hours = HappyHour.objects.filter(submitted_by=user).count()
        saved_deals = SavedDeal.objects.filter(user=user).count()

        total_savings = float(
            Order.objects.filter(
                user=user,
                status="completed",
                deal__isnull=False,
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )

        return Response({
            "success": True,
            "data": {
                "points": user.points,
                "total_savings": total_savings,
                "submitted_deals": submitted_deals,
                "user_created_deals": user_created_deals,
                "restaurant_created_deals": restaurant_created_deals,
                "planned_happy_hours": planned_happy_hours,
                "saved_deals": saved_deals,
            }
        })


# ─── ADMIN USERS MANAGEMENT ─────────────────────────────────
from datetime import timedelta
from .permissions import IsAdmin

class AdminUsersListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        
        users = (
            User.objects.filter(role="user")
            .annotate(
                deals_count=Count("submitted_deals", distinct=True),
                happy_hours_count=Count("planned_happy_hours", distinct=True),
            )
            .order_by("-date_joined")
        )
        
        data = []
        for u in users:
            if u.is_suspended:
                status_label = "Suspended"
            elif u.date_joined >= thirty_days_ago:
                status_label = "Newly Joined"
            else:
                status_label = "Active"
                
            data.append({
                "id": u.id,
                "name": u.full_name or "User",
                "email": u.email,
                "image": u.avatar.url if u.avatar else "user-1.jpg",
                "date": u.date_joined.strftime("%b %d, %Y") if u.date_joined else "N/A",
                "deals": u.deals_count,
                "happyHours": u.happy_hours_count,
                "status": status_label,
            })
            
        return Response({"success": True, "data": data})


class AdminUserDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role="user")
            user.delete()
            return Response({"success": True, "message": "User deleted successfully."})
        except User.DoesNotExist:
            return Response({"success": False, "message": "User not found."}, status=404)


class AdminUserSuspendView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role="user")
            user.is_suspended = not user.is_suspended
            user.save()
            status_text = "suspended" if user.is_suspended else "activated"
            return Response({
                "success": True,
                "message": f"User {status_text} successfully.",
                "is_suspended": user.is_suspended
            })
        except User.DoesNotExist:
            return Response({"success": False, "message": "User not found."}, status=404)


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role="user")
            
            # Fetch user's deals
            deals = []
            for deal in user.submitted_deals.all().order_by("-created_at"):
                status_label = "Approved" if deal.status == "active" else deal.status.capitalize()
                deals.append({
                    "title": deal.title,
                    "restaurant": deal.restaurant.name if deal.restaurant else None,
                    "date": deal.created_at.strftime("%b %d, %Y") if deal.created_at else "N/A",
                    "status": status_label,
                })

            # Fetch user's happy hours
            happy_hours = []
            for hh in user.planned_happy_hours.all().order_by("-created_at"):
                map_status = {
                    "active": "Active",
                    "upcoming": "Upcoming",
                    "pending": "Pending",
                    "rejected": "Rejected",
                    "cancelled": "Cancelled",
                    "draft": "Draft",
                    "expired": "Expired",
                }
                status_label = map_status.get(hh.status, hh.status.capitalize())
                
                start = hh.start_time.strftime("%I:%M %p") if hh.start_time else ""
                end = hh.end_time.strftime("%I:%M %p") if hh.end_time else ""
                time_slot = f"{start} - {end}" if start and end else "N/A"
                
                happy_hours.append({
                    "title": hh.title,
                    "location": hh.location or hh.restaurant.address or "N/A",
                    "date": hh.date.strftime("%b %d, %Y") if hh.date else "N/A",
                    "time": time_slot,
                    "status": status_label,
                })

            total_approved_deals = user.submitted_deals.filter(status="active").count()
            total_approved_happy_hours = user.planned_happy_hours.filter(status="active").count()
            total_approved = total_approved_deals + total_approved_happy_hours

            data = {
                "id": user.id,
                "name": user.full_name or "User",
                "email": user.email,
                "phone": user.phone_number or "-",
                "image_url": user.avatar.url if user.avatar else None,   
                "joined": user.date_joined.strftime("%b %d, %Y") if user.date_joined else "N/A",
                "totalPoints": user.points,
                "dealsSubmitted": user.submitted_deals.count(),
                "happyHours": user.planned_happy_hours.count(),
                "totalApproved": total_approved,
                "deals": deals,
                "happyHoursList": happy_hours,
                "is_suspended": user.is_suspended,
            }
            return Response({"success": True, "data": data})
        except User.DoesNotExist:
            return Response({"success": False, "message": "User not found."}, status=404)


# ─── REWARDS & POINTS ──────────────────────────────────────────
from .models import Referral, PointsTransaction, ReceiptScan
from .serializers import PointsTransactionSerializer, ReceiptScanSerializer, ReferralSerializer
from accounts.permissions import IsAdmin

class PointsRewardsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Successful referrals count
        referrals_count = Referral.objects.filter(referrer=user).count()
        referrals_points_earned = referrals_count * 100

        # Submitted deals count (only active/approved ones can give points, but let's see how many deals are submitted)
        deals_submitted_count = user.submitted_deals.filter(status="active").count()
        deals_points_earned = deals_submitted_count * 50

        # Receipts scanned count (approved/verified ones)
        receipts_scanned_count = ReceiptScan.objects.filter(user=user, status="approved").count()
        
        # We can also compute total receipts scanned regardless of status for stats
        total_receipts_scanned = ReceiptScan.objects.filter(user=user).count()

        return Response({
            "success": True,
            "data": {
                "total_points": user.points,
                "referrals_count": referrals_count,
                "referrals_points_earned": referrals_points_earned,
                "deals_submitted_count": user.submitted_deals.count(),  # total submitted
                "deals_approved_count": deals_submitted_count,          # approved count
                "deals_points_earned": deals_points_earned,
                "receipts_scanned_count": total_receipts_scanned,       # total scanned
                "receipts_approved_count": receipts_scanned_count,      # approved scanned
                "referral_code": user.referral_code,
            }
        })


class PointsTransactionHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = PointsTransaction.objects.filter(user=request.user).order_by("-created_at")
        serializer = PointsTransactionSerializer(transactions, many=True)
        return Response({
            "success": True,
            "data": serializer.data
        })


class ReceiptScanUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        scans = ReceiptScan.objects.filter(user=request.user).order_by("-uploaded_at")
        serializer = ReceiptScanSerializer(scans, many=True)
        return Response({
            "success": True,
            "data": serializer.data
        })

    def post(self, request):
        serializer = ReceiptScanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save receipt scan
        scan = serializer.save(user=request.user, status="pending")

        # Create pending PointsTransaction
        rest_name = scan.restaurant.name if scan.restaurant else scan.restaurant_name
        PointsTransaction.objects.create(
            user=request.user,
            text=f"Receipt scanned at {rest_name or 'Restaurant'}",
            status="pending",
            points=25
        )

        return Response({
            "success": True,
            "data": ReceiptScanSerializer(scan).data,
            "message": "Receipt uploaded successfully and is pending review."
        }, status=status.HTTP_201_CREATED)


class AdminReceiptScanListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        scans = ReceiptScan.objects.all().order_by("-uploaded_at")
        serializer = ReceiptScanSerializer(scans, many=True)
        return Response({
            "success": True,
            "data": serializer.data
        })


class AdminVerifyReceiptScanView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            scan = ReceiptScan.objects.get(pk=pk)
        except ReceiptScan.DoesNotExist:
            return Response({
                "success": False,
                "message": "Receipt scan not found."
            }, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in ["approved", "rejected"]:
            return Response({
                "success": False,
                "message": "Invalid status. Must be 'approved' or 'rejected'."
            }, status=status.HTTP_400_BAD_REQUEST)

        if scan.status != "pending":
            return Response({
                "success": False,
                "message": "Receipt scan is already processed."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update scan
        scan.status = new_status
        scan.save(update_fields=["status"])

        # Find the associated pending PointsTransaction
        rest_name = scan.restaurant.name if scan.restaurant else scan.restaurant_name
        # Match text pattern
        text_prefix = f"Receipt scanned at {rest_name or 'Restaurant'}"
        transaction = PointsTransaction.objects.filter(
            user=scan.user,
            text__startswith=text_prefix,
            status="pending"
        ).last()

        if new_status == "approved":
            # Add points to user
            user = scan.user
            user.points += 25
            user.save(update_fields=["points"])

            # Update transaction
            if transaction:
                transaction.status = "approved"
                transaction.points = 25
                transaction.save(update_fields=["status", "points"])
            else:
                PointsTransaction.objects.create(
                    user=user,
                    text=f"Receipt scanned at {rest_name or 'Restaurant'}",
                    status="approved",
                    points=25
                )
        else: # rejected
            if transaction:
                transaction.status = "rejected"
                transaction.points = -25 # set to -25 to match frontend style
                transaction.save(update_fields=["status", "points"])
            else:
                PointsTransaction.objects.create(
                    user=scan.user,
                    text=f"Receipt scanned at {rest_name or 'Restaurant'}",
                    status="rejected",
                    points=-25
                )

        return Response({
            "success": True,
            "message": f"Receipt scan status updated to {new_status}."
        })


