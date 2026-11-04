from django.contrib import admin

from .models import AccessGrant, MedicalRecord


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "granted_at", "revoked_at")
    list_filter = ("revoked_at",)
    search_fields = ("patient__username", "doctor__username")


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doc_type", "status", "verified_by", "created_at")
    list_filter = ("doc_type", "status")
    search_fields = ("patient__username", "diagnosis")
    readonly_fields = ("created_at",)