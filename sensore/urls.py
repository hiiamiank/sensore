"""
urls.py — Sensore Application


All URL patterns organised by section.
Include this file in your project-level urls.py:

    path('', include('sensore.urls')),

or mount it under a prefix:

    path('app/', include('sensore.urls')),
"""

from django.urls import path
from . import views

urlpatterns = [

    # Authentication
    path(
        '',
        views.login_view,
        name='login',
    ),
    path(
        'logout/',
        views.logout_view,
        name='logout',
    ),

    # Patient routes
    path(
        'patient/dashboard/',
        views.patient_dashboard,
        name='patient_dashboard',
    ),
    path(
        'patient/sessions/',
        views.patient_session_list,
        name='patient_session_list',
    ),
    path(
        'patient/sessions/<int:session_id>/',
        views.patient_session_detail,
        name='patient_session_detail',
    ),

    # Clinician routes
    path(
        'clinician/dashboard/',
        views.clinician_dashboard,
        name='clinician_dashboard',
    ),
    path(
        'clinician/patients/<int:patient_id>/',
        views.clinician_patient_detail,
        name='clinician_patient_detail',
    ),
    path(
        'clinician/patients/<int:patient_id>/sessions/',
        views.clinician_patient_sessions,
        name='clinician_patient_sessions',
    ),

    # Pressure Frames
    path(
        'frames/<int:frame_id>/',
        views.frame_detail,
        name='frame_detail',
    ),

    # APIs (JSON)
    path(
        'api/frames/<int:frame_id>/heatmap/',
        views.frame_heatmap_data,
        name='api_frame_heatmap',
    ),
    path(
        'api/patients/<int:patient_id>/metrics/',
        views.metric_history_api,
        name='api_metric_history',
    ),
    path(
        'api/frames/<int:frame_id>/comments/',
        views.frame_comments,
        name='api_frame_comments',
    ),
    path(
        'api/frames/<int:frame_id>/comments/add/',
        views.add_comment,
        name='api_add_comment',
    ),
    path(
        'api/alerts/<int:alert_id>/acknowledge/',
        views.acknowledge_alert,
        name='api_acknowledge_alert',
    ),

    path(
        'api/frames/<int:frame_id>/resolve/',
        views.resolve_frame,
        name='api_resolve_frame',
    ),

    # CSV Upload
    path(
        'sessions/<int:session_id>/upload/',
        views.upload_csv,
        name='upload_csv',
    ),

    # Alerts
    path(
        'alerts/',
        views.alert_list,
        name='alert_list',
    ),

    # Reports
    path(
        'reports/',
        views.report_list,
        name='report_list',
    ),
    path(
        'reports/<int:report_id>/',
        views.report_detail,
        name='report_detail',
    ),
    path(
        'reports/generate/<int:patient_id>/',
        views.generate_report,
        name='generate_report',
    ),

    # Admin panel
    path(
        'admin-panel/dashboard/',
        views.admin_dashboard,
        name='admin_dashboard',
    ),
    path(
        'admin-panel/users/',
        views.admin_user_list,
        name='admin_user_list',
    ),
    path(
        'admin-panel/users/create/',
        views.admin_create_user,
        name='admin_create_user',
    ),
    path(
        'admin-panel/users/<int:user_id>/edit/',
        views.admin_edit_user,
        name='admin_edit_user',
    ),
    path(
        'admin-panel/users/<int:user_id>/deactivate/',
        views.admin_deactivate_user,
        name='admin_deactivate_user',
    ),
]