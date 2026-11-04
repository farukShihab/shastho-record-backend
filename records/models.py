import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def record_image_path(instance, filename):
    """Store as records/<patient_id>/<random uuid>.<ext>.
    We never trust the uploaded filename: it can contain path tricks or personal info."""
    ext = Path(filename).suffix.lower()
    return f"records/{instance.patient_id}/{uuid.uuid4().hex}{ext}"


class AccessGrant(models.Model):
    """A patient letting one doctor see their records. Revoking keeps the row
    (sets revoked_at) so there's an audit trail instead of silently deleting history."""

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="access_grants_given", limit_choices_to={"role": "patient"},
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="access_grants_received", limit_choices_to={"role": "doctor"},
    )
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # At most ONE active (non-revoked) grant per patient/doctor pair.
            models.UniqueConstraint(
                fields=["patient", "doctor"],
                condition=Q(revoked_at__isnull=True),
                name="unique_active_grant",
            )
        ]

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        state = "active" if self.is_active else "revoked"
        return f"{self.patient} -> {self.doctor} ({state})"


class MedicalRecord(models.Model):
    class DocType(models.TextChoices):
        PRESCRIPTION = "prescription", "Prescription"
        LAB_REPORT = "lab_report", "Lab report"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        VERIFIED = "verified", "Verified"

    # Set by the server from request.user (never from the request body)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="records"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verified_records",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNVERIFIED)

    # Patient-supplied: image + a choice from a fixed list. No free text.
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    image = models.ImageField(upload_to=record_image_path)

    # Doctor-only structured fields
    diagnosis = models.TextField(blank=True, null=True)
    medications = models.TextField(blank=True, null=True)
    visit_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["patient", "-created_at"])]

    def __str__(self):
        return f"{self.get_doc_type_display()} for {self.patient} ({self.status})"