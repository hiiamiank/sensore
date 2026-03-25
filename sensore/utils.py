"""
utils.py — Sensore Application

Helper functions used across views.
"""

from .models import Alert


# Threshold constants — adjust as needed
PPI_HIGH_THRESHOLD   = 3000   # Triggers a HIGH alert
PPI_MEDIUM_THRESHOLD = 1800   # Triggers a MEDIUM alert
CA_HIGH_THRESHOLD    = 80     # High contact area (% of mat covered)


def generate_alert_if_needed(frame, patient):
    """
    Inspects a freshly computed PressureFrame and creates
    an Alert record if thresholds are exceeded.

    Called immediately after frame.compute_metrics().
    """
    ppi = frame.peak_pressure_index or 0
    ca  = frame.contact_area_pct    or 0

    severity = None
    message  = ""

    if ppi >= PPI_HIGH_THRESHOLD:
        severity = Alert.HIGH
        message  = (
            f"Critical pressure detected. PPI {ppi:.0f} exceeds the high threshold "
            f"({PPI_HIGH_THRESHOLD}). Immediate repositioning recommended."
        )
    elif ppi >= PPI_MEDIUM_THRESHOLD:
        severity = Alert.MEDIUM
        message  = (
            f"Elevated pressure detected. PPI {ppi:.0f} exceeds the medium threshold "
            f"({PPI_MEDIUM_THRESHOLD}). Monitor closely and consider repositioning."
        )

    if severity:
        Alert.objects.create(
            frame    = frame,
            patient  = patient,
            severity = severity,
            message  = message,
        )

        # Flag the frame for clinician review
        frame.flagged_for_review = True
        frame.save(update_fields=['flagged_for_review'])