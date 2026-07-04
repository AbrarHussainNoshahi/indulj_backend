from django.db import IntegrityError
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsRestaurant, IsUser
from restaurants.models import Restaurant

from .models import Deal, SavedDeal, DealView
from .serializers import (
    DealListSerializer,
    DealDetailSerializer,
    SubmitDealSerializer,
    CreateDealSerializer,
    RejectDealSerializer,
    SavedDealSerializer,
    AdminCreateDealSerializer,
)

from django.utils import timezone
from datetime import timedelta
from notifications.utils import create_notification, notify_admins


# PUBLIC

class PublicDealListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Deal.objects.filter(
            status="active",
            restaurant__status="active",
        ).select_related("restaurant", "submitted_by")

        restaurant_id = request.query_params.get("restaurant")
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)

        food_type = request.query_params.get("food_type")
        if food_type:
            qs = qs.filter(food_type=food_type)

        day = request.query_params.get("day_of_week")
        if day:
            qs = qs.filter(day_of_week=day)

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        is_hot = request.query_params.get("is_hot_deal")
        if is_hot in ["true", "1", "yes"]:
            qs = qs.filter(is_hot_deal=True)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class PublicDealDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant", "submitted_by").get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.views_count += 1
        deal.save(update_fields=["views_count"])

        return Response({
            "success": True,
            "data": DealDetailSerializer(deal, context={"request": request}).data,
        })


class MapDealsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Deal.objects.filter(
            status="active",
            restaurant__status="active",
            restaurant__latitude__isnull=False,
            restaurant__longitude__isnull=False,
        ).select_related("restaurant")

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        day = request.query_params.get("day")
        if day:
            qs = qs.filter(day_of_week=day)

        data = [
            {
                "id": deal.id,
                "title": deal.title,
                "restaurant_name": deal.restaurant.name,
                "latitude": deal.restaurant.latitude,
                "longitude": deal.restaurant.longitude,
                "is_hot_deal": deal.is_hot_deal,
                "price": str(deal.price),
                "food_type": deal.food_type,
                "day_of_week": deal.day_of_week,
            }
            for deal in qs
        ]

        return Response({"success": True, "data": data})
    
class TrackDealView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk)
        except Deal.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        session_id = request.data.get("session_id") or None
        user = request.user if request.user.is_authenticated else None

        # prevent spam (30 min window)
        recent = DealView.objects.filter(
            deal=deal,
            user=user,
            session_id=session_id,
            created_at__gte=timezone.now() - timedelta(minutes=30),
        ).exists()

        if recent:
            return Response({"message": "already counted"}, status=200)

        try:
            DealView.objects.create(
                deal=deal,
                user=user,
                session_id=session_id,
                ip_address=self.get_client_ip(request),
            )

            deal.views_count = (deal.views_count or 0) + 1
            deal.save(update_fields=["views_count"])

        except IntegrityError:
            # fallback safety (VERY IMPORTANT)
            return Response({"message": "duplicate ignored"}, status=200)

        return Response({"message": "view counted"}, status=201)

    def get_client_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0]
        return request.META.get("REMOTE_ADDR")

# USER

