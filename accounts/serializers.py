from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import DoctorProfile, PatientProfile, User


class UserSerializer(serializers.ModelSerializer):
    """Read-only view of the current user, with profile info flattened in."""
    patient_code = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    clinic_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name",
                  "role", "patient_code", "specialty", "clinic_name")
        read_only_fields = fields

    def get_patient_code(self, user):
        return user.patient_profile.patient_code if hasattr(user, "patient_profile") else None

    def get_specialty(self, user):
        return user.doctor_profile.specialty if hasattr(user, "doctor_profile") else None

    def get_clinic_name(self, user):
        return user.doctor_profile.clinic_name if hasattr(user, "doctor_profile") else None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    # ChoiceField limited to patient/doctor, so nobody can register as anything else.
    role = serializers.ChoiceField(choices=User.Role.choices)
    # Doctor-only extras; ignored for patients.
    specialty = serializers.CharField(required=False, allow_blank=True, write_only=True)
    clinic_name = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "first_name", "last_name",
                  "role", "specialty", "clinic_name")
        extra_kwargs = {"email": {"required": True}}

    @transaction.atomic
    def create(self, validated_data):
        specialty = validated_data.pop("specialty", "")
        clinic_name = validated_data.pop("clinic_name", "")
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)   # hashes the password; never store it raw
        user.save()

        if user.role == User.Role.PATIENT:
            PatientProfile.objects.create(user=user)
        else:
            DoctorProfile.objects.create(user=user, specialty=specialty, clinic_name=clinic_name)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Standard simplejwt login, plus the user object in the response
    so the frontend knows the role immediately."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data