from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from feedback.models import PlatformFeedback
from notifications.models import Notification


class PlatformFeedbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Super Admin
        self.super_admin = User.objects.create_user(
            email="superadmin@indulj.com",
            password="Password123!",
            full_name="Super Admin User",
            role="admin",
            admin_type="super_admin",
            is_email_verified=True,
        )

        # 2. Sub-Admin / Employee Admin
        self.sub_admin = User.objects.create_user(
            email="subadmin@indulj.com",
            password="Password123!",
            full_name="Sub Admin Employee",
            role="admin",
            admin_type="employee",
            is_email_verified=True,
        )

        # 3. Regular User
        self.regular_user = User.objects.create_user(
            email="user@example.com",
            password="Password123!",
            full_name="Alice Customer",
            role="user",
            is_email_verified=True,
        )

    def test_submit_feedback_authenticated(self):
        self.client.force_authenticate(user=self.regular_user)
        payload = {
            "rating": 5,
            "ease_of_use": 4,
            "usefulness": 5,
            "smoothness": 4,
            "category": "features",
            "difficulties": "None, worked well",
            "confusing_aspects": "Points redemption was slightly tricky",
            "feature_requests": "Dark mode option and apple pay",
            "comments": "Love the app!",
        }

        response = self.client.post(reverse("feedback-submit"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        feedback = PlatformFeedback.objects.get(id=response.data["data"]["id"])
        self.assertEqual(feedback.user, self.regular_user)
        self.assertEqual(feedback.rating, 5)
        self.assertEqual(feedback.feature_requests, "Dark mode option and apple pay")

        # Verify Super Admin received notification
        super_admin_notifs = Notification.objects.filter(user=self.super_admin, type="feedback")
        self.assertEqual(super_admin_notifs.count(), 1)
        notif = super_admin_notifs.first()
        self.assertIn("New INDULJ Feedback", notif.title)
        self.assertEqual(notif.metadata["feedback_id"], feedback.id)
        self.assertEqual(notif.metadata["action_url"], f"/admin/dashboard/feedback?id={feedback.id}")

        # Verify Sub-Admin did NOT receive notification
        sub_admin_notifs = Notification.objects.filter(user=self.sub_admin, type="feedback")
        self.assertEqual(sub_admin_notifs.count(), 0)

    def test_sub_admin_cannot_access_admin_feedback(self):
        # Sub-admins should get 403 Forbidden
        self.client.force_authenticate(user=self.sub_admin)
        response = self.client.get(reverse("feedback-admin-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(reverse("feedback-admin-stats"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_access_admin_feedback(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(reverse("feedback-admin-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_manage_feedback(self):
        feedback = PlatformFeedback.objects.create(
            user=self.regular_user,
            rating=4,
            ease_of_use=4,
            usefulness=5,
            smoothness=4,
            category="usability",
            comments="Great platform, clean design",
        )

        self.client.force_authenticate(user=self.super_admin)

        # 1. List
        list_res = self.client.get(reverse("feedback-admin-list"))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(list_res.data["count"], 1)

        # 2. Stats
        stats_res = self.client.get(reverse("feedback-admin-stats"))
        self.assertEqual(stats_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stats_res.data["data"]["total_feedback"], 1)
        self.assertEqual(stats_res.data["data"]["avg_rating"], 4.0)

        # 3. Toggle Like
        like_res = self.client.post(reverse("feedback-admin-toggle-like", kwargs={"pk": feedback.id}))
        self.assertEqual(like_res.status_code, status.HTTP_200_OK)
        self.assertTrue(like_res.data["is_liked"])
        feedback.refresh_from_db()
        self.assertTrue(feedback.is_liked)

        # 4. Status update
        status_res = self.client.patch(
            reverse("feedback-admin-status", kwargs={"pk": feedback.id}),
            {"status": "resolved"},
            format="json",
        )
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        feedback.refresh_from_db()
        self.assertEqual(feedback.status, "resolved")

        # 5. Reply
        reply_res = self.client.post(
            reverse("feedback-admin-reply", kwargs={"pk": feedback.id}),
            {"reply": "Thank you for the kind words!", "status": "reviewed"},
            format="json",
        )
        self.assertEqual(reply_res.status_code, status.HTTP_200_OK)
        feedback.refresh_from_db()
        self.assertEqual(feedback.admin_reply, "Thank you for the kind words!")
        self.assertEqual(feedback.replied_by, self.super_admin)

        # Check user got a reply notification
        user_notifs = Notification.objects.filter(user=self.regular_user)
        self.assertTrue(user_notifs.exists())
        self.assertIn("INDULJ Team Replied", user_notifs.first().title)

        # 6. Delete
        del_res = self.client.delete(reverse("feedback-admin-detail", kwargs={"pk": feedback.id}))
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertEqual(PlatformFeedback.objects.count(), 0)
