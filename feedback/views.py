from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import PlatformFeedback
from .serializers import (
    PlatformFeedbackSerializer,
    PlatformFeedbackCreateSerializer,
    PlatformFeedbackReplySerializer,
    PlatformFeedbackStatusSerializer,
)
from accounts.models import User
from accounts.permissions import IsSuperAdmin
from notifications.utils import create_notification


class SubmitFeedbackView(APIView):
    """
    Public or authenticated submission of platform feedback about INDULJ itself.
    Notifies Super Admins exclusively upon submission.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlatformFeedbackCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        feedback = serializer.save()

        # Attach authenticated user if available
        if request.user and request.user.is_authenticated:
            feedback.user = request.user
            if not feedback.user_name:
                feedback.user_name = (
                    request.user.full_name
                    or request.user.display_username
                    or request.user.email
                )
            if not feedback.user_email:
                feedback.user_email = request.user.email
            feedback.save()

        # Notify ONLY Super Admins
        try:
            super_admins = User.objects.filter(
                role="admin",
                is_active=True,
                is_suspended=False
            ).filter(
                Q(admin_type="super_admin") | Q(is_superuser=True)
            )

            preview_text = (
                feedback.comments
                or feedback.difficulties
                or feedback.confusing_aspects
                or feedback.feature_requests
                or f"Rated {feedback.rating}/5 stars"
            )
            if len(preview_text) > 80:
                preview_text = preview_text[:77] + "..."

            submitter = feedback.submitter_name

            for sa in super_admins:
                create_notification(
                    user=sa,
                    type="feedback",
                    title="New INDULJ Feedback Received",
                    message=f"{submitter} submitted {feedback.rating}★ feedback: \"{preview_text}\"",
                    metadata={
                        "feedback_id": feedback.id,
                        "action_url": f"/admin/dashboard/feedback?id={feedback.id}",
                        "category": feedback.category,
                        "rating": feedback.rating,
                        "submitter_name": submitter,
                    }
                )
        except Exception as e:
            # Avoid failing submission if notification encounters an issue
            print(f"Error notifying super admins of feedback: {e}")

        response_serializer = PlatformFeedbackSerializer(
            feedback,
            context={"request": request}
        )
        return Response(
            {
                "message": "Thank you! Your feedback has been received by the INDULJ team.",
                "data": response_serializer.data,
            },
            status=status.HTTP_201_CREATED
        )


class MyFeedbackListView(APIView):
    """
    Returns platform feedbacks submitted by the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        feedbacks = PlatformFeedback.objects.filter(
            Q(user=request.user) | Q(user_email=request.user.email)
        ).order_by("-created_at")

        serializer = PlatformFeedbackSerializer(
            feedbacks,
            many=True,
            context={"request": request}
        )
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)


class AdminFeedbackListView(APIView):
    """
    List all platform feedbacks with search, filtering, and sorting.
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        queryset = PlatformFeedback.objects.select_related(
            "user", "replied_by"
        ).all()

        # Search
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user_name__icontains=search)
                | Q(user_email__icontains=search)
                | Q(comments__icontains=search)
                | Q(difficulties__icontains=search)
                | Q(confusing_aspects__icontains=search)
                | Q(feature_requests__icontains=search)
            )

        # Filters
        category = request.query_params.get("category")
        if category and category != "all":
            queryset = queryset.filter(category=category)

        status_param = request.query_params.get("status")
        if status_param and status_param != "all":
            queryset = queryset.filter(status=status_param)

        rating = request.query_params.get("rating")
        if rating and rating.isdigit():
            queryset = queryset.filter(rating=int(rating))

        is_liked = request.query_params.get("is_liked")
        if is_liked in ["true", "1"]:
            queryset = queryset.filter(is_liked=True)
        elif is_liked in ["false", "0"]:
            queryset = queryset.filter(is_liked=False)

        has_reply = request.query_params.get("has_reply")
        if has_reply in ["true", "1"]:
            queryset = queryset.exclude(admin_reply="")
        elif has_reply in ["false", "0"]:
            queryset = queryset.filter(admin_reply="")

        # Sorting
        sort_by = request.query_params.get("sort_by", "newest")
        if sort_by == "oldest":
            queryset = queryset.order_by("created_at")
        elif sort_by == "highest_rating":
            queryset = queryset.order_by("-rating", "-created_at")
        elif sort_by == "lowest_rating":
            queryset = queryset.order_by("rating", "-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        serializer = PlatformFeedbackSerializer(
            queryset,
            many=True,
            context={"request": request}
        )
        return Response(
            {
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK
        )


class AdminFeedbackStatsView(APIView):
    """
    Computes analytical stats for platform feedback.
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        queryset = PlatformFeedback.objects.all()
        total_count = queryset.count()

        if total_count == 0:
            return Response({
                "data": {
                    "total_feedback": 0,
                    "avg_rating": 0,
                    "avg_ease_of_use": 0,
                    "avg_usefulness": 0,
                    "avg_smoothness": 0,
                    "pending_count": 0,
                    "reviewed_count": 0,
                    "resolved_count": 0,
                    "liked_count": 0,
                    "replied_count": 0,
                    "rating_breakdown": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
                    "category_breakdown": {},
                }
            })

        averages = queryset.aggregate(
            avg_rating=Avg("rating"),
            avg_ease=Avg("ease_of_use"),
            avg_usefulness=Avg("usefulness"),
            avg_smoothness=Avg("smoothness"),
        )

        pending_count = queryset.filter(status="pending").count()
        reviewed_count = queryset.filter(status="reviewed").count()
        resolved_count = queryset.filter(status="resolved").count()
        liked_count = queryset.filter(is_liked=True).count()
        replied_count = queryset.exclude(admin_reply="").count()

        # Rating breakdown
        rating_counts = {}
        for r in [5, 4, 3, 2, 1]:
            rating_counts[r] = queryset.filter(rating=r).count()

        # Category breakdown
        category_counts = {}
        for row in queryset.values("category").annotate(count=Count("id")):
            category_counts[row["category"]] = row["count"]

        return Response({
            "data": {
                "total_feedback": total_count,
                "avg_rating": round(averages["avg_rating"] or 0, 1),
                "avg_ease_of_use": round(averages["avg_ease"] or 0, 1),
                "avg_usefulness": round(averages["avg_usefulness"] or 0, 1),
                "avg_smoothness": round(averages["avg_smoothness"] or 0, 1),
                "pending_count": pending_count,
                "reviewed_count": reviewed_count,
                "resolved_count": resolved_count,
                "liked_count": liked_count,
                "replied_count": replied_count,
                "rating_breakdown": rating_counts,
                "category_breakdown": category_counts,
            }
        })


