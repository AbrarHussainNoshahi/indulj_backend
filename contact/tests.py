from django.test import TestCase, override_settings
from django.core import mail
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from .models import ContactMessage
from .email_utils import build_contact_email_html, get_superadmin_contact_recipients


class ContactMessageTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superadmin = User.objects.create_superuser(
            email="superadmin@indulj.com",
            password="testpassword123",
            role="admin",
            admin_type="super_admin",
            full_name="Super Admin User"
        )

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        SUPERADMIN_CONTACT_EMAIL='admin_test@indulj.com'
    )
    def test_guest_can_submit_contact_message_and_send_email(self):
        payload = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555-123-4567",
            "inquiry_type": "restaurant",
            "subject": "Restaurant Partnership Inquiry",
            "message": "Hello, I would like to partner with INDULJ for our local restaurant."
        }
        response = self.client.post("/api/contact/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["email_dispatched"])

        # Check DB
        msg = ContactMessage.objects.first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.name, "Jane Doe")
        self.assertEqual(msg.email, "jane@example.com")
        self.assertEqual(msg.inquiry_type, "restaurant")
        self.assertTrue(msg.email_sent)
        self.assertIsNone(msg.user)

        # Check email sent via locmem
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn("Restaurant Partnership Inquiry", sent_email.subject)
        self.assertEqual(sent_email.to, ["admin_test@indulj.com"])
        self.assertEqual(sent_email.reply_to, ["jane@example.com"])
        self.assertIn("Jane Doe", sent_email.body)
        self.assertIn("jane@example.com", sent_email.body)

        # Verify HTML alternative
        self.assertEqual(len(sent_email.alternatives), 1)
        html_content, mimetype = sent_email.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("INDULJ", html_content)
        self.assertIn("Jane Doe", html_content)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        SUPERADMIN_CONTACT_EMAIL='admin_test@indulj.com'
    )
    def test_authenticated_user_submits_contact_message(self):
        normal_user = User.objects.create_user(
            email="normaluser@example.com",
            password="testpassword123",
            role="user",
            full_name="Alice User"
        )
        self.client.force_authenticate(user=normal_user)

        payload = {
            "name": "Alice User",
            "email": "normaluser@example.com",
            "inquiry_type": "support",
            "subject": "Need help with saved deals",
            "message": "My saved deals list is not updating properly."
        }
        response = self.client.post("/api/contact/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        msg = ContactMessage.objects.filter(email="normaluser@example.com").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.user, normal_user)

    def test_validation_errors(self):
        # Missing required fields
        response = self.client.post("/api/contact/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data["details"])
        self.assertIn("email", response.data["details"])
        self.assertIn("subject", response.data["details"])
        self.assertIn("message", response.data["details"])
