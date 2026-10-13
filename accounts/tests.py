from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Referral, PointsTransaction, ReceiptScan, OTPVerification
from restaurants.models import Restaurant
from deals.models import Deal

User = get_user_model()

class PointsRewardsTests(APITestCase):
    def setUp(self):
        # Create standard user (referrer)
        self.referrer = User.objects.create_user(
            email="referrer@example.com",
            password="Password123!",
            full_name="Referrer User",
            phone_number="1234567890",
        )
        self.referrer.is_email_verified = True
        self.referrer.save()

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
            full_name="Admin User",
        )

        # Create restaurant for tests
        self.restaurant_owner = User.objects.create_user(
            email="owner@example.com",
            password="Password123!",
            full_name="Owner User"
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.restaurant_owner,
            name="Test Restaurant",
            address="123 Test St",
            city="Testville",
            operating_hours={"open": "09:00", "close": "22:00"}
        )

    def test_referral_rewards_flow(self):
        # 1. Register a new user using the referrer's code
        ref_code = self.referrer.referral_code
        response = self.client.post("/api/auth/register/", {
            "full_name": "Referred User",
            "email": "referred@example.com",
            "phone": "0987654321",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "referral_code": ref_code
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        # Fetch the referred user and verify they have referred_by_code set
        referred_user = User.objects.get(email="referred@example.com")
        self.assertEqual(referred_user.referred_by_code, ref_code)
        self.assertFalse(referred_user.is_email_verified)

        # Confirm referrer hasn't got points yet (requires OTP verification)
        self.referrer.refresh_from_db()
        self.assertEqual(self.referrer.points, 0)

        # Get OTP
        otp_record = OTPVerification.objects.filter(user=referred_user).last()
        self.assertIsNotNone(otp_record)

        # 2. Verify OTP
        response = self.client.post("/api/auth/verify-otp/", {
            "email": "referred@example.com",
            "otp": otp_record.otp
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Confirm referrer now got 100 points!
        self.referrer.refresh_from_db()
        self.assertEqual(self.referrer.points, 100)

        # Verify PointsTransaction was created
        tx = PointsTransaction.objects.filter(user=self.referrer).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.points, 100)
        self.assertEqual(tx.status, "approved")
        self.assertIn("Referral bonus", tx.text)

        # Verify Referral record exists
        referral_record = Referral.objects.filter(referrer=self.referrer, referred_user=referred_user).exists()
        self.assertTrue(referral_record)

        # Verify Notification exists for referrer
        from notifications.models import Notification
        notif = Notification.objects.filter(user=self.referrer).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, "system")
        self.assertIn("referral code", notif.message.lower())

    def test_deal_approval_rewards_points(self):
        # Create a pending deal submitted by referrer
        deal = Deal.objects.create(
            restaurant=self.restaurant,
            submitted_by=self.referrer,
            title="Referrer's Hot Deal",
            description="Super hot deal!",
            price=9.99,
            status="pending"
        )

        # Log in as admin
        self.client.force_authenticate(user=self.admin_user)

        # Approve deal
        response = self.client.post(f"/api/deals/admin/{deal.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check if referrer user gained 50 points
        self.referrer.refresh_from_db()
        self.assertEqual(self.referrer.points, 50)

        # Check transaction history
        tx = PointsTransaction.objects.filter(user=self.referrer).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.points, 50)
        self.assertEqual(tx.status, "approved")
        self.assertIn("Deal submitted", tx.text)

    def test_receipt_scan_flow(self):
        self.client.force_authenticate(user=self.referrer)

        # Create temporary dummy file for receipt (valid PNG)
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        file = io.BytesIO()
        image = Image.new('RGB', (1, 1), color='red')
        image.save(file, 'png')
        file.seek(0)
        
        receipt_image = SimpleUploadedFile("receipt.png", file.read(), content_type="image/png")

        # 1. Upload receipt scan
        response = self.client.post("/api/auth/rewards/receipts/", {
            "restaurant": self.restaurant.id,
            "restaurant_name": "",
            "receipt_image": receipt_image,
            "amount": "45.50",
            "receipt_date": "2026-07-04"
        }, format='multipart')

        if response.status_code == 400:
            print("VALIDATION ERRORS:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        # Check that receipt scan and transaction exist in pending status
        scan = ReceiptScan.objects.filter(user=self.referrer).first()
        self.assertIsNotNone(scan)
        self.assertEqual(scan.status, "pending")
        self.assertEqual(float(scan.amount), 45.50)

        tx = PointsTransaction.objects.filter(user=self.referrer).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.status, "pending")
        self.assertEqual(tx.points, 25)

        # 2. Admin verifies and approves the receipt
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(f"/api/auth/admin/receipts/{scan.pk}/verify/", {
            "status": "approved"
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify points awarded
        self.referrer.refresh_from_db()
        self.assertEqual(self.referrer.points, 25)

        scan.refresh_from_db()
        self.assertEqual(scan.status, "approved")

        tx.refresh_from_db()
        self.assertEqual(tx.status, "approved")
        self.assertEqual(tx.points, 25)


class RegistrationEmailTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="superadmin@example.com",
            password="Password123!",
            full_name="Super Admin",
        )

    def test_admin_create_restaurant_sends_email(self):
        from unittest.mock import patch
        self.client.force_authenticate(user=self.admin)

        with patch("accounts.registration_emails.send_restaurant_registration_email") as mock_email:
            response = self.client.post("/api/restaurants/create/", {
                "restaurant_name": "Email Test Bistro",
                "email": "bistro@example.com",
                "password": "SecretPassword123",
                "owner_name": "Chef Mario",
                "location": "456 Food St",
                "city": "Chicago",
                "phone": "555-1234",
                "latitude": 41.8781,
                "longitude": -87.6298,
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            mock_email.assert_called_once_with(
                restaurant_name="Email Test Bistro",
                owner_name="Chef Mario",
                email="bistro@example.com",
                password="SecretPassword123",
            )

    def test_admin_register_unregistered_restaurant_sends_email(self):
        from unittest.mock import patch
        # Create an unregistered restaurant
        unregistered = Restaurant.objects.create(
            name="Unregistered Cafe",
            address="789 Street",
            city="New York",
            owner=None,
        )

        self.client.force_authenticate(user=self.admin)
        with patch("accounts.registration_emails.send_restaurant_registration_email") as mock_email:
            response = self.client.put(f"/api/restaurants/{unregistered.id}/update/", {
                "name": "Registered Cafe",
                "owner_name": "Cafe Owner",
                "owner_email": "cafeowner@example.com",
                "password": "CafePassword456",
            })
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_email.assert_called_once_with(
                restaurant_name="Registered Cafe",
                owner_name="Cafe Owner",
                email="cafeowner@example.com",
                password="CafePassword456",
            )

    def test_super_admin_create_sub_admin_sends_email(self):
        from unittest.mock import patch
        self.client.force_authenticate(user=self.admin)

        with patch("accounts.registration_emails.send_sub_admin_registration_email") as mock_email:
            response = self.client.post("/api/auth/admin/staff/create/", {
                "full_name": "John Subadmin",
                "email": "john.subadmin@example.com",
                "password": "SubadminPassword789",
                "designation": "Regional Manager",
                "admin_type": "employee",
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            mock_email.assert_called_once()
            call_kwargs = mock_email.call_args[1]
            self.assertEqual(call_kwargs["full_name"], "John Subadmin")
            self.assertEqual(call_kwargs["email"], "john.subadmin@example.com")
            self.assertEqual(call_kwargs["password"], "SubadminPassword789")
            self.assertEqual(call_kwargs["designation"], "Regional Manager")
            self.assertEqual(call_kwargs["admin_type"], "employee")

    def test_email_html_templates_contain_credentials(self):
        from accounts.registration_emails import (
            build_restaurant_registration_email_html,
            build_sub_admin_registration_email_html,
        )

        rest_html = build_restaurant_registration_email_html(
            restaurant_name="Taco Palace",
            owner_name="Carlos",
            email="carlos@taco.com",
            password="TacoPassword123",
            login_url="https://indulj.vercel.app/restaurant/login",
        )
        self.assertIn("Taco Palace", rest_html)
        self.assertIn("carlos@taco.com", rest_html)
        self.assertIn("TacoPassword123", rest_html)
        self.assertIn("https://indulj.vercel.app/restaurant/login", rest_html)

        sub_admin_html = build_sub_admin_registration_email_html(
            full_name="Sarah Staff",
            email="sarah@indulj.com",
            password="SarahPassword456",
            designation="Operations Lead",
            unique_id="SL-1234",
            admin_type="employee",
            login_url="https://indulj.vercel.app/login",
        )
        self.assertIn("Sarah Staff", sub_admin_html)
        self.assertIn("sarah@indulj.com", sub_admin_html)
        self.assertIn("SarahPassword456", sub_admin_html)
        self.assertIn("Operations Lead", sub_admin_html)
        self.assertIn("SL-1234", sub_admin_html)
        self.assertIn("https://indulj.vercel.app/login", sub_admin_html)

