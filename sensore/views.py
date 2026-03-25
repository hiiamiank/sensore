"""
views.py — Sensore Application

All views for authentication, dashboard, pressure data,
alerts, comments, reports, and admin user management.

Role access summary:
  patient    -> own data only
  clinician  -> own patients' data
  admin      -> full access + user management
"""

import json
import csv
import io
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Avg, Max, Min, Count
from django.core.paginator import Paginator

from .models import (
    User, PatientProfile, Session,
    PressureFrame, Alert, Comment, Report,
)
from .decorators import role_required          
from .utils import generate_alert_if_needed    


#  AUTHENTICATION

def login_view(request):
    """
    GET  → render login page
    POST → authenticate and redirect based on role
    """
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username or user.email}!")
            return _redirect_by_role(user)
        else:
            messages.error(request, "Invalid email or password.")

    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


def _redirect_by_role(user):
    """Helper: send users to the right dashboard after login."""
    if user.is_admin:
        return redirect('admin_dashboard')
    if user.is_clinician:
        return redirect('clinician_dashboard')
    return redirect('patient_dashboard')


#  PATIENT DASHBOARD

@login_required
@role_required('patient')
def patient_dashboard(request):
    """
    Patient's own dashboard — shows their sessions, latest heatmap,
    key metrics, alerts, and comment thread.
    """
    profile = get_object_or_404(PatientProfile, user=request.user)

    # Latest session
    latest_session = (
        profile.sessions
        .prefetch_related('frames')
        .order_by('-session_start')
        .first()
    )

    # Latest frame metrics
    latest_frame = None
    if latest_session:
        latest_frame = latest_session.frames.order_by('-recorded_at').first()

    # Recent unacknowledged alerts
    active_alerts = (
        profile.alerts
        .filter(acknowledged=False)
        .select_related('frame')
        .order_by('-triggered_at')[:5]
    )

    # Time range filter — default 24h
    hours = int(request.GET.get('hours', 24))
    if hours not in [1, 6, 24, 168]:
        hours = 24
    since = timezone.now() - timedelta(hours=hours)

    metric_history = list(
        PressureFrame.objects
        .filter(session__patient=profile, recorded_at__gte=since)
        .order_by('recorded_at')
        .values('recorded_at', 'peak_pressure_index', 'contact_area_pct')
    )
    metric_history_json = json.dumps([
        {
            'recorded_at':         f['recorded_at'].isoformat(),
            'peak_pressure_index': f['peak_pressure_index'],
            'contact_area_pct':    f['contact_area_pct'],
        }
        for f in metric_history
    ])

    context = {
        'profile':        profile,
        'latest_session': latest_session,
        'latest_frame':   latest_frame,
        'active_alerts':  active_alerts,
        'metric_history': metric_history_json,
        'hours':          hours,
    }
    return render(request, 'patient/dashboard.html', context)


@login_required
@role_required('patient')
def patient_session_list(request):
    """List all sessions for the logged-in patient."""
    profile  = get_object_or_404(PatientProfile, user=request.user)
    sessions = profile.sessions.order_by('-session_start')
    paginator = Paginator(sessions, 10)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'patient/session_list.html', {'page_obj': page, 'profile': profile})


@login_required
@role_required('patient')
def patient_session_detail(request, session_id):
    """Detail view for a single session — frame list + chart data."""
    profile = get_object_or_404(PatientProfile, user=request.user)
    session = get_object_or_404(Session, id=session_id, patient=profile)
    frames  = session.frames.order_by('recorded_at')
    return render(request, 'patient/session_detail.html', {
        'session': session,
        'frames':  frames,
        'profile': profile,
    })


#  CLINICIAN DASHBOARD

@login_required
@role_required('clinician')
def clinician_dashboard(request):
    """
    Clinician overview — all assigned patients with latest metrics
    and outstanding alert counts.
    """
    patients = (
        PatientProfile.objects
        .filter(assigned_clinician=request.user)
        .prefetch_related('sessions', 'alerts')
        .select_related('user')
    )

    # Build summary cards
    patient_summaries = []
    for p in patients:
        latest = (
            PressureFrame.objects
            .filter(session__patient=p)
            .order_by('-recorded_at')
            .first()
        )
        alert_count = p.alerts.filter(acknowledged=False).count()
        patient_summaries.append({
            'profile':     p,
            'latest_frame': latest,
            'alert_count': alert_count,
        })

    context = {'patient_summaries': patient_summaries}
    return render(request, 'clinician/dashboard.html', context)


