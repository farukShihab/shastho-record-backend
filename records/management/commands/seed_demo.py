import io
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import DoctorProfile, PatientProfile, User
from records.models import AccessGrant, MedicalRecord

PASSWORD = "DemoPass123!"

DOCTORS = [
    dict(username="dr_anika", first_name="Anika", last_name="Rahman", email="anika@demo.example",
         specialty="Cardiology", clinic_name="Dhaka Heart Clinic"),
    dict(username="dr_karim", first_name="Karim", last_name="Hossain", email="karim@demo.example",
         specialty="Endocrinology", clinic_name="Chattogram Diabetes & Hormone Centre"),
]
PATIENTS = [
    dict(username="rahim", first_name="Rahim", last_name="Uddin", email="rahim@demo.example"),
    dict(username="nusrat", first_name="Nusrat", last_name="Jahan", email="nusrat@demo.example"),
]

# (patient, doc_type, verifier or None, uploaded_days_ago, visit_days_ago, diagnosis, medications, notes)
RECORDS = [
    ("rahim", "prescription", "dr_anika", 80, 83, "Hypertension (stage 1)",
     "Amlodipine 5 mg, once daily", "Monitor BP at home. Review in 4 weeks."),
    ("rahim", "lab_report", "dr_karim", 55, 58, "Vitamin D deficiency",
     "Vitamin D3 2000 IU, once daily", "Repeat the test after 3 months."),
    ("rahim", "prescription", "dr_anika", 25, 27, "Hypertension, follow-up",
     "Continue Amlodipine 5 mg", "BP improved. Reduce salt intake."),
    ("rahim", "lab_report", None, 4, None, None, None, None),
    ("rahim", "other", None, 1, None, None, None, None),
    ("nusrat", "prescription", "dr_karim", 40, 41, "Hypothyroidism",
     "Levothyroxine 50 mcg, mornings on an empty stomach", "Recheck TSH in 6 weeks."),
    ("nusrat", "lab_report", None, 3, None, None, None, None),
]

# patient -> doctors they have granted access to.
# dr_anika sees only Rahim; dr_karim sees both, so you can demo the permission wall.
GRANTS = [("rahim", "dr_anika"), ("rahim", "dr_karim"), ("nusrat", "dr_karim")]


def make_image(title, lines):
    """A simple fake 'scan' so the timeline has something to display."""
    img = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 580, 780], outline=(40, 90, 160), width=4)
    y = 60
    for text in [title, *lines]:
        draw.text((50, y), text, fill=(20, 20, 20))
        y += 40
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Create demo doctors, patients, records and access grants."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete the demo users (and their records/grants) first.")

    @transaction.atomic
    def handle(self, *args, **options):
        usernames = [u["username"] for u in DOCTORS + PATIENTS]
        if options["reset"]:
            User.objects.filter(username__in=usernames).delete()
        if User.objects.filter(username__in=usernames).exists():
            self.stdout.write(self.style.WARNING("Demo users already exist. Run with --reset to rebuild."))
            return

        users = {}
        for data in DOCTORS:
            user = self._make_user(data, User.Role.DOCTOR)
            DoctorProfile.objects.create(user=user, specialty=data["specialty"], clinic_name=data["clinic_name"])
            users[user.username] = user
        for data in PATIENTS:
            user = self._make_user(data, User.Role.PATIENT)
            PatientProfile.objects.create(user=user)
            users[user.username] = user

        for patient, doctor in GRANTS:
            AccessGrant.objects.create(patient=users[patient], doctor=users[doctor])

        now = timezone.now()
        today = timezone.localdate()
        for patient, doc_type, verifier, up_days, visit_days, dx, meds, notes in RECORDS:
            record = MedicalRecord(patient=users[patient], uploaded_by=users[patient], doc_type=doc_type)
            if verifier:
                record.verified_by = users[verifier]
                record.status = MedicalRecord.Status.VERIFIED
                record.visit_date = today - timedelta(days=visit_days)
                record.diagnosis, record.medications, record.notes = dx, meds, notes
            label = dict(MedicalRecord.DocType.choices)[doc_type].upper()
            image = make_image(f"DEMO {label}", [f"Patient: {patient}", "(fake sample image)"])
            record.image.save("seed.jpg", ContentFile(image), save=False)
            record.save()
            # created_at is auto_now_add, so backdate it with an UPDATE.
            MedicalRecord.objects.filter(pk=record.pk).update(created_at=now - timedelta(days=up_days))

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write(f"Password for every demo user: {PASSWORD}")
        self.stdout.write("Doctors: dr_anika, dr_karim | Patients: rahim, nusrat")

    def _make_user(self, data, role):
        user = User(username=data["username"], email=data["email"], role=role,
                    first_name=data["first_name"], last_name=data["last_name"])
        user.set_password(PASSWORD)
        user.save()
        return user