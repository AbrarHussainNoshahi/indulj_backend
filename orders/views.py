from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsAdmin, IsRestaurant, IsUser
from .models import Order
from .serializers import (
    CreateOrderSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderResponseSerializer,
    RejectOrderSerializer,
)


def filter_orders(qs, request):
    status_filter = request.query_params.get("status")
    order_type = request.query_params.get("order_type")
    search = request.query_params.get("search")
    restaurant = request.query_params.get("restaurant")
    ordering = request.query_params.get("ordering", "-created_at")

    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)

    if order_type and order_type != "all":
        qs = qs.filter(order_type=order_type)

    if restaurant:
        qs = qs.filter(restaurant_id=restaurant)

    if search:
        qs = qs.filter(
            Q(order_number__icontains=search)
            | Q(deal__title__icontains=search)
            | Q(happy_hour__title__icontains=search)
            | Q(restaurant__name__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__full_name__icontains=search)
            | Q(notes__icontains=search)
        )

    if ordering in ["created_at", "-created_at", "updated_at", "-updated_at"]:
        qs = qs.order_by(ordering)

    return qs


class CreateOrderView(APIView):
    permission_classes = [IsUser]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        order = Order.objects.create(
            user=request.user,
            restaurant=data["restaurant"],
            deal=data.get("deal_obj"),
            happy_hour=data.get("happy_hour_obj"),
            order_type=data["order_type"],
            items=data.get("items", []),
            quantity=data.get("quantity", 1),
            group_size=data.get("group_size", 1),
            booking_date=data.get("booking_date"),
            booking_time=data.get("booking_time"),
            notes=data.get("notes", ""),
            total_amount=data.get("total_amount", 0),
            status="pending",
        )

        self._notify_restaurant(order)

        return Response(
            {
                "success": True,
                "message": "Booking created successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _notify_restaurant(self, order):
        try:
            from notifications.models import Notification

            Notification.objects.create(
                user=order.restaurant.owner,
                type="order",
                title=f"New Booking {order.order_number}",
                message=f"{order.user.full_name} created a new {order.order_type.replace('_', ' ')} booking.",
                related_order=order,
            )
        except Exception:
            pass


class MyOrdersView(APIView):
    permission_classes = [IsUser]

    def get(self, request):
        qs = Order.objects.select_related(
            "user",
            "restaurant",
            "deal",
            "happy_hour",
        ).filter(user=request.user)

        qs = filter_orders(qs, request)

        serializer = OrderListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "count": qs.count(),
                "data": serializer.data,
            }
        )


