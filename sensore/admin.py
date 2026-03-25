from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import User, PatientProfile, Session, PressureFrame, Alert, Comment, Report


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display  = ('email', 'username', 'role', 'is_active', 'created_at')
    list_filter   = ('role', 'is_active')
    search_fields = ('email', 'username')


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display  = ('full_name', 'user', 'assigned_clinician', 'created_at')
    search_fields = ('full_name',)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display  = ('id', 'patient', 'session_start', 'session_end', 'device_id')
    list_filter   = ('patient',)


@admin.register(PressureFrame)
class PressureFrameAdmin(admin.ModelAdmin):
    list_display  = ('id', 'session', 'recorded_at', 'peak_pressure_index', 'contact_area_pct', 'flagged_for_review')
    list_filter   = ('flagged_for_review',)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display  = ('id', 'patient', 'severity', 'triggered_at', 'acknowledged')
    list_filter   = ('severity', 'acknowledged')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display  = ('id', 'author', 'frame', 'created_at')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display  = ('id', 'patient', 'period_start', 'period_end', 'created_at')