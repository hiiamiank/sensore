from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


# Custom User Manager

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


# User (custom auth model)

class User(AbstractBaseUser, PermissionsMixin):
    PATIENT   = 'patient'
    CLINICIAN = 'clinician'
    ADMIN     = 'admin'

    ROLE_CHOICES = [
        (PATIENT,   'Patient'),
        (CLINICIAN, 'Clinician'),
        (ADMIN,     'Admin'),
    ]

    email      = models.EmailField(unique=True)
    username   = models.CharField(max_length=150, blank=True)
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default=PATIENT)
    is_active  = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'User'

    def __str__(self):
        return f"{self.email} ({self.role})"

    # Role helpers
    @property
    def is_patient(self):
        return self.role == self.PATIENT

    @property
    def is_clinician(self):
        return self.role == self.CLINICIAN

    @property
    def is_admin(self):
        return self.role == self.ADMIN


# Patient Profile

class PatientProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='patient_profile',
        limit_choices_to={'role': User.PATIENT},
    )
    assigned_clinician = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patients',
        limit_choices_to={'role': User.CLINICIAN},
    )
    full_name     = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    medical_notes = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'patient_profiles'
        verbose_name = 'Patient Profile'

    def __str__(self):
        return self.full_name


# Session (one continuous monitoring period)

class Session(models.Model):
    patient       = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    session_start = models.DateTimeField()
    session_end   = models.DateTimeField(null=True, blank=True)
    device_id     = models.CharField(max_length=100, blank=True)
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = 'sessions'
        ordering  = ['-session_start']
        verbose_name = 'Session'

    def __str__(self):
        return f"Session {self.id} – {self.patient.full_name} ({self.session_start.date()})"

    @property
    def duration_minutes(self):
        if self.session_end:
            delta = self.session_end - self.session_start
            return round(delta.total_seconds() / 60, 1)
        return None


# Pressure Frame (one 32×32 CSV snapshot)

class PressureFrame(models.Model):
    session             = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='frames',
    )
    recorded_at         = models.DateTimeField(db_index=True)

    # Pre-computed metrics (stored so charts don't re-calculate)
    peak_pressure_index = models.FloatField(
        null=True, blank=True,
        help_text="Highest recorded pressure value, excluding regions < 10 px"
    )
    contact_area_pct    = models.FloatField(
        null=True, blank=True,
        help_text="Percentage of pixels above the lower pressure threshold"
    )

    # Raw sensor data stored as CSV text (32 cols × 32 rows)
    csv_data            = models.TextField(
        help_text="Raw 32×32 sensor CSV data"
    )

    # Flag set when clinician marks for review
    flagged_for_review  = models.BooleanField(default=False)

    class Meta:
        db_table = 'pressure_frames'
        ordering = ['recorded_at']
        indexes  = [
            models.Index(fields=['session', 'recorded_at']),
        ]

    def __str__(self):
        return f"Frame {self.id} @ {self.recorded_at}"

    def compute_metrics(self):
        """
        Parse csv_data and compute PPI and contact area %.
        Call this after saving raw data; updates and saves the record.
        Values range 1–4095; 1 = zero-force baseline.
        """
        import csv, io

        LOWER_THRESHOLD = 100  # pixels above this count as contact
        MIN_REGION_SIZE = 10   # exclude isolated regions smaller than this

        rows = list(csv.reader(io.StringIO(self.csv_data)))
        matrix = [[int(v) for v in row] for row in rows if row]

        all_pixels = [v for row in matrix for v in row]
        active = [v for v in all_pixels if v > LOWER_THRESHOLD]

        self.contact_area_pct = round(len(active) / len(all_pixels) * 100, 2)

        # PPI: find contiguous regions ≥ 10 px and report highest value
        visited = [[False] * 32 for _ in range(32)]
        regions = []

        def flood_fill(r, c):
            stack, region = [(r, c)], []
            while stack:
                row, col = stack.pop()
                if row < 0 or row >= 32 or col < 0 or col >= 32:
                    continue
                if visited[row][col] or matrix[row][col] <= LOWER_THRESHOLD:
                    continue
                visited[row][col] = True
                region.append(matrix[row][col])
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    stack.append((row+dr, col+dc))
            return region

        for r in range(32):
            for c in range(32):
                if not visited[r][c] and matrix[r][c] > LOWER_THRESHOLD:
                    region = flood_fill(r, c)
                    if len(region) >= MIN_REGION_SIZE:
                        regions.append(region)

        if regions:
            self.peak_pressure_index = max(max(r) for r in regions)
        else:
            self.peak_pressure_index = 0.0

        self.save(update_fields=['peak_pressure_index', 'contact_area_pct'])


# Alert

class Alert(models.Model):
    LOW    = 'low'
    MEDIUM = 'medium'
    HIGH   = 'high'

    SEVERITY_CHOICES = [
        (LOW,    'Low'),
        (MEDIUM, 'Medium'),
        (HIGH,   'High'),
    ]

    frame        = models.ForeignKey(
        PressureFrame,
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    patient      = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    severity     = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=MEDIUM)
    message      = models.TextField()
    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'alerts'
        ordering = ['-triggered_at']

    def __str__(self):
        return f"[{self.severity.upper()}] Alert for {self.patient.full_name} @ {self.triggered_at}"


# Comment (threaded, linked to a frame)

class Comment(models.Model):
    frame      = models.ForeignKey(
        PressureFrame,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    author     = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    parent     = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comments'
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.email} on Frame {self.frame_id}"

    @property
    def is_reply(self):
        return self.parent_id is not None


# Report
class Report(models.Model):
    patient      = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='reports',
    )
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_reports',
    )
    period_start = models.DateTimeField()
    period_end   = models.DateTimeField()
    summary      = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reports'
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"Report for {self.patient.full_name} "
            f"({self.period_start.date()} – {self.period_end.date()})"
        )