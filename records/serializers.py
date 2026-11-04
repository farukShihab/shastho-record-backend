from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import MedicalRecord
from .validators import check_image


class RecordSerializer(serializers.ModelSerializer):
    """READ-ONLY output for both roles."""
    image_url = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MedicalRecord
        fields = ("id", "patient", "uploaded_by", "uploaded_by_name", "doc_type",
                  "image_url", "created_at", "status", "verified_by", "verified_by_name",
                  "diagnosis", "medications", "visit_date", "notes")
        read_only_fields = fields

    def get_image_url(self, obj):
        return reverse("record-image", args=[obj.pk], request=self.context.get("request"))

    @staticmethod
    def _name(user):
        return (user.get_full_name() or user.username) if user else None

    def get_verified_by_name(self, obj):
        return self._name(obj.verified_by)

    def get_uploaded_by_name(self, obj):
        return self._name(obj.uploaded_by)


class PatientUploadSerializer(serializers.ModelSerializer):
    """What a PATIENT may send: an image and a doc_type. Nothing else exists
    on this serializer, so any other key in the request body is silently dropped."""

    class Meta:
        model = MedicalRecord
        fields = ("image", "doc_type")

    def validate_image(self, image):
        ext = check_image(image)
        image.name = f"upload{ext}"   # extension comes from the real format
        return image


class DoctorRecordUpdateSerializer(serializers.ModelSerializer):
    """What a DOCTOR may send when reviewing a record."""

    class Meta:
        model = MedicalRecord
        fields = ("diagnosis", "medications", "visit_date", "notes")

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs