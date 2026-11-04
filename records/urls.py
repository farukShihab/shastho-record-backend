from django.urls import path

from .access_views import AccessListCreateView, AccessRevokeView, DoctorListView, PatientListView
from .views import RecordDetailView, RecordImageView, RecordListCreateView

from .timeline import TimelineView

urlpatterns = [
    path("records/", RecordListCreateView.as_view(), name="record-list"),
    path("records/<int:pk>/", RecordDetailView.as_view(), name="record-detail"),
    path("records/<int:pk>/image/", RecordImageView.as_view(), name="record-image"),
    path("doctors/", DoctorListView.as_view(), name="doctor-list"),
    path("access/", AccessListCreateView.as_view(), name="access-list"),
    path("access/<int:pk>/revoke/", AccessRevokeView.as_view(), name="access-revoke"),
    path("timeline/", TimelineView.as_view(), name="timeline"),
    path("patients/", PatientListView.as_view(), name="patient-list"),
]
