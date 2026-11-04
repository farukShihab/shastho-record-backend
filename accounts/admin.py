from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import DoctorProfile, PatientProfile,User


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("patient_code", "user")
    search_fields = ("patient_code", "user__username", "user__email")
    readonly_fields = ("patient_code",)


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "clinic_name")
    search_fields = ("user__username", "specialty", "clinic_name")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_active")
    # Add `role` and `email` to the stock admin forms.
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role", {"fields": ("email", "role")}),
    )