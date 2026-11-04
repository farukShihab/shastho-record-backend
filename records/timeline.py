from django.contrib.auth import get_user_model
from django.db.models import DateField
from django.db.models.functions import Coalesce, TruncDate
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsPatientOrDoctor, granted_patient_ids, visible_records
from .serializers import RecordSerializer

User = get_user_model()


class TimelineItemSerializer(RecordSerializer):
    """A record plus the date it is placed at on the timeline, and the verifying clinic."""
    date = serializers.DateField(read_only=True)
    verified_by_clinic = serializers.SerializerMethodField()

    class Meta(RecordSerializer.Meta):
        fields = RecordSerializer.Meta.fields + ("date", "verified_by_clinic")
        read_only_fields = fields

    def get_verified_by_clinic(self, obj):
        profile = getattr(obj.verified_by, "doctor_profile", None) if obj.verified_by else None
        return profile.clinic_name if profile else None


class TimelineView(APIView):
    permission_classes = [IsPatientOrDoctor]

    def get(self, request):
        user = request.user

        if user.is_patient:
            patient = user            # a patient can only ever see their own timeline
        else:
            raw = request.query_params.get("patient")
            if not raw:
                raise ValidationError({"patient": "This query parameter is required for doctors."})
            try:
                patient_id = int(raw)
            except ValueError:
                raise ValidationError({"patient": "Must be a numeric patient id."})
            # One answer for "no such patient" and "no access", so ids can't be probed.
            if not granted_patient_ids(user).filter(patient_id=patient_id).exists():
                raise PermissionDenied("You do not have access to this patient's records.")
            patient = User.objects.select_related("patient_profile").get(pk=patient_id)

        # visit_date if a doctor filled it in, otherwise the upload day.
        # TruncDate converts created_at to a date in the project time zone (Asia/Dhaka).
        records = (
            visible_records(user)
            .filter(patient=patient)
            .select_related("verified_by__doctor_profile")
            .annotate(date=Coalesce("visit_date", TruncDate("created_at"), output_field=DateField()))
        )
        if request.query_params.get("order") == "asc":
            records = records.order_by("date", "created_at", "id")
        else:
            records = records.order_by("-date", "-created_at", "-id")

        profile = getattr(patient, "patient_profile", None)
        return Response({
            "patient": {
                "id": patient.id,
                "patient_code": profile.patient_code if profile else None,
                "name": patient.get_full_name() or patient.username,
            },
            "count": records.count(),
            "results": TimelineItemSerializer(records, many=True, context={"request": request}).data,
        })