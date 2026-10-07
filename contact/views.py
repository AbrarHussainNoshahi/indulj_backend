import logging
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import ContactMessage
from .serializers import ContactMessageSerializer
from .email_utils import send_contact_email_to_admin, get_superadmin_contact_recipients
from accounts.models import User
from accounts.permissions import IsSuperAdmin
from notifications.utils import create_notification

logger = logging.getLogger(__name__)


class ContactMessageCreateView(APIView):
    """
    Public or authenticated submission endpoint for contacting SuperAdmin.
    Saves inquiry to DB, sends HTML email to configured SuperAdmin,
    and dispatches in-app notification to active super admins.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        contact_msg = serializer.save()

        # Link authenticated user if logged in
        if request.user and request.user.is_authenticated:
            contact_msg.user = request.user
            contact_msg.save(update_fields=["user"])

        # Send email to SuperAdmin
        email_ok, email_info = send_contact_email_to_admin(contact_msg)
        if email_ok:
            contact_msg.email_sent = True
            contact_msg.save(update_fields=["email_sent"])
        else:
            logger.warning(f"Contact email sending issue: {email_info}")

        # Send in-app notification to SuperAdmins
        try:
            super_admins = User.objects.filter(
                role="admin",
                is_active=True,
                is_suspended=False
            ).filter(
                Q(admin_type="super_admin") | Q(is_superuser=True)
            )

            preview_msg = f"From: {contact_msg.name} ({contact_msg.email})\nSubject: {contact_msg.subject}\n\n{contact_msg.message[:150]}"
            for admin in super_admins:
                create_notification(
                    user=admin,
                    type="system",
                    title=f"📩 Contact Inquiry: {contact_msg.subject[:60]}",
                    message=preview_msg,
                    metadata={
                        "contact_id": contact_msg.id,
                        "email": contact_msg.email,
                        "inquiry_type": contact_msg.inquiry_type,
                    }
                )
        except Exception as notify_err:
            logger.warning(f"Failed to create admin in-app notification: {notify_err}")

        recipients = get_superadmin_contact_recipients()

        return Response(
            {
                "success": True,
                "message": "Thank you! Your message has been sent to the SuperAdmin team. We will get back to you shortly.",
                "email_dispatched": email_ok,
                "admin_recipient": ", ".join(recipients),
                "data": ContactMessageSerializer(contact_msg).data,
            },
            status=status.HTTP_201_CREATED
        )


class AdminContactMessagePagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminContactMessageListView(APIView):
    """
    Super Admin endpoint to list all contact inquiries with filters and search.
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = ContactMessage.objects.all().order_by("-created_at")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(subject__icontains=search) |
                Q(message__icontains=search)
            )

        inquiry_type = request.query_params.get("inquiry_type")
        if inquiry_type:
            qs = qs.filter(inquiry_type=inquiry_type)

        is_read = request.query_params.get("is_read")
        if is_read is not None:
            if is_read.lower() == "true":
                qs = qs.filter(is_read=True)
            elif is_read.lower() == "false":
                qs = qs.filter(is_read=False)

        paginator = AdminContactMessagePagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ContactMessageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminContactMessageDetailView(APIView):
    """
    Super Admin endpoint to get or mark read a specific contact message.
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        try:
            msg = ContactMessage.objects.get(pk=pk)
        except ContactMessage.DoesNotExist:
            return Response({"error": "Message not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(ContactMessageSerializer(msg).data)

    def patch(self, request, pk):
        try:
            msg = ContactMessage.objects.get(pk=pk)
        except ContactMessage.DoesNotExist:
            return Response({"error": "Message not found"}, status=status.HTTP_404_NOT_FOUND)

        is_read = request.data.get("is_read")
        admin_notes = request.data.get("admin_notes")

        if is_read is not None:
            msg.is_read = bool(is_read)
        if admin_notes is not None:
            msg.admin_notes = str(admin_notes)

        msg.save()
        return Response(ContactMessageSerializer(msg).data)
