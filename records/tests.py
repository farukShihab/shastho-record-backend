import io
import shutil
import tempfile
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import DoctorProfile, PatientProfile, User

from .models import AccessGrant, MedicalRecord

TEMP_MEDIA = tempfile.mkdtemp()   # uploads during tests go here, not into your real media/


def image_bytes(fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (30, 120, 200)).save(buf, fmt)
    return buf.getvalue()


def upload(name="scan.png", fmt="PNG", content_type="image/png"):
    return SimpleUploadedFile(name, image_bytes(fmt), content_type=content_type)


def make_user(username, role):
    user = User.objects.create_user(
        username=username, email=f"{username}@test.example", password="Test-pass-123", role=role)
    if role == "patient":
        PatientProfile.objects.create(user=user)
    else:
        DoctorProfile.objects.create(user=user, specialty="General", clinic_name="Test Clinic")
    return user


def make_record(patient, **fields):
    record = MedicalRecord(patient=patient, uploaded_by=patient, doc_type="prescription", **fields)
    record.image.save("t.png", ContentFile(image_bytes()), save=False)
    record.save()
    return record


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BaseTest(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.patient = make_user("pat", "patient")
        self.other_patient = make_user("pat2", "patient")
        self.doctor = make_user("doc", "doctor")
        self.other_doctor = make_user("doc2", "doctor")

    def login(self, user):
        self.client.force_authenticate(user)

    def grant(self, patient, doctor):
        return AccessGrant.objects.create(patient=patient, doctor=doctor)

    def detail(self, record):
        return reverse("record-detail", args=[record.pk])


class PatientRuleTests(BaseTest):
    def test_patient_cannot_patch(self):
        record = make_record(self.patient)
        self.login(self.patient)
        resp = self.client.patch(self.detail(record), {"diagnosis": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        record.refresh_from_db()
        self.assertIsNone(record.diagnosis)

    def test_patient_cannot_put_or_delete(self):
        record = make_record(self.patient)
        self.login(self.patient)
        self.assertEqual(self.client.put(self.detail(record), {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.detail(record)).status_code, 405)

    def test_patient_text_and_server_fields_are_ignored_on_upload(self):
        self.login(self.patient)
        resp = self.client.post(reverse("record-list"), {
            "doc_type": "prescription", "image": upload(),
            "diagnosis": "hacked", "notes": "hacked", "status": "verified",
            "verified_by": self.doctor.pk, "patient": self.other_patient.pk,
        }, format="multipart")
        self.assertEqual(resp.status_code, 201)
        record = MedicalRecord.objects.get(pk=resp.data["id"])
        self.assertIsNone(record.diagnosis)
        self.assertIsNone(record.notes)
        self.assertEqual(record.status, "unverified")
        self.assertIsNone(record.verified_by)
        self.assertEqual(record.patient, self.patient)        # from request.user, not the body
        self.assertEqual(record.uploaded_by, self.patient)

    def test_doc_type_must_be_in_fixed_list(self):
        self.login(self.patient)
        resp = self.client.post(reverse("record-list"),
                                {"doc_type": "anything", "image": upload()}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_patient_sees_only_own_records(self):
        mine = make_record(self.patient)
        theirs = make_record(self.other_patient)
        self.login(self.patient)
        ids = [r["id"] for r in self.client.get(reverse("record-list")).data]
        self.assertEqual(ids, [mine.id])
        self.assertEqual(self.client.get(self.detail(theirs)).status_code, 404)

    def test_doctor_cannot_upload(self):
        self.login(self.doctor)
        resp = self.client.post(reverse("record-list"),
                                {"doc_type": "other", "image": upload()}, format="multipart")
        self.assertEqual(resp.status_code, 403)


class ImageValidationTests(BaseTest):
    def post_image(self, file):
        self.login(self.patient)
        return self.client.post(reverse("record-list"),
                                {"doc_type": "other", "image": file}, format="multipart")

    def test_fake_image_rejected(self):
        fake = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.post_image(fake).status_code, 400)

    def test_disallowed_format_rejected(self):
        gif = upload("a.gif", "GIF", "image/gif")
        self.assertEqual(self.post_image(gif).status_code, 400)

    def test_oversize_rejected(self):
        with patch("records.validators.MAX_IMAGE_BYTES", 10):   # any real image is bigger than 10 bytes
            self.assertEqual(self.post_image(upload()).status_code, 400)

    def test_valid_png_accepted(self):
        self.assertEqual(self.post_image(upload()).status_code, 201)


class DoctorAccessTests(BaseTest):
    def test_doctor_can_patch_with_access_and_it_verifies(self):
        record = make_record(self.patient)
        self.grant(self.patient, self.doctor)
        self.login(self.doctor)
        resp = self.client.patch(self.detail(record), {
            "diagnosis": "Hypertension", "medications": "Amlodipine", "visit_date": "2026-10-20",
            "notes": "ok", "status": "unverified", "verified_by": self.other_doctor.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.diagnosis, "Hypertension")
        self.assertEqual(record.status, "verified")
        self.assertEqual(record.verified_by, self.doctor)     # server decides, not the body

    def test_doctor_cannot_access_ungranted_patient(self):
        record = make_record(self.patient)
        self.login(self.doctor)
        self.assertEqual(self.client.get(self.detail(record)).status_code, 404)
        self.assertEqual(self.client.patch(self.detail(record), {"diagnosis": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(reverse("record-list")).data, [])
        self.assertEqual(self.client.get(reverse("record-image", args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("timeline"), {"patient": self.patient.pk}).status_code, 403)

    def test_grant_for_one_patient_does_not_open_another(self):
        self.grant(self.patient, self.doctor)
        other = make_record(self.other_patient)
        self.login(self.doctor)
        self.assertEqual(self.client.get(self.detail(other)).status_code, 404)

    def test_revoked_access_is_blocked(self):
        record = make_record(self.patient)
        grant = self.grant(self.patient, self.doctor)
        self.login(self.doctor)
        self.assertEqual(self.client.get(self.detail(record)).status_code, 200)

        self.login(self.patient)
        self.assertEqual(self.client.post(reverse("access-revoke", args=[grant.pk])).status_code, 200)

        self.login(self.doctor)
        self.assertEqual(self.client.get(self.detail(record)).status_code, 404)
        self.assertEqual(self.client.patch(self.detail(record), {"diagnosis": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(reverse("record-image", args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("timeline"), {"patient": self.patient.pk}).status_code, 403)

    def test_patient_list_for_doctor_only_shows_granted(self):
        self.grant(self.patient, self.doctor)
        self.login(self.doctor)
        ids = [p["id"] for p in self.client.get(reverse("patient-list")).data]
        self.assertEqual(ids, [self.patient.id])
        self.login(self.patient)
        self.assertEqual(self.client.get(reverse("patient-list")).status_code, 403)


class ImageEndpointTests(BaseTest):
    def test_requires_login(self):
        record = make_record(self.patient)
        self.assertEqual(self.client.get(reverse("record-image", args=[record.pk])).status_code, 401)

    def test_owner_and_granted_doctor_can_download(self):
        record = make_record(self.patient)
        self.grant(self.patient, self.doctor)
        for user in (self.patient, self.doctor):
            self.login(user)
            resp = self.client.get(reverse("record-image", args=[record.pk]))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp["Content-Type"], "image/png")
            b"".join(resp.streaming_content)   # read the stream so the file handle is closed

    def test_other_patient_cannot_download(self):
        record = make_record(self.patient)
        self.login(self.other_patient)
        self.assertEqual(self.client.get(reverse("record-image", args=[record.pk])).status_code, 404)


class AccessGrantTests(BaseTest):
    def test_patient_grants_and_duplicate_is_rejected(self):
        self.login(self.patient)
        url = reverse("access-list")
        self.assertEqual(self.client.post(url, {"doctor": self.doctor.pk}, format="json").status_code, 201)
        self.assertEqual(self.client.post(url, {"doctor": self.doctor.pk}, format="json").status_code, 400)

    def test_can_regrant_after_revoke(self):
        grant = self.grant(self.patient, self.doctor)
        self.login(self.patient)
        self.client.post(reverse("access-revoke", args=[grant.pk]))
        resp = self.client.post(reverse("access-list"), {"doctor": self.doctor.pk}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(AccessGrant.objects.filter(patient=self.patient, doctor=self.doctor).count(), 2)

    def test_cannot_grant_a_non_doctor(self):
        self.login(self.patient)
        resp = self.client.post(reverse("access-list"), {"doctor": self.other_patient.pk}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_revoke_someone_elses_grant(self):
        grant = self.grant(self.other_patient, self.doctor)
        self.login(self.patient)
        self.assertEqual(self.client.post(reverse("access-revoke", args=[grant.pk])).status_code, 404)
        grant.refresh_from_db()
        self.assertIsNone(grant.revoked_at)

    def test_doctor_cannot_use_patient_only_endpoints(self):
        self.login(self.doctor)
        self.assertEqual(self.client.get(reverse("access-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("doctor-list")).status_code, 403)
        resp = self.client.post(reverse("access-list"), {"doctor": self.other_doctor.pk}, format="json")
        self.assertEqual(resp.status_code, 403)


class TimelineTests(BaseTest):
    def test_sorted_by_visit_date_falling_back_to_created_at(self):
        r1 = make_record(self.patient, visit_date=date(2026, 1, 10))
        r2 = make_record(self.patient)   # no visit_date: uses created_at
        MedicalRecord.objects.filter(pk=r2.pk).update(
            created_at=datetime(2026, 2, 1, 12, 0, tzinfo=dt_timezone.utc))
        r3 = make_record(self.patient, visit_date=date(2026, 3, 1))
        self.login(self.patient)
        resp = self.client.get(reverse("timeline"))
        self.assertEqual([i["id"] for i in resp.data["results"]], [r3.id, r2.id, r1.id])
        resp = self.client.get(reverse("timeline"), {"order": "asc"})
        self.assertEqual([i["id"] for i in resp.data["results"]], [r1.id, r2.id, r3.id])

    def test_items_include_status_and_verifier(self):
        record = make_record(self.patient, status="verified", verified_by=self.doctor)
        self.login(self.patient)
        item = self.client.get(reverse("timeline")).data["results"][0]
        self.assertEqual(item["id"], record.id)
        self.assertEqual(item["status"], "verified")
        self.assertEqual(item["verified_by_name"], "doc")
        self.assertEqual(item["verified_by_clinic"], "Test Clinic")

    def test_patient_cannot_view_another_timeline(self):
        make_record(self.other_patient)
        self.login(self.patient)
        resp = self.client.get(reverse("timeline"), {"patient": self.other_patient.pk})
        self.assertEqual(resp.data["patient"]["id"], self.patient.id)
        self.assertEqual(resp.data["count"], 0)

    def test_doctor_needs_patient_param_and_grant(self):
        make_record(self.patient)
        self.grant(self.patient, self.doctor)
        self.login(self.doctor)
        self.assertEqual(self.client.get(reverse("timeline")).status_code, 400)
        resp = self.client.get(reverse("timeline"), {"patient": self.patient.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)


class AuthTests(APITestCase):
    def register(self, **overrides):
        data = {"username": "newuser", "email": "new@test.example",
                "password": "Str0ng!Pass123", "role": "patient"}
        data.update(overrides)
        return self.client.post("/api/auth/register/", data, format="json")

    def test_register_creates_matching_profile(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(PatientProfile.objects.filter(user__username="newuser").exists())
        resp = self.register(username="newdoc", email="d@test.example", role="doctor", specialty="ENT")
        self.assertTrue(DoctorProfile.objects.filter(user__username="newdoc", specialty="ENT").exists())

    def test_cannot_register_as_admin_or_set_staff(self):
        self.assertEqual(self.register(role="admin").status_code, 400)
        resp = self.register(is_staff=True, is_superuser=True)
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_weak_password_and_duplicate_email_rejected(self):
        self.assertEqual(self.register(password="12345").status_code, 400)
        self.register()
        self.assertEqual(self.register(username="other").status_code, 400)   # same email

    def test_me_requires_login(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)