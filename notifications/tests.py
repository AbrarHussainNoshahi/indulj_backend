from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from notifications.models import Notification
from notifications.utils import create_notification, notify_admins

User = get_user_model()

class NotificationAPITests(APITestCase):
    def setUp(self):
        # Create test users
        self.user = User.objects.create_user(
            email="user@example.com",
            password="password123",
            full_name="Regular User",
            role="user"
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            full_name="Admin User",
            role="admin"
        )
        
        # Create some notifications
        self.notif1 = create_notification(
            user=self.user,
            type="system",
            title="System Alert",
            message="Welcome to the platform!"
        )
        self.notif2 = create_notification(
            user=self.user,
            type="deal",
            title="New Deal",
            message="Check out this new deal!"
        )
        
    def test_notification_model_properties(self):
        self.assertEqual(self.notif1.status, "unread")
        self.notif1.mark_read()
        self.assertEqual(self.notif1.status, "read")
        self.assertTrue(self.notif1.is_read)
        self.assertIsNotNone(self.notif1.read_at)

    def test_get_notifications_unauthenticated(self):
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_notifications_list(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['unread_count'], 2)
        
    def test_get_notifications_list_filtering(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-list')
        
        # Filter by type
        response = self.client.get(url, {'type': 'system'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['data'][0]['type'], 'system')
        
        # Filter by unread
        response = self.client.get(url, {'unread': 'true'})
        self.assertEqual(response.data['count'], 2)
        
        # Mark one read
        self.notif1.mark_read()
        response = self.client.get(url, {'unread': 'true'})
        self.assertEqual(response.data['count'], 1)

    def test_get_unread_count(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-unread-count')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 2)

    def test_mark_read(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-read', kwargs={'pk': self.notif1.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['is_read'], True)
        
        # Verify db updated
        self.notif1.refresh_from_db()
        self.assertTrue(self.notif1.is_read)

    def test_mark_all_read(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-mark-all-read')
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.notif1.refresh_from_db()
        self.notif2.refresh_from_db()
        self.assertTrue(self.notif1.is_read)
        self.assertTrue(self.notif2.is_read)

    def test_delete_notification(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-delete', kwargs={'pk': self.notif1.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.filter(id=self.notif1.id).exists())

    def test_clear_all(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('notification-clear-all')
        
        # Test clear only read (currently 0 read)
        response = self.client.delete(f"{url}?only_read=true")
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)
        
        # Mark one read, try again
        self.notif1.mark_read()
        response = self.client.delete(f"{url}?only_read=true")
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Notification.objects.filter(id=self.notif1.id).exists())
        
        # Clear all remaining
        response = self.client.delete(url)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_notify_admins(self):
        notify_admins(
            type="system",
            title="System Maintenance",
            message="Maintenance tonight."
        )
        # Regular user should not get it, only admins
        self.assertEqual(Notification.objects.filter(user=self.user, title="System Maintenance").count(), 0)
        self.assertEqual(Notification.objects.filter(user=self.admin, title="System Maintenance").count(), 1)
