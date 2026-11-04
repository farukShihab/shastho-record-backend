from rest_framework.permissions import BasePermission

from .models import AccessGrant, MedicalRecord


class IsPatient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_patient)


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_doctor)


class IsPatientOrDoctor(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_patient or u.is_doctor))


def granted_patient_ids(doctor):
    """IDs of patients with an ACTIVE (non-revoked) grant to this doctor.
    Returned as a lazy queryset, so it becomes a SQL subquery, not a Python list."""
    return AccessGrant.objects.filter(
        doctor=doctor, revoked_at__isnull=True
    ).values("patient_id")


def visible_records(user):
    """The single source of truth for 'which records can this user see?'."""
    qs = MedicalRecord.objects.select_related("patient", "uploaded_by", "verified_by")
    if user.is_patient:
        return qs.filter(patient=user)
    if user.is_doctor:
        return qs.filter(patient_id__in=granted_patient_ids(user))
    return qs.none()