class CancelMyOrderView(APIView):
    permission_classes = [IsUser]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "pending":
            return Response(
                {
                    "success": False,
                    "message": "Only pending orders can be cancelled.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.mark_cancelled()

        return Response(
            {
                "success": True,
                "message": "Order cancelled successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class DeleteMyOrderView(APIView):
    permission_classes = [IsUser]

    def delete(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status not in ["cancelled", "rejected"]:
            return Response(
                {
                    "success": False,
                    "message": "Only cancelled or rejected orders can be deleted.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.delete()

        return Response(
            {
                "success": True,
                "message": "Order deleted successfully.",
            }
        )


class RestaurantOrderListView(APIView):
    permission_classes = [IsRestaurant]

    def get(self, request):
        try:
            restaurant = request.user.restaurant
        except Exception:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant profile not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Order.objects.select_related(
            "user",
            "restaurant",
            "deal",
            "happy_hour",
        ).filter(restaurant=restaurant)

        qs = filter_orders(qs, request)

        serializer = OrderListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "count": qs.count(),
                "data": serializer.data,
            }
        )


class RestaurantOrderDetailView(APIView):
    permission_classes = [IsRestaurant]

    def get(self, request, pk):
        try:
            order = Order.objects.select_related(
                "user",
                "restaurant",
                "deal",
                "happy_hour",
            ).get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class RestaurantAcceptOrderView(APIView):
    permission_classes = [IsRestaurant]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "pending":
            return Response(
                {
                    "success": False,
                    "message": "Only pending orders can be accepted.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order.mark_confirmed(serializer.validated_data.get("response", ""))

        self._notify_user(order, "Order Confirmed", f"Your booking {order.order_number} has been confirmed.")

        return Response(
            {
                "success": True,
                "message": "Order accepted successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )

    def _notify_user(self, order, title, message):
        try:
            from notifications.models import Notification

            Notification.objects.create(
                user=order.user,
                type="order",
                title=title,
                message=message,
                related_order=order,
            )
        except Exception:
            pass


class RestaurantRejectOrderView(APIView):
    permission_classes = [IsRestaurant]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "pending":
            return Response(
                {
                    "success": False,
                    "message": "Only pending orders can be rejected.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RejectOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data["rejection_reason"]
        order.mark_rejected(reason)

        self._notify_user(order, "Order Rejected", f"Your booking {order.order_number} was rejected. Reason: {reason}")

        return Response(
            {
                "success": True,
                "message": "Order rejected successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )

    def _notify_user(self, order, title, message):
        try:
            from notifications.models import Notification

            Notification.objects.create(
                user=order.user,
                type="order",
                title=title,
                message=message,
                related_order=order,
            )
        except Exception:
            pass


class RestaurantCompleteOrderView(APIView):
    permission_classes = [IsRestaurant]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "confirmed":
            return Response(
                {
                    "success": False,
                    "message": "Only confirmed orders can be completed.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.mark_completed()

        return Response(
            {
                "success": True,
                "message": "Order completed successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class RestaurantDeleteOrderView(APIView):
    permission_classes = [IsRestaurant]

    def delete(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status == "pending":
            return Response(
                {
                    "success": False,
                    "message": "Reject the order before deleting it.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.delete()

        return Response(
            {
                "success": True,
                "message": "Order deleted successfully.",
            }
        )


class AdminOrderListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = Order.objects.select_related(
            "user",
            "restaurant",
            "deal",
            "happy_hour",
        ).all()

        qs = filter_orders(qs, request)

        serializer = OrderListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "count": qs.count(),
                "data": serializer.data,
            }
        )


class AdminOrderDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        try:
            order = Order.objects.select_related(
                "user",
                "restaurant",
                "deal",
                "happy_hour",
            ).get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )

    def delete(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        order.delete()

        return Response(
            {
                "success": True,
                "message": "Order deleted successfully.",
            }
        )


class AdminAcceptOrderView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "pending":
            return Response(
                {
                    "success": False,
                    "message": "Only pending orders can be accepted.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order.mark_confirmed(serializer.validated_data.get("response", "Accepted by admin"))

        return Response(
            {
                "success": True,
                "message": "Order accepted successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class AdminRejectOrderView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "pending":
            return Response(
                {
                    "success": False,
                    "message": "Only pending orders can be rejected.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RejectOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order.mark_rejected(serializer.validated_data["rejection_reason"])

        return Response(
            {
                "success": True,
                "message": "Order rejected successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class AdminCompleteOrderView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "confirmed":
            return Response(
                {
                    "success": False,
                    "message": "Only confirmed orders can be completed.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.mark_completed()

        return Response(
            {
                "success": True,
                "message": "Order completed successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class AdminCancelOrderView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Order not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status in ["completed", "rejected", "cancelled"]:
            return Response(
                {
                    "success": False,
                    "message": "This order cannot be cancelled.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.mark_cancelled()

        return Response(
            {
                "success": True,
                "message": "Order cancelled successfully.",
                "data": OrderDetailSerializer(
                    order,
                    context={"request": request},
                ).data,
            }
        )


class AdminAcceptAllOrdersView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        qs = Order.objects.filter(status="pending")
        count = qs.count()

        for order in qs:
            order.mark_confirmed("Accepted by admin")

        return Response(
            {
                "success": True,
                "message": f"{count} pending orders accepted.",
                "count": count,
            }
        )