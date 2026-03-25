from django.test import TestCase

# Create your tests here.
"""
tests.py — Sensore Application

Full test suite covering all 10 categories from the created testing log.

Run all tests:
    python manage.py test sensore

Run a single category:
    python manage.py test sensore.tests.TC01_Authentication
    python manage.py test sensore.tests.TC02_AdminUserManagement
    ...

Run a single test:
    python manage.py test sensore.tests.TC01_Authentication.test_valid_patient_login
"""

import io
import csv
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import (
    User, PatientProfile, Session,
    PressureFrame, Alert, Comment, Report,
)
from .utils import generate_alert_if_needed


#  SHARED HELPER — builds all test fixtures

class BaseTestCase(TestCase):
    """
    Creates the standard set of users, profiles, sessions and frames
    used across all test categories. Every TestCase that needs data
    should inherit from this instead of TestCase directly.
    """

    def setUp(self):
        self.client = Client()

        # ── Users ──
        self.admin = User.objects.create_user(
            email='admin@test.com', password='test1234', role=User.ADMIN,
            username='Admin', is_staff=True, is_superuser=True,
        )
        self.clinician = User.objects.create_user(
            email='clinician@test.com', password='test1234', role=User.CLINICIAN,
            username='Dr Test',
        )
        self.clinician2 = User.objects.create_user(
            email='clinician2@test.com', password='test1234', role=User.CLINICIAN,
            username='Dr Other',
        )
        self.patient_user = User.objects.create_user(
            email='patient@test.com', password='test1234', role=User.PATIENT,
            username='Samuel',
        )
        self.patient_user2 = User.objects.create_user(
            email='patient2@test.com', password='test1234', role=User.PATIENT,
            username='Amina',
        )

        # Patient profiles
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            full_name='Samuel Odhiambo',
            assigned_clinician=self.clinician,
        )
        self.patient2 = PatientProfile.objects.create(
            user=self.patient_user2,
            full_name='Amina Kamau',
            assigned_clinician=self.clinician2,
        )

        # Sessions
        self.session = Session.objects.create(
            patient=self.patient,
            session_start=timezone.now(),
            device_id='MAT-001',
        )
        self.session2 = Session.objects.create(
            patient=self.patient2,
            session_start=timezone.now(),
            device_id='MAT-002',
        )

        # Pressure frames
        self.low_frame = self._make_frame(self.session, ppi=500.0, ca=30.0)
        self.med_frame = self._make_frame(self.session, ppi=2000.0, ca=55.0)
        self.high_frame = self._make_frame(self.session, ppi=3500.0, ca=70.0)
        self.other_frame = self._make_frame(self.session2, ppi=1000.0, ca=40.0)

        # Alerts
        self.med_alert = Alert.objects.create(
            frame=self.med_frame, patient=self.patient,
            severity=Alert.MEDIUM,
            message='Elevated pressure detected.',
        )
        self.high_alert = Alert.objects.create(
            frame=self.high_frame, patient=self.patient,
            severity=Alert.HIGH,
            message='Critical pressure detected.',
        )

    def _make_frame(self, session, ppi=500.0, ca=30.0):
        """Create a PressureFrame with preset metric values and dummy CSV."""
        rows = [[100] * 32 for _ in range(32)]
        csv_text = '\n'.join(','.join(map(str, row)) for row in rows)
        frame = PressureFrame.objects.create(
            session=session,
            recorded_at=timezone.now(),
            csv_data=csv_text,
            peak_pressure_index=ppi,
            contact_area_pct=ca,
        )
        return frame

    def _make_csv(self, num_frames=1, base_val=500):
        """
        Build a valid in-memory CSV with num_frames × 32 rows.
        Returns a BytesIO object suitable for file upload.
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        for _ in range(num_frames):
            for _ in range(32):
                writer.writerow([base_val] * 32)
        buf.seek(0)
        return io.BytesIO(buf.read().encode())

    def login_as(self, user):
        self.client.logout()
        self.client.login(username=user.email, password='test1234')


#  TC-01: AUTHENTICATION

class TC01_Authentication(BaseTestCase):

    def test_valid_patient_login(self):
        """TC-1.1: Patient logs in and is redirected to patient dashboard."""
        res = self.client.post(reverse('login'), {
            'email': 'patient@test.com', 'password': 'test1234'
        })
        self.assertRedirects(res, reverse('patient_dashboard'))

    def test_valid_clinician_login(self):
        """TC-1.2: Clinician logs in and is redirected to clinician dashboard."""
        res = self.client.post(reverse('login'), {
            'email': 'clinician@test.com', 'password': 'test1234'
        })
        self.assertRedirects(res, reverse('clinician_dashboard'))

    def test_valid_admin_login(self):
        """TC-1.3: Admin logs in and is redirected to admin dashboard."""
        res = self.client.post(reverse('login'), {
            'email': 'admin@test.com', 'password': 'test1234'
        })
        self.assertRedirects(res, reverse('admin_dashboard'))

    def test_invalid_password(self):
        """TC-1.4: Wrong password stays on login page with error."""
        res = self.client.post(reverse('login'), {
            'email': 'patient@test.com', 'password': 'wrongpassword'
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Invalid email or password')

    def test_logout(self):
        """TC-1.6: Logout redirects to login page."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('logout'))
        self.assertRedirects(res, reverse('login'))

    def test_patient_cannot_access_clinician_dashboard(self):
        """TC-1.7: Patient hitting clinician URL gets 403."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('clinician_dashboard'))
        self.assertEqual(res.status_code, 403)

    def test_patient_cannot_access_admin_panel(self):
        """TC-1.8: Patient hitting admin URL gets 403."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_redirect_to_login(self):
        """TC-1.9: Unauthenticated access to protected page redirects to login."""
        res = self.client.get(reverse('patient_dashboard'))
        self.assertRedirects(res, f"{reverse('login')}?next={reverse('patient_dashboard')}")

    def test_deactivated_user_cannot_login(self):
        """TC-1.10: Deactivated user cannot log in."""
        self.patient_user.is_active = False
        self.patient_user.save()
        res = self.client.post(reverse('login'), {
            'email': 'patient@test.com', 'password': 'test1234'
        })
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_clinician_cannot_access_patient_dashboard(self):
        """TC-1.7 variant: Clinician hitting patient URL gets 403."""
        self.login_as(self.clinician)
        res = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(res.status_code, 403)


