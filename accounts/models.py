from django.contrib.auth.models import AbstractUser
from django.db import models

import secrets
import string


class User(AbstractUser):
    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"

    role = models.CharField(max_length=10, choices=Role.choices)

    # Make email unique and required: it's the natural identifier for login.
    email = models.EmailField(unique=True)

    @property
    def is_patient(self):
        return self.role == self.Role.PATIENT

    @property
    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

def generate_patient_code():
    """Human-friendly unique code like SR-7K3QX9AB (no confusing look-alikes needed for a demo)."""
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "SR-" + "".join(secrets.choice(alphabet) for _ in range(8))
        if not PatientProfile.objects.filter(patient_code=code).exists():
            return code


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    patient_code = models.CharField(max_length=12, unique=True, default=generate_patient_code, editable=False)

    def __str__(self):
        return f"{self.patient_code} - {self.user}"


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    specialty = models.CharField(max_length=100, blank=True)
    clinic_name = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username}"