class SubmitDealView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = SubmitDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        restaurant_name = data.get("restaurant_name")

        try:
            restaurant = Restaurant.objects.get(
                name__iexact=restaurant_name,
                status="active",
            )
        except Restaurant.DoesNotExist:
            return Response(
                {"restaurant_name": ["Active restaurant not found."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if restaurant operating hours are set
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "This restaurant has not configured its operating hours yet. Deals cannot be created for it."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="user",
            title=data.get("title") or f"{restaurant.name} Deal",
            description=data.get("description"),
            price=data.get("price"),
            food_type=data.get("food_type"),
            day_of_week=data.get("day_of_week"),
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=data.get("location_branch", ""),
            image=data.get("image"),
            status="pending",
        )

        notify_admins(
            type="deal",
            title="New Deal Submitted",
            message=f"A new deal '{deal.title}' has been submitted for approval.",
            related_deal=deal,
        )

        if restaurant.owner:
            create_notification(
                user=restaurant.owner,
                type="deal",
                title="New Deal Submitted",
                message=f"A customer has submitted a new deal '{deal.title}' for your restaurant. It is pending admin approval.",
                related_deal=deal,
            )

        response_serializer = DealDetailSerializer(
            deal,
            context={"request": request},
        )

        return Response(
            {
                "message": "Deal submitted successfully. Waiting for admin approval.",
                "data": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

class MyDealsView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        qs = Deal.objects.filter(submitted_by=request.user).select_related("restaurant")

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({"success": True, "data": serializer.data})


class DeleteMyDealView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def delete(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk, submitted_by=request.user)
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if deal.status == "active":
            return Response(
                {"success": False, "message": "Active deals cannot be deleted by user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})


class SaveDealView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        saved, created = SavedDeal.objects.get_or_create(
            user=request.user,
            deal=deal,
        )

        if not created:
            return Response(
                {"success": False, "message": "Deal already saved"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"success": True, "message": "Deal saved"},
            status=status.HTTP_201_CREATED,
        )


class UnsaveDealView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def delete(self, request, pk):
        try:
            saved = SavedDeal.objects.get(user=request.user, deal_id=pk)
        except SavedDeal.DoesNotExist:
            return Response(
                {"success": False, "message": "Saved deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        saved.delete()
        return Response({"success": True, "message": "Deal unsaved"})


class SavedDealsView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        saved = SavedDeal.objects.filter(user=request.user).select_related(
            "deal__restaurant"
        )

        search = request.query_params.get("search")
        if search:
            saved = saved.filter(deal__title__icontains=search)

        serializer = SavedDealSerializer(saved, many=True, context={"request": request})

        return Response({"success": True, "data": serializer.data})


# RESTAURANT

class RestaurantDealListView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Deal.objects.filter(restaurant=restaurant).select_related("submitted_by")

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class RestaurantCreateDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "Please set your restaurant's operating hours in your profile settings before creating a deal."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal = serializer.save(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="restaurant",
            status="pending",
        )

        notify_admins(
            type="deal",
            title="New Deal Submitted",
            message=f"A new deal '{deal.title}' has been submitted for approval.",
            related_deal=deal,
        )

        return Response(
            {
                "success": True,
                "message": "Deal created. Pending admin approval.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RestaurantUpdateDeleteDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_deal(self, pk, user):
        try:
            return Deal.objects.get(
                pk=pk,
                restaurant__owner=user,
                created_by_role="restaurant",
            )
        except Deal.DoesNotExist:
            return None

    def put(self, request, pk):
        deal = self.get_deal(pk, request.user)

        if not deal:
            return Response(
                {
                    "success": False,
                    "message": "Deal not found or you cannot edit customer-submitted deal.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if deal.status == "active":
            return Response(
                {"success": False, "message": "Active deals cannot be edited directly."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateDealSerializer(deal, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save(status="pending", rejection_reason="")

            notify_admins(
                type="deal",
                title="New Deal Submitted",
                message=f"A new deal '{deal.title}' has been submitted for approval.",
                related_deal=deal,
            )

            return Response({
                "success": True,
                "message": "Deal updated. Pending admin approval again.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            })

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):
        deal = self.get_deal(pk, request.user)

        if not deal:
            return Response(
                {
                    "success": False,
                    "message": "Deal not found or you cannot delete customer-submitted deal.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if deal.status == "active":
            return Response(
                {"success": False, "message": "Active deals cannot be deleted directly."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})


# ADMIN

class AdminCreateDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = AdminCreateDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        restaurant = Restaurant.objects.filter(
            name__icontains=data["restaurant_name"],
            status="active",
        ).first()

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": f"Restaurant '{data['restaurant_name']}' not found or not active.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": f"Restaurant '{restaurant.name}' has not configured its operating hours yet. Deals cannot be created for it."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="admin",
            title=data["title"],
            description=data["description"],
            price=data["price"],
            food_type=data["food_type"],
            day_of_week=data["day_of_week"],
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=data.get("location_branch", ""),
            discount_percentage=data.get("discount_percentage", ""),
            image=data.get("image"),
            is_hot_deal=data.get("is_hot_deal", False),
            expires_at=data.get("expires_at"),
            status=data.get("status", "active"),
        )

        return Response(
            {
                "success": True,
                "message": "Deal created successfully.",
                "data": DealListSerializer(
                    deal,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminDealListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = Deal.objects.select_related("restaurant", "submitted_by").all()

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        food_type = request.query_params.get("food_type")
        if food_type:
            qs = qs.filter(food_type=food_type)

        restaurant = request.query_params.get("restaurant")
        if restaurant:
            qs = qs.filter(restaurant_id=restaurant)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class AdminApproveDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk, status="pending")
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found or not pending approval"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.status = "active"
        deal.rejection_reason = ""
        deal.save(update_fields=["status", "rejection_reason"])

        if deal.submitted_by:
            from accounts.models import PointsTransaction
            submitter = deal.submitted_by
            submitter.points += 50
            submitter.save(update_fields=["points"])
            PointsTransaction.objects.create(
                user=submitter,
                text=f"Deal submitted - {deal.title}",
                status="approved",
                points=50
            )

        if deal.submitted_by:
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Approved! 🎉",
                message=f"Your deal '{deal.title}' has been approved.",
                related_deal=deal,
            )
        if deal.restaurant.owner and deal.restaurant.owner != deal.submitted_by:
            create_notification(
                user=deal.restaurant.owner,
                type="deal",
                title="Deal Approved! 🎉",
                message=f"Your deal '{deal.title}' has been approved.",
                related_deal=deal,
            )

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' approved",
        })
        
class AdminToggleHotDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk)
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.is_hot_deal = not deal.is_hot_deal
        deal.save(update_fields=["is_hot_deal"])

        return Response({
            "success": True,
            "message": "Deal marked as hot" if deal.is_hot_deal else "Deal removed from hot deals",
            "is_hot_deal": deal.is_hot_deal,
        })


class AdminRejectDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk)
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RejectDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.status = "rejected"
        deal.rejection_reason = serializer.validated_data["rejection_reason"]
        deal.save(update_fields=["status", "rejection_reason"])

        if deal.submitted_by:
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Rejected",
                message=f"Your deal '{deal.title}' was rejected. Reason: {deal.rejection_reason}",
                related_deal=deal,
            )
        if deal.restaurant.owner and deal.restaurant.owner != deal.submitted_by:
            create_notification(
                user=deal.restaurant.owner,
                type="deal",
                title="Deal Rejected",
                message=f"Your deal '{deal.title}' was rejected. Reason: {deal.rejection_reason}",
                related_deal=deal,
            )

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' rejected",
        })


class AdminAcceptAllDealsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        pending = Deal.objects.filter(status="pending")
        count = pending.count()

        pending.update(status="active", rejection_reason="")

        return Response({
            "success": True,
            "message": f"{count} pending deals approved",
        })


class AdminDeleteDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk)
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})