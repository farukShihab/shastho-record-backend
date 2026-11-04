from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AccessGrant

User = get_user_model()


def display_name(user):
    return user.get_full_name() or user.username


class DoctorListSerializer(serializers.ModelSerializer):
    """What a patient sees in the 'pick a doctor' dropdown. No email or other private fields."""
    name = serializers.SerializerMethodField()
    specialty = serializers.CharField(source="doctor_profile.specialty", default="")
    clinic_name = serializers.CharField(source="doctor_profile.clinic_name", default="")

    class Meta:
        model = User
        fields = ("id", "name", "specialty", "clinic_name")

    def get_name(self, user):
        return display_name(user)


class AccessGrantSerializer(serializers.ModelSerializer):
    """READ output for a grant."""
    doctor_name = serializers.SerializerMethodField()
    specialty = serializers.CharField(source="doctor.doctor_profile.specialty", default="")
    clinic_name = serializers.CharField(source="doctor.doctor_profile.clinic_name", default="")
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = AccessGrant
        fields = ("id", "doctor", "doctor_name", "specialty", "clinic_name",
                  "granted_at", "revoked_at", "is_active")
        read_only_fields = fields

    def get_doctor_name(self, grant):
        return display_name(grant.doctor)


class AccessGrantCreateSerializer(serializers.ModelSerializer):
    """WRITE input: the only thing a patient sends is which doctor."""
    doctor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.DOCTOR, is_active=True)
    )

    class Meta:
        model = AccessGrant
        fields = ("doctor",)

    def validate_doctor(self, doctor):
        patient = self.context["request"].user
        if AccessGrant.objects.filter(
            patient=patient, doctor=doctor, revoked_at__isnull=True
        ).exists():
            raise serializers.ValidationError("You have already given this doctor access.")
        return doctor

class PatientListSerializer(serializers.ModelSerializer):
    """What a doctor sees in 'my patients': only people who granted access."""
    name = serializers.SerializerMethodField()
    patient_code = serializers.CharField(source="patient_profile.patient_code", default=None)

    class Meta:
        model = User
        fields = ("id", "name", "patient_code")

    def get_name(self, user):
        return display_name(user)