from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .access_serializers import (
    AccessGrantCreateSerializer, AccessGrantSerializer, DoctorListSerializer,
    PatientListSerializer,
)
from .models import AccessGrant
from .permissions import IsPatient, IsDoctor, granted_patient_ids

User = get_user_model()


class DoctorListView(generics.ListAPIView):
    """Patients only: doctors they can choose to grant access to."""
    permission_classes = [IsPatient]
    serializer_class = DoctorListSerializer

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.DOCTOR, is_active=True).select_related("doctor_profile")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(username__icontains=search) | qs.filter(first_name__icontains=search) \
                | qs.filter(last_name__icontains=search) | qs.filter(doctor_profile__specialty__icontains=search)
        return qs.order_by("first_name", "username")


class AccessListCreateView(generics.ListCreateAPIView):
    """GET: my grants (active and revoked). POST: grant a doctor access."""
    permission_classes = [IsPatient]

    def get_serializer_class(self):
        return AccessGrantCreateSerializer if self.request.method == "POST" else AccessGrantSerializer

    def get_queryset(self):
        # Scoped to request.user: a patient can never see another patient's grants.
        return (AccessGrant.objects.filter(patient=self.request.user)
                .select_related("doctor", "doctor__doctor_profile")
                .order_by("-granted_at"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            grant = serializer.save(patient=request.user)   # patient comes from the token
        except IntegrityError:
            # Two simultaneous requests can slip past validation; the DB constraint catches it.
            return Response({"doctor": ["You have already given this doctor access."]},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(AccessGrantSerializer(grant).data, status=status.HTTP_201_CREATED)


class AccessRevokeView(APIView):
    """POST /api/access/<id>/revoke/: patient revokes one of THEIR grants."""
    permission_classes = [IsPatient]

    def post(self, request, pk):
        grant = get_object_or_404(AccessGrant, pk=pk, patient=request.user)
        if grant.revoked_at is None:
            grant.revoked_at = timezone.now()
            grant.save(update_fields=["revoked_at"])
        return Response(AccessGrantSerializer(grant).data)

class PatientListView(generics.ListAPIView):
    """Doctors only: patients with an ACTIVE grant to me."""
    permission_classes = [IsDoctor]
    serializer_class = PatientListSerializer

    def get_queryset(self):
        return (User.objects.filter(pk__in=granted_patient_ids(self.request.user))
                .select_related("patient_profile")
                .order_by("first_name", "username"))