class AdminFeedbackDetailView(APIView):
    """
    Retrieve or delete a single feedback.
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def get_object(self, pk):
        try:
            return PlatformFeedback.objects.select_related("user", "replied_by").get(pk=pk)
        except PlatformFeedback.DoesNotExist:
            return None

    def get(self, request, pk):
        feedback = self.get_object(pk)
        if not feedback:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PlatformFeedbackSerializer(feedback, context={"request": request})
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        feedback = self.get_object(pk)
        if not feedback:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        feedback.delete()
        return Response(
            {"message": "Feedback deleted successfully"},
            status=status.HTTP_200_OK
        )


class AdminFeedbackReplyView(APIView):
    """
    Submit or update super admin's reply to user feedback.
    Sends notification to the user upon replying.
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        try:
            feedback = PlatformFeedback.objects.select_related("user").get(pk=pk)
        except PlatformFeedback.DoesNotExist:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PlatformFeedbackReplySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        reply_text = serializer.validated_data["reply"].strip()
        status_choice = serializer.validated_data.get("status", "reviewed")

        feedback.admin_reply = reply_text
        feedback.replied_at = timezone.now()
        feedback.replied_by = request.user
        feedback.status = status_choice
        feedback.save()

        # Notify the user who submitted the feedback if they are a registered user
        if feedback.user:
            try:
                preview = reply_text[:100] + "..." if len(reply_text) > 100 else reply_text
                create_notification(
                    user=feedback.user,
                    type="system",
                    title="INDULJ Team Replied to Your Feedback",
                    message=f"Admin responded: \"{preview}\"",
                    metadata={
                        "feedback_id": feedback.id,
                        "action_url": "/dashboard",
                    }
                )
            except Exception as e:
                print(f"Error creating user reply notification: {e}")

        response_serializer = PlatformFeedbackSerializer(
            feedback,
            context={"request": request}
        )
        return Response(
            {
                "message": "Reply saved successfully",
                "data": response_serializer.data,
            },
            status=status.HTTP_200_OK
        )


class AdminFeedbackToggleLikeView(APIView):
    """
    Toggle is_liked state for feedback.
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        try:
            feedback = PlatformFeedback.objects.get(pk=pk)
        except PlatformFeedback.DoesNotExist:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        feedback.is_liked = not feedback.is_liked
        feedback.save(update_fields=["is_liked", "updated_at"])

        return Response(
            {
                "message": f"Feedback {'liked' if feedback.is_liked else 'unliked'}",
                "is_liked": feedback.is_liked,
            },
            status=status.HTTP_200_OK
        )


class AdminFeedbackStatusView(APIView):
    """
    Update status of feedback (pending, reviewed, resolved).
    Strictly restricted to Super Admins.
    """
    permission_classes = [IsSuperAdmin]

    def patch(self, request, pk):
        try:
            feedback = PlatformFeedback.objects.get(pk=pk)
        except PlatformFeedback.DoesNotExist:
            return Response({"error": "Feedback not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PlatformFeedbackStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        feedback.status = serializer.validated_data["status"]
        feedback.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "message": f"Status updated to {feedback.status}",
                "status": feedback.status,
            },
            status=status.HTTP_200_OK
        )


class PublicFeedbackListView(APIView):
    """
    Publicly accessible endpoint returning platform feedback/reviews
    to showcase real platform user testimonials on the login page & website.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Return reviews that have comments or feedback content, prioritizing liked and high ratings
        queryset = PlatformFeedback.objects.exclude(
            comments="",
            feature_requests="",
            difficulties=""
        ).order_by("-is_liked", "-rating", "-created_at")[:20]

        serializer = PlatformFeedbackSerializer(
            queryset,
            many=True,
            context={"request": request}
        )
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