#  TC-02: ADMIN USER MANAGEMENT

class TC02_AdminUserManagement(BaseTestCase):

    def test_create_clinician(self):
        """TC-2.1: Admin creates a clinician account."""
        self.login_as(self.admin)
        res = self.client.post(reverse('admin_create_user'), {
            'email': 'newclinician@test.com',
            'username': 'New Clinician',
            'password': 'pass1234',
            'role': 'clinician',
        })
        self.assertTrue(User.objects.filter(email='newclinician@test.com', role='clinician').exists())

    def test_create_patient_with_profile(self):
        """TC-2.2: Admin creates a patient — PatientProfile auto-created."""
        self.login_as(self.admin)
        self.client.post(reverse('admin_create_user'), {
            'email': 'newpatient@test.com',
            'username': 'New Patient',
            'password': 'pass1234',
            'role': 'patient',
            'full_name': 'New Patient Full',
            'clinician_id': self.clinician.id,
        })
        user = User.objects.get(email='newpatient@test.com')
        self.assertTrue(PatientProfile.objects.filter(user=user).exists())
        profile = PatientProfile.objects.get(user=user)
        self.assertEqual(profile.assigned_clinician, self.clinician)

    def test_duplicate_email_rejected(self):
        """TC-2.4: Creating a user with an existing email shows an error."""
        self.login_as(self.admin)
        res = self.client.post(reverse('admin_create_user'), {
            'email': 'patient@test.com',  # already exists
            'username': 'Duplicate',
            'password': 'pass1234',
            'role': 'patient',
        }, follow=True)
        self.assertContains(res, 'already exists')

    def test_edit_user_role(self):
        """TC-2.5: Admin can change a user's role."""
        self.login_as(self.admin)
        self.client.post(reverse('admin_edit_user', args=[self.clinician.id]), {
            'username': self.clinician.username,
            'role': 'admin',
            'is_active': 'on',
        })
        self.clinician.refresh_from_db()
        self.assertEqual(self.clinician.role, 'admin')

    def test_deactivate_user(self):
        """TC-2.7: Admin deactivates a user."""
        self.login_as(self.admin)
        res = self.client.post(reverse('admin_deactivate_user', args=[self.patient_user.id]))
        self.assertEqual(res.status_code, 200)
        self.patient_user.refresh_from_db()
        self.assertFalse(self.patient_user.is_active)

    def test_cannot_deactivate_self(self):
        """TC-2.9: Admin cannot deactivate their own account."""
        self.login_as(self.admin)
        res = self.client.post(reverse('admin_deactivate_user', args=[self.admin.id]))
        data = json.loads(res.content)
        self.assertIn('error', data)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_filter_users_by_role(self):
        """TC-2.8: User list filtered by role returns correct users."""
        self.login_as(self.admin)
        res = self.client.get(reverse('admin_user_list') + '?role=clinician')
        self.assertEqual(res.status_code, 200)
        for user in res.context['page_obj']:
            self.assertEqual(user.role, 'clinician')