@login_required
@role_required('clinician')
def clinician_patient_detail(request, patient_id):
    """
    Full patient view for a clinician — heatmap, metrics, alerts,
    trend chart, and comment thread.
    """
    # Ensure this patient belongs to the requesting clinician
    profile = get_object_or_404(
        PatientProfile,
        id=patient_id,
        assigned_clinician=request.user,
    )

    # Time range filter (default: last 24 h)
    hours = int(request.GET.get('hours', 24))
    since = timezone.now() - timedelta(hours=hours)

    latest_session = profile.sessions.order_by('-session_start').first()
    latest_frame   = None
    if latest_session:
        latest_frame = latest_session.frames.order_by('-recorded_at').first()

    # Metric history for chart
    metric_history = list(
        PressureFrame.objects
        .filter(session__patient=profile, recorded_at__gte=since)
        .order_by('recorded_at')
        .values('recorded_at', 'peak_pressure_index', 'contact_area_pct')
    )
    metric_history_json = json.dumps([
        {
            'recorded_at':         f['recorded_at'].isoformat(),
            'peak_pressure_index': f['peak_pressure_index'],
            'contact_area_pct':    f['contact_area_pct'],
        }
        for f in metric_history
    ])

    # Alerts (all unacknowledged)
    alerts = (
        profile.alerts
        .filter(acknowledged=False)
        .select_related('frame')
        .order_by('-triggered_at')
    )

    # Flagged frames for review
    flagged_frames = (
        PressureFrame.objects
        .filter(session__patient=profile, flagged_for_review=True)
        .order_by('-recorded_at')[:10]
    )

    context = {
        'profile':         profile,
        'latest_frame':    latest_frame,
        'latest_session':  latest_session,
        'metric_history':  metric_history_json,
        'alerts':          alerts,
        'flagged_frames':  flagged_frames,
        'hours':           hours,
    }
    return render(request, 'clinician/patient_detail.html', context)


@login_required
@role_required('clinician')
def clinician_patient_sessions(request, patient_id):
    """All sessions for a given patient (clinician view)."""
    profile  = get_object_or_404(PatientProfile, id=patient_id, assigned_clinician=request.user)
    sessions = profile.sessions.order_by('-session_start')
    paginator = Paginator(sessions, 15)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'clinician/session_list.html', {
        'page_obj': page,
        'profile':  profile,
    })


#  PRESSURE FRAMES

@login_required
@require_POST
@role_required('clinician', 'admin')
def resolve_frame(request, frame_id):
    """
    POST: Mark a flagged frame as resolved (clears flagged_for_review).
    Only the assigned clinician or an admin can resolve.
    """
    frame   = get_object_or_404(PressureFrame, id=frame_id)
    patient = frame.session.patient

    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    frame.flagged_for_review = False
    frame.save(update_fields=['flagged_for_review'])

    return JsonResponse({'status': 'resolved', 'frame_id': frame_id})

@login_required
def frame_detail(request, frame_id):
    """
    Detail view for a single pressure frame — heatmap + comments.
    Accessible by the patient who owns the frame or their clinician.
    """
    frame = get_object_or_404(PressureFrame, id=frame_id)
    patient = frame.session.patient

    # Access control
    if request.user.is_patient and patient.user != request.user:
        return HttpResponseForbidden()
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return HttpResponseForbidden()

    # Top-level comments + their replies
    comments = (
        frame.comments
        .filter(parent__isnull=True)
        .select_related('author')
        .prefetch_related('replies__author')
        .order_by('created_at')
    )

    return render(request, 'frames/detail.html', {
        'frame':    frame,
        'comments': comments,
        'patient':  patient,
    })


@login_required
def frame_heatmap_data(request, frame_id):
    """
    API: Returns the 32×32 matrix as JSON for JS rendering.
    Used by the frontend heatmap canvas.
    """
    frame = get_object_or_404(PressureFrame, id=frame_id)
    patient = frame.session.patient

    if request.user.is_patient and patient.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    reader = csv.reader(io.StringIO(frame.csv_data))
    matrix = [[int(v) for v in row] for row in reader if row]

    return JsonResponse({
        'frame_id':           frame.id,
        'recorded_at':        frame.recorded_at.isoformat(),
        'peak_pressure_index': frame.peak_pressure_index,
        'contact_area_pct':   frame.contact_area_pct,
        'matrix':             matrix,
    })


