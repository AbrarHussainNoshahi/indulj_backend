from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification
from .serializers import NotificationSerializer
from .utils import check_and_expire_happy_hours

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        check_and_expire_happy_hours()
        user = request.user
        qs = Notification.objects.select_related(
            'related_order',
            'related_deal',
            'related_happy_hour',
            'related_restaurant'
        ).filter(user=user)

        # Filters
        notification_type = request.query_params.get('type')
        if notification_type and notification_type != 'all':
            qs = qs.filter(type=notification_type)

        is_read_param = request.query_params.get('is_read')
        if is_read_param:
            if is_read_param.lower() == 'true':
                qs = qs.filter(is_read=True)
            elif is_read_param.lower() == 'false':
                qs = qs.filter(is_read=False)

        unread_param = request.query_params.get('unread')
        if unread_param and unread_param.lower() == 'true':
            qs = qs.filter(is_read=False)

        unread_count = Notification.objects.filter(user=user, is_read=False).count()
        count = qs.count()

        limit = request.query_params.get('limit')
        if limit:
            try:
                limit = int(limit)
                qs = qs[:limit]
            except ValueError:
                pass

        serializer = NotificationSerializer(qs, many=True, context={'request': request})
        return Response({
            "success": True,
            "count": count,
            "unread_count": unread_count,
            "data": serializer.data
        })


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        check_and_expire_happy_hours()
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({
            "success": True,
            "count": unread_count,
            "unread_count": unread_count
        })


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response({
            "success": True,
            "message": "All notifications marked as read."
        })


class ClearAllView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        qs = Notification.objects.filter(user=request.user)
        only_read = request.query_params.get('only_read')
        if only_read and only_read.lower() == 'true':
            qs = qs.filter(is_read=True)
        
        count, _ = qs.delete()
        return Response({
            "success": True,
            "message": f"Successfully cleared {count} notifications."
        })


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({
                "success": False,
                "message": "Notification not found."
            }, status=status.HTTP_404_NOT_FOUND)

        notification.mark_read()
        serializer = NotificationSerializer(notification, context={'request': request})
        return Response({
            "success": True,
            "data": serializer.data
        })


class DeleteNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({
                "success": False,
                "message": "Notification not found."
            }, status=status.HTTP_404_NOT_FOUND)

        notification.delete()
        return Response({
            "success": True,
            "message": "Notification deleted."
        })