#  TC-03: SESSION MANAGEMENT

class TC03_SessionManagement(BaseTestCase):

    def test_patient_sees_own_sessions(self):
        """TC-3.1: Patient's session list shows their sessions."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_session_list'))
        self.assertEqual(res.status_code, 200)
        sessions = list(res.context['page_obj'])
        self.assertIn(self.session, sessions)

    def test_patient_cannot_see_other_session(self):
        """TC-3.2: Patient cannot view another patient's session detail."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_session_detail', args=[self.session2.id]))
        self.assertEqual(res.status_code, 404)

    def test_clinician_sees_assigned_patient_sessions(self):
        """TC-3.3: Clinician can see sessions of their assigned patient."""
        self.login_as(self.clinician)
        res = self.client.get(reverse('clinician_patient_sessions', args=[self.patient.id]))
        self.assertEqual(res.status_code, 200)

    def test_clinician_cannot_see_unassigned_patient(self):
        """TC-3.3 security: Clinician cannot access an unassigned patient's sessions."""
        self.login_as(self.clinician)
        res = self.client.get(reverse('clinician_patient_sessions', args=[self.patient2.id]))
        self.assertEqual(res.status_code, 404)

    def test_session_detail_shows_frames(self):
        """TC-3.4: Session detail page shows correct frame count."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_session_detail', args=[self.session.id]))
        self.assertEqual(res.status_code, 200)
        frames = res.context['frames']
        self.assertEqual(frames.count(), 3)  # low, med, high frames


#  TC-04: CSV UPLOAD & DATA PROCESSING

class TC04_CSVUpload(BaseTestCase):

    def test_upload_valid_csv(self):
        """TC-4.1: Uploading a valid 3-frame CSV creates 3 PressureFrame records."""
        self.login_as(self.patient_user)
        initial_count = PressureFrame.objects.filter(session=self.session).count()
        csv_file = self._make_csv(num_frames=3, base_val=500)
        res = self.client.post(
            reverse('upload_csv', args=[self.session.id]),
            {'csv_file': ('test.csv', csv_file, 'text/csv')},
            format='multipart',
        )
        new_count = PressureFrame.objects.filter(session=self.session).count()
        self.assertEqual(new_count, initial_count + 3)

    def test_upload_no_file_shows_error(self):
        """TC-4.2: Upload with no file shows an error message."""
        self.login_as(self.patient_user)
        res = self.client.post(
            reverse('upload_csv', args=[self.session.id]),
            {},
            follow=True,
        )
        messages = list(res.context['messages'])
        self.assertTrue(any('No file' in str(m) for m in messages))

    def test_ppi_computed_on_upload(self):
        """TC-4.3: PPI is calculated and saved on each new frame."""
        self.login_as(self.patient_user)
        csv_file = self._make_csv(num_frames=1, base_val=500)
        self.client.post(
            reverse('upload_csv', args=[self.session.id]),
            {'csv_file': ('test.csv', csv_file, 'text/csv')},
            format='multipart',
        )
        latest = PressureFrame.objects.filter(session=self.session).order_by('-recorded_at').first()
        self.assertIsNotNone(latest.peak_pressure_index)

    def test_contact_area_computed_on_upload(self):
        """TC-4.4: Contact area % is calculated and saved on each new frame."""
        self.login_as(self.patient_user)
        csv_file = self._make_csv(num_frames=1, base_val=500)
        self.client.post(
            reverse('upload_csv', args=[self.session.id]),
            {'csv_file': ('test.csv', csv_file, 'text/csv')},
            format='multipart',
        )
        latest = PressureFrame.objects.filter(session=self.session).order_by('-recorded_at').first()
        self.assertIsNotNone(latest.contact_area_pct)

    def test_frames_ordered_by_time(self):
        """TC-4.8: Frames in a session are ordered by recorded_at ascending."""
        frames = list(
            PressureFrame.objects.filter(session=self.session).order_by('recorded_at')
        )
        times = [f.recorded_at for f in frames]
        self.assertEqual(times, sorted(times))


#  TC-05: ALERTS

class TC05_Alerts(BaseTestCase):

    def test_high_alert_created_for_high_ppi(self):
        """TC-5.1: Frame with PPI >= 3000 triggers a HIGH alert."""
        frame = self._make_frame(self.session, ppi=3500.0, ca=60.0)
        initial = Alert.objects.filter(patient=self.patient, severity=Alert.HIGH).count()
        generate_alert_if_needed(frame, self.patient)
        final = Alert.objects.filter(patient=self.patient, severity=Alert.HIGH).count()
        self.assertEqual(final, initial + 1)

    def test_medium_alert_created_for_medium_ppi(self):
        """TC-5.2: Frame with PPI >= 1800 triggers a MEDIUM alert."""
        frame = self._make_frame(self.session, ppi=2000.0, ca=50.0)
        initial = Alert.objects.filter(patient=self.patient, severity=Alert.MEDIUM).count()
        generate_alert_if_needed(frame, self.patient)
        final = Alert.objects.filter(patient=self.patient, severity=Alert.MEDIUM).count()
        self.assertEqual(final, initial + 1)

    def test_no_alert_for_low_ppi(self):
        """TC-5.3: Frame with PPI < 1800 creates no alert."""
        frame = self._make_frame(self.session, ppi=500.0, ca=20.0)
        initial = Alert.objects.filter(patient=self.patient).count()
        generate_alert_if_needed(frame, self.patient)
        final = Alert.objects.filter(patient=self.patient).count()
        self.assertEqual(final, initial)

    def test_patient_sees_only_own_alerts(self):
        """TC-5.4: Patient alert list shows only their own alerts."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('alert_list'))
        self.assertEqual(res.status_code, 200)
        for alert in res.context['page_obj']:
            self.assertEqual(alert.patient, self.patient)

    def test_acknowledge_alert(self):
        """TC-5.6: Clinician can acknowledge an alert via API."""
        self.login_as(self.clinician)
        res = self.client.post(
            reverse('api_acknowledge_alert', args=[self.high_alert.id]),
            HTTP_X_CSRFTOKEN='test',
        )
        self.assertEqual(res.status_code, 200)
        self.high_alert.refresh_from_db()
        self.assertTrue(self.high_alert.acknowledged)
        self.assertEqual(self.high_alert.acknowledged_by, self.clinician)

    def test_patient_cannot_acknowledge_other_patient_alert(self):
        """TC-10.5: Patient A cannot acknowledge Patient B's alert."""
        other_alert = Alert.objects.create(
            frame=self.other_frame, patient=self.patient2,
            severity=Alert.MEDIUM, message='Test',
        )
        self.login_as(self.patient_user)
        res = self.client.post(reverse('api_acknowledge_alert', args=[other_alert.id]))
        self.assertEqual(res.status_code, 403)

    def test_admin_sees_all_alerts(self):
        """TC-5.9: Admin alert list shows alerts from all patients."""
        self.login_as(self.admin)
        res = self.client.get(reverse('alert_list'))
        self.assertEqual(res.status_code, 200)
        patient_ids = {a.patient.id for a in res.context['page_obj']}
        self.assertIn(self.patient.id, patient_ids)


#  TC-06: HEATMAP & FRAME DETAIL

class TC06_HeatmapFrameDetail(BaseTestCase):

    def test_frame_detail_loads_for_patient(self):
        """TC-6.1: Frame detail page loads for the owning patient."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('frame_detail', args=[self.low_frame.id]))
        self.assertEqual(res.status_code, 200)

    def test_frame_detail_loads_for_clinician(self):
        """TC-6.1: Frame detail page loads for the assigned clinician."""
        self.login_as(self.clinician)
        res = self.client.get(reverse('frame_detail', args=[self.low_frame.id]))
        self.assertEqual(res.status_code, 200)

    def test_patient_cannot_view_other_patient_frame(self):
        """TC-10.1: Patient A cannot view Patient B's frame."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('frame_detail', args=[self.other_frame.id]))
        self.assertEqual(res.status_code, 403)

    def test_heatmap_api_returns_matrix(self):
        """TC-6.1: Heatmap API returns a 32x32 matrix."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('api_frame_heatmap', args=[self.low_frame.id]))
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('matrix', data)
        self.assertEqual(len(data['matrix']), 32)
        self.assertEqual(len(data['matrix'][0]), 32)

    def test_heatmap_api_forbidden_for_other_patient(self):
        """TC-10.1: Heatmap API returns 403 for wrong patient."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('api_frame_heatmap', args=[self.other_frame.id]))
        self.assertEqual(res.status_code, 403)

    def test_resolve_frame(self):
        """TC-6.5: Clinician can resolve a flagged frame."""
        self.high_frame.flagged_for_review = True
        self.high_frame.save()
        self.login_as(self.clinician)
        res = self.client.post(reverse('api_resolve_frame', args=[self.high_frame.id]))
        self.assertEqual(res.status_code, 200)
        self.high_frame.refresh_from_db()
        self.assertFalse(self.high_frame.flagged_for_review)

    def test_patient_cannot_resolve_frame(self):
        """TC-6.6: Patient cannot resolve a frame — 403."""
        self.high_frame.flagged_for_review = True
        self.high_frame.save()
        self.login_as(self.patient_user)
        res = self.client.post(reverse('api_resolve_frame', args=[self.high_frame.id]))
        self.assertEqual(res.status_code, 403)

    def test_clinician_cannot_resolve_unassigned_frame(self):
        """TC-10.6: Clinician cannot resolve a frame from an unassigned patient."""
        self.login_as(self.clinician)
        res = self.client.post(reverse('api_resolve_frame', args=[self.other_frame.id]))
        self.assertEqual(res.status_code, 403)


#  TC-07: COMMENTS & THREADING

class TC07_Comments(BaseTestCase):

    def test_patient_can_add_comment(self):
        """TC-7.1: Patient can post a comment on their frame."""
        self.login_as(self.patient_user)
        res = self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': 'Feeling discomfort.', 'parent_id': None}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(Comment.objects.filter(frame=self.low_frame, author=self.patient_user).exists())

    def test_comment_linked_to_correct_frame(self):
        """TC-7.2: Comment is only linked to the frame it was posted on."""
        self.login_as(self.patient_user)
        self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': 'Frame 1 comment.', 'parent_id': None}),
            content_type='application/json',
        )
        self.assertFalse(Comment.objects.filter(frame=self.med_frame).exists())

    def test_patient_comment_flags_frame(self):
        """TC-7.3: Posting a comment as patient flags the frame for review."""
        self.login_as(self.patient_user)
        self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': 'Pain here.', 'parent_id': None}),
            content_type='application/json',
        )
        self.low_frame.refresh_from_db()
        self.assertTrue(self.low_frame.flagged_for_review)

    def test_clinician_can_reply(self):
        """TC-7.5: Clinician can reply to a patient comment (threaded)."""
        # Patient posts first
        self.login_as(self.patient_user)
        res = self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': 'Discomfort.', 'parent_id': None}),
            content_type='application/json',
        )
        parent_id = json.loads(res.content)['id']

        # Clinician replies
        self.login_as(self.clinician)
        res = self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': 'Noted, reposition.', 'parent_id': parent_id}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        reply = Comment.objects.get(id=json.loads(res.content)['id'])
        self.assertEqual(reply.parent_id, parent_id)

    def test_empty_comment_rejected(self):
        """TC-7.6: Empty comment body is rejected with 400."""
        self.login_as(self.patient_user)
        res = self.client.post(
            reverse('api_add_comment', args=[self.low_frame.id]),
            data=json.dumps({'body': '', 'parent_id': None}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)

    def test_patient_cannot_comment_on_other_patient_frame(self):
        """Security: Patient cannot comment on another patient's frame."""
        self.login_as(self.patient_user)
        res = self.client.post(
            reverse('api_add_comment', args=[self.other_frame.id]),
            data=json.dumps({'body': 'Intruder comment.', 'parent_id': None}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 403)


#  TC-08: CHARTS & TIME FILTER

class TC08_ChartsTimeFilter(BaseTestCase):

    def test_patient_dashboard_default_24h(self):
        """TC-8.5: Default patient dashboard uses 24h filter."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['hours'], 24)

    def test_patient_dashboard_1h_filter(self):
        """TC-8.3: Patient dashboard respects ?hours=1."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_dashboard') + '?hours=1')
        self.assertEqual(res.context['hours'], 1)

    def test_patient_dashboard_6h_filter(self):
        """TC-8.4: Patient dashboard respects ?hours=6."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_dashboard') + '?hours=6')
        self.assertEqual(res.context['hours'], 6)

    def test_patient_dashboard_7d_filter(self):
        """TC-8.6: Patient dashboard respects ?hours=168."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_dashboard') + '?hours=168')
        self.assertEqual(res.context['hours'], 168)

    def test_invalid_hours_defaults_to_24(self):
        """TC-8.8 safety: Invalid hours param defaults to 24."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('patient_dashboard') + '?hours=999')
        self.assertEqual(res.context['hours'], 24)

    def test_clinician_time_filter(self):
        """TC-8.3: Clinician patient detail respects ?hours= filter."""
        self.login_as(self.clinician)
        res = self.client.get(
            reverse('clinician_patient_detail', args=[self.patient.id]) + '?hours=6'
        )
        self.assertEqual(res.context['hours'], 6)

    def test_metric_history_api(self):
        """TC-8.1: Metric history API returns data list."""
        self.login_as(self.patient_user)
        res = self.client.get(
            reverse('api_metric_history', args=[self.patient.id]) + '?hours=24'
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_metric_history_forbidden_for_other_patient(self):
        """TC-10.1: Metric history API is forbidden for wrong patient."""
        self.login_as(self.patient_user)
        res = self.client.get(
            reverse('api_metric_history', args=[self.patient2.id])
        )
        self.assertEqual(res.status_code, 403)


#  TC-09: REPORTS

class TC09_Reports(BaseTestCase):

    def _generate_report(self):
        """Helper: clinician generates a report for patient."""
        self.login_as(self.clinician)
        today = timezone.now().date().isoformat()
        return self.client.post(
            reverse('generate_report', args=[self.patient.id]),
            {'period_start': today, 'period_end': today},
            follow=True,
        )

    def test_generate_report_creates_record(self):
        """TC-9.1: Generating a report creates a Report record."""
        initial = Report.objects.count()
        self._generate_report()
        self.assertEqual(Report.objects.count(), initial + 1)

    def test_report_detail_loads(self):
        """TC-9.2: Report detail page loads successfully."""
        self._generate_report()
        report = Report.objects.latest('created_at')
        self.login_as(self.clinician)
        res = self.client.get(reverse('report_detail', args=[report.id]))
        self.assertEqual(res.status_code, 200)

    def test_report_in_list(self):
        """TC-9.5: Generated report appears in report list."""
        self._generate_report()
        res = self.client.get(reverse('report_list'))
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.context['page_obj'].paginator.count, 0)

    def test_patient_sees_own_reports(self):
        """TC-9.6: Patient only sees reports for themselves."""
        self._generate_report()
        self.login_as(self.patient_user)
        res = self.client.get(reverse('report_list'))
        for report in res.context['page_obj']:
            self.assertEqual(report.patient, self.patient)

    def test_patient_cannot_view_other_patient_report(self):
        """Security: Patient cannot view another patient's report."""
        self._generate_report()
        report = Report.objects.latest('created_at')

        # Create a report for patient2
        self.login_as(self.clinician2)
        today = timezone.now().date().isoformat()
        self.client.post(
            reverse('generate_report', args=[self.patient2.id]),
            {'period_start': today, 'period_end': today},
            follow=True,
        )
        report2 = Report.objects.latest('created_at')

        self.login_as(self.patient_user)
        res = self.client.get(reverse('report_detail', args=[report2.id]))
        self.assertEqual(res.status_code, 403)

    def test_missing_dates_redirects_with_error(self):
        """TC-9.1: Submitting report form without dates shows error."""
        self.login_as(self.clinician)
        res = self.client.post(
            reverse('generate_report', args=[self.patient.id]),
            {'period_start': '', 'period_end': ''},
            follow=True,
        )
        messages = list(res.context['messages'])
        self.assertTrue(any('date' in str(m).lower() for m in messages))


#  TC-10: SECURITY

class TC10_Security(BaseTestCase):

    def test_sql_injection_in_login(self):
        """TC-10.4: SQL injection attempt in login does not bypass auth."""
        res = self.client.post(reverse('login'), {
            'email': "' OR 1=1 --",
            'password': 'anything',
        })
        # Should stay on login page, not redirect
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_clinician_cannot_access_unassigned_patient(self):
        """TC-10.2: Clinician gets 404 for patient not assigned to them."""
        self.login_as(self.clinician)
        res = self.client.get(reverse('clinician_patient_detail', args=[self.patient2.id]))
        self.assertEqual(res.status_code, 404)

    def test_patient_cannot_access_other_patient_heatmap(self):
        """TC-10.1: Patient cannot access another patient's heatmap API."""
        self.login_as(self.patient_user)
        res = self.client.get(reverse('api_frame_heatmap', args=[self.other_frame.id]))
        self.assertEqual(res.status_code, 403)

    def test_patient_cannot_resolve_frame(self):
        """TC-10.6: Patient cannot call the resolve frame API."""
        self.login_as(self.patient_user)
        res = self.client.post(reverse('api_resolve_frame', args=[self.high_frame.id]))
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_api_access_redirects(self):
        """TC-1.9: Unauthenticated user hitting an API endpoint is redirected."""
        res = self.client.get(reverse('api_frame_heatmap', args=[self.low_frame.id]))
        self.assertEqual(res.status_code, 302)

    def test_clinician_cannot_resolve_other_patient_frame(self):
        """TC-10.6: Clinician cannot resolve a frame belonging to an unassigned patient."""
        self.login_as(self.clinician)
        res = self.client.post(reverse('api_resolve_frame', args=[self.other_frame.id]))
        self.assertEqual(res.status_code, 403)