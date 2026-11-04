from pathlib import Path

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MedicalRecord
from .permissions import IsDoctor, IsPatient, IsPatientOrDoctor, visible_records
from .serializers import DoctorRecordUpdateSerializer, PatientUploadSerializer, RecordSerializer

from django.http import FileResponse, Http404

CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class RecordListCreateView(generics.ListAPIView):
    """GET: records visible to me. POST: patient uploads an image."""
    serializer_class = RecordSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsPatient()]
        return [IsPatientOrDoctor()]

    def get_queryset(self):
        qs = visible_records(self.request.user)
        patient_id = self.request.query_params.get("patient")
        if patient_id and self.request.user.is_doctor:
            qs = qs.filter(patient_id=patient_id)   # still inside granted patients only
        return qs

    def post(self, request, *args, **kwargs):
        serializer = PatientUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Server-side fields come from request.user, never from the body.
        record = serializer.save(patient=request.user, uploaded_by=request.user)
        out = RecordSerializer(record, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)


class RecordDetailView(generics.RetrieveAPIView):
    """GET: one record I can see. PATCH: doctor reviews it (and verifies it)."""
    serializer_class = RecordSerializer

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsDoctor()]
        return [IsPatientOrDoctor()]

    def get_queryset(self):
        return visible_records(self.request.user)

    def patch(self, request, *args, **kwargs):
        record = self.get_object()   # 404 if the doctor has no active grant
        serializer = DoctorRecordUpdateSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(verified_by=request.user, status=MedicalRecord.Status.VERIFIED)
        out = RecordSerializer(record, context=self.get_serializer_context())
        return Response(out.data)


class RecordImageView(APIView):
    """Authenticated image download. Same visibility rules as the API."""

    def get(self, request, pk):
        record = get_object_or_404(visible_records(request.user), pk=pk)
        try:
            file = record.image.open("rb")
        except FileNotFoundError:
            raise Http404("Image file is missing.")
        ext = Path(record.image.name).suffix.lower()
        response = FileResponse(
            file,
            content_type=CONTENT_TYPES.get(ext, "application/octet-stream"),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response