@login_required
def metric_history_api(request, patient_id):
    """
    API: Returns PPI and contact area history for chart rendering.
    Accepts ?hours=1|6|24|168 query param.
    """
    # Resolve patient and check permission
    profile = get_object_or_404(PatientProfile, id=patient_id)
    if request.user.is_patient and profile.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and profile.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    hours = int(request.GET.get('hours', 24))
    since = timezone.now() - timedelta(hours=hours)

    frames = (
        PressureFrame.objects
        .filter(session__patient=profile, recorded_at__gte=since)
        .order_by('recorded_at')
        .values('recorded_at', 'peak_pressure_index', 'contact_area_pct')
    )

    data = [
        {
            'time':  f['recorded_at'].isoformat(),
            'ppi':   f['peak_pressure_index'],
            'ca':    f['contact_area_pct'],
        }
        for f in frames
    ]
    return JsonResponse({'data': data, 'hours': hours})


#  CSV UPLOAD (Ingest sensor data)

@login_required
@require_POST
def upload_csv(request, session_id):
    """
    POST: Accept a CSV file upload for a session.
    Parses each 32-row block as one PressureFrame,
    computes metrics, and fires alerts if needed.

    Expected: multipart/form-data with field 'csv_file'
    """
    session = get_object_or_404(Session, id=session_id)
    patient = session.patient

    # Only the patient themselves or their clinician may upload
    if request.user.is_patient and patient.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    uploaded_file = request.FILES.get('csv_file')
    if not uploaded_file:
        messages.error(request, 'No file provided.')
        return redirect('patient_session_detail', session_id=session_id)

    text    = uploaded_file.read().decode('utf-8')
    reader  = list(csv.reader(io.StringIO(text)))
    frames_created = 0

    # Split rows into 32-row blocks (each block = 1 frame)
    for i in range(0, len(reader), 32):
        block = reader[i:i + 32]
        if len(block) < 32:
            break  # Skip incomplete trailing block

        csv_text = '\n'.join(','.join(row) for row in block)
        frame = PressureFrame.objects.create(
            session     = session,
            recorded_at = timezone.now(),
            csv_data    = csv_text,
        )
        frame.compute_metrics()
        generate_alert_if_needed(frame, patient)
        frames_created += 1

    messages.success(request, f'Upload successful — {frames_created} frame(s) processed.')
    return redirect('patient_session_detail', session_id=session_id)


#  ALERTS

@login_required
def alert_list(request):
    """
    List alerts relevant to the requesting user's role.
    Supports ?acknowledged=true|false filter.
    """
    acked = request.GET.get('acknowledged', 'false').lower() == 'true'

    if request.user.is_patient:
        profile = get_object_or_404(PatientProfile, user=request.user)
        alerts  = Alert.objects.filter(patient=profile, acknowledged=acked)
    elif request.user.is_clinician:
        alerts = Alert.objects.filter(
            patient__assigned_clinician=request.user,
            acknowledged=acked,
        ).select_related('patient', 'frame')
    else:  # admin
        alerts = Alert.objects.filter(acknowledged=acked).select_related('patient', 'frame')

    alerts = alerts.order_by('-triggered_at')
    paginator = Paginator(alerts, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'alerts/list.html', {
        'page_obj':   page,
        'show_acked': acked,
    })


@login_required
@require_POST
def acknowledge_alert(request, alert_id):
    """Mark a single alert as acknowledged."""
    alert   = get_object_or_404(Alert, id=alert_id)
    patient = alert.patient

    if request.user.is_patient and patient.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    alert.acknowledged    = True
    alert.acknowledged_by = request.user
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=['acknowledged', 'acknowledged_by', 'acknowledged_at'])

    return JsonResponse({'status': 'acknowledged', 'alert_id': alert_id})


#  COMMENTS

@login_required
@require_POST
def add_comment(request, frame_id):
    """
    POST: Add a top-level comment or reply to a frame.
    Body (JSON): { "body": "...", "parent_id": null|int }
    """
    frame   = get_object_or_404(PressureFrame, id=frame_id)
    patient = frame.session.patient

    if request.user.is_patient and patient.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    body      = payload.get('body', '').strip()
    parent_id = payload.get('parent_id')

    if not body:
        return JsonResponse({'error': 'Comment body cannot be empty'}, status=400)

    parent = None
    if parent_id:
        parent = get_object_or_404(Comment, id=parent_id, frame=frame)

    comment = Comment.objects.create(
        frame  = frame,
        author = request.user,
        parent = parent,
        body   = body,
    )

    # Flag the frame for clinician review when a patient comments
    if request.user.is_patient:
        frame.flagged_for_review = True
        frame.save(update_fields=['flagged_for_review'])

    return JsonResponse({
        'id':         comment.id,
        'body':       comment.body,
        'author':     comment.author.username or comment.author.email,
        'role':       comment.author.role,
        'created_at': comment.created_at.isoformat(),
        'parent_id':  parent_id,
    }, status=201)


@login_required
def frame_comments(request, frame_id):
    """API: Return all comments for a frame as JSON."""
    frame   = get_object_or_404(PressureFrame, id=frame_id)
    patient = frame.session.patient

    if request.user.is_patient and patient.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.is_clinician and patient.assigned_clinician != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    comments = (
        frame.comments
        .filter(parent__isnull=True)
        .select_related('author')
        .prefetch_related('replies__author')
        .order_by('created_at')
    )

    def serialize(c):
        return {
            'id':         c.id,
            'body':       c.body,
            'author':     c.author.username or c.author.email,
            'role':       c.author.role,
            'created_at': c.created_at.isoformat(),
            'replies': [serialize(r) for r in c.replies.all()],
        }

    return JsonResponse({'comments': [serialize(c) for c in comments]})


#  REPORTS

@login_required
def report_list(request):
    """List reports for the current user's scope."""
    if request.user.is_patient:
        profile = get_object_or_404(PatientProfile, user=request.user)
        reports = Report.objects.filter(patient=profile)
    elif request.user.is_clinician:
        reports = Report.objects.filter(
            patient__assigned_clinician=request.user
        ).select_related('patient')
    else:
        reports = Report.objects.all().select_related('patient', 'generated_by')

    reports = reports.order_by('-created_at')
    paginator = Paginator(reports, 10)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'reports/list.html', {'page_obj': page})


@login_required
@role_required('clinician', 'admin')
def generate_report(request, patient_id):
    """
    GET  → show report generation form
    POST → create report for a given patient + time range
    """
    profile = get_object_or_404(PatientProfile, id=patient_id)

    if request.user.is_clinician and profile.assigned_clinician != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        period_start = request.POST.get('period_start')
        period_end   = request.POST.get('period_end')

        if not period_start or not period_end:
            messages.error(request, "Please provide both start and end dates.")
            return redirect('generate_report', patient_id=patient_id)

        from django.utils.dateparse import parse_datetime
        start_dt = parse_datetime(period_start + 'T00:00:00')
        end_dt   = parse_datetime(period_end   + 'T23:59:59')

        frames = PressureFrame.objects.filter(
            session__patient = profile,
            recorded_at__range = (start_dt, end_dt),
        )

        # Aggregate stats for the summary
        stats = frames.aggregate(
            avg_ppi  = Avg('peak_pressure_index'),
            max_ppi  = Max('peak_pressure_index'),
            min_ppi  = Min('peak_pressure_index'),
            avg_ca   = Avg('contact_area_pct'),
            total    = Count('id'),
        )
        alert_count = Alert.objects.filter(
            patient=profile,
            triggered_at__range=(start_dt, end_dt),
        ).count()

        summary = (
            f"Period: {period_start} to {period_end}. "
            f"Total frames: {stats['total']}. "
            f"Average PPI: {stats['avg_ppi']:.1f} (max {stats['max_ppi']}, min {stats['min_ppi']}). "
            f"Average contact area: {stats['avg_ca']:.1f}%. "
            f"Alerts triggered: {alert_count}."
        )

        report = Report.objects.create(
            patient      = profile,
            generated_by = request.user,
            period_start = start_dt,
            period_end   = end_dt,
            summary      = summary,
        )
        messages.success(request, "Report generated successfully.")
        return redirect('report_detail', report_id=report.id)

    return render(request, 'reports/generate.html', {'profile': profile})


@login_required
def report_detail(request, report_id):
    """Full report view with aggregated stats and comparison to previous period."""
    report  = get_object_or_404(Report, id=report_id)
    profile = report.patient

    if request.user.is_patient and profile.user != request.user:
        return HttpResponseForbidden()
    if request.user.is_clinician and profile.assigned_clinician != request.user:
        return HttpResponseForbidden()

    # Frames within this report's period
    frames = PressureFrame.objects.filter(
        session__patient   = profile,
        recorded_at__range = (report.period_start, report.period_end),
    ).order_by('recorded_at')

    stats = frames.aggregate(
        avg_ppi = Avg('peak_pressure_index'),
        max_ppi = Max('peak_pressure_index'),
        avg_ca  = Avg('contact_area_pct'),
        total   = Count('id'),
    )

    # Comparison: equivalent previous period
    period_len  = report.period_end - report.period_start
    prev_start  = report.period_start - period_len
    prev_end    = report.period_start

    prev_stats = PressureFrame.objects.filter(
        session__patient   = profile,
        recorded_at__range = (prev_start, prev_end),
    ).aggregate(
        avg_ppi = Avg('peak_pressure_index'),
        avg_ca  = Avg('contact_area_pct'),
    )

    chart_data = json.dumps([
        {
            'recorded_at':         f['recorded_at'].isoformat(),
            'peak_pressure_index': f['peak_pressure_index'],
            'contact_area_pct':    f['contact_area_pct'],
        }
        for f in frames.values('recorded_at', 'peak_pressure_index', 'contact_area_pct')
    ])

    context = {
        'report':      report,
        'profile':     profile,
        'frames':      frames,
        'stats':       stats,
        'prev_stats':  prev_stats,
        'chart_data':  chart_data,
    }
    return render(request, 'reports/detail.html', context)


#  ADMIN — USER MANAGEMENT

@login_required
@role_required('admin')
def admin_dashboard(request):
    """Admin overview — user counts, recent activity."""
    context = {
        'total_patients':   PatientProfile.objects.count(),
        'total_clinicians': User.objects.filter(role=User.CLINICIAN).count(),
        'total_admins':     User.objects.filter(role=User.ADMIN).count(),
        'open_alerts':      Alert.objects.filter(acknowledged=False).count(),
        'recent_users':     User.objects.order_by('-created_at')[:10],
    }
    return render(request, 'admin_panel/dashboard.html', context)


@login_required
@role_required('admin')
def admin_user_list(request):
    """Admin: list all users with optional role filter."""
    role   = request.GET.get('role', '')
    users  = User.objects.all().select_related()
    if role in [User.PATIENT, User.CLINICIAN, User.ADMIN]:
        users = users.filter(role=role)
    users = users.order_by('role', 'email')
    paginator = Paginator(users, 25)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'admin_panel/user_list.html', {
        'page_obj':    page,
        'role_filter': role,
    })


@login_required
@role_required('admin')
def admin_create_user(request):
    """
    Admin: Create any type of user account.
    GET  → blank form
    POST → validate and create
    """
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role     = request.POST.get('role', User.PATIENT)

        if User.objects.filter(email=email).exists():
            messages.error(request, f"A user with email '{email}' already exists.")
            return redirect('admin_create_user')

        if role not in [User.PATIENT, User.CLINICIAN, User.ADMIN]:
            messages.error(request, "Invalid role selected.")
            return redirect('admin_create_user')

        user = User.objects.create_user(
            email    = email,
            password = password,
            username = username,
            role     = role,
        )

        # If patient, automatically create their profile
        if role == User.PATIENT:
            full_name  = request.POST.get('full_name', username or email)
            clinician_id = request.POST.get('clinician_id')
            clinician  = None
            if clinician_id:
                clinician = User.objects.filter(id=clinician_id, role=User.CLINICIAN).first()
            PatientProfile.objects.create(
                user               = user,
                full_name          = full_name,
                assigned_clinician = clinician,
            )

        messages.success(request, f"Account created for {email} ({role}).")
        return redirect('admin_user_list')

    clinicians = User.objects.filter(role=User.CLINICIAN, is_active=True)
    return render(request, 'admin_panel/create_user.html', {'clinicians': clinicians})


@login_required
@role_required('admin')
def admin_edit_user(request, user_id):
    """
    Admin: Edit any user account — update role, clinician assignment, active status.
    """
    target_user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        target_user.username  = request.POST.get('username', target_user.username)
        target_user.role      = request.POST.get('role', target_user.role)
        target_user.is_active = request.POST.get('is_active') == 'on'
        target_user.save()

        # Update patient profile clinician assignment if applicable
        if target_user.is_patient and hasattr(target_user, 'patient_profile'):
            clinician_id = request.POST.get('clinician_id')
            if clinician_id:
                clinician = User.objects.filter(id=clinician_id, role=User.CLINICIAN).first()
                target_user.patient_profile.assigned_clinician = clinician
                target_user.patient_profile.save(update_fields=['assigned_clinician'])

        messages.success(request, f"User {target_user.email} updated.")
        return redirect('admin_user_list')

    clinicians = User.objects.filter(role=User.CLINICIAN, is_active=True)
    return render(request, 'admin_panel/edit_user.html', {
        'target_user': target_user,
        'clinicians':  clinicians,
    })


@login_required
@role_required('admin')
@require_POST
def admin_deactivate_user(request, user_id):
    """Admin: Soft-delete (deactivate) a user account."""
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        return JsonResponse({'error': 'Cannot deactivate your own account'}, status=400)
    user.is_active = False
    user.save(update_fields=['is_active'])
    return JsonResponse({'status': 'deactivated', 'user_id': user_id})