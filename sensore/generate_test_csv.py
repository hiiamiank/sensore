"""
generate_test_csv.py

Run this script once to create a test CSV file
that you can upload to the Sensore application.

How to run:
    python generate_test_csv.py

Output:
    test_data.csv  (created in the same folder as this script)

The CSV contains 3 frames of 32x32 pressure data.
Frame 1 = low pressure  (safe range)
Frame 2 = medium pressure (will trigger a MEDIUM alert)
Frame 3 = high pressure  (will trigger a HIGH alert)
"""

import random
import csv

FRAMES    = 3
ROWS      = 32
COLS      = 32

def make_frame(base_pressure, hot_zone=True):
    """
    Generate one 32x32 frame.
    hot_zone=True adds a high-pressure cluster in the centre
    to simulate a real sitting posture.
    """
    matrix = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            # Background noise
            val = random.randint(1, base_pressure // 4)

            if hot_zone:
                # Create a pressure cluster around row 18-24, col 12-20
                # (simulates ischial region when sitting)
                dr = r - 20
                dc = c - 16
                dist = (dr**2 + dc**2) ** 0.5
                if dist < 8:
                    intensity = int((1 - dist / 8) * base_pressure)
                    val = min(4095, val + intensity)

            row.append(val)
        matrix.append(row)
    return matrix


# Frame definitions
frames = [
    make_frame(base_pressure=800,  hot_zone=True),   # Frame 1: safe  (~PPI 800)
    make_frame(base_pressure=2200, hot_zone=True),   # Frame 2: medium (~PPI 2200)
    make_frame(base_pressure=3800, hot_zone=True),   # Frame 3: high  (~PPI 3800)
]

output_file = 'test_data.csv'

with open(output_file, 'w', newline='') as f:
    writer = csv.writer(f)
    for frame in frames:
        for row in frame:
            writer.writerow(row)

print(f"Done! Created '{output_file}' with {FRAMES} frames ({FRAMES * ROWS} rows total).")
print("Upload this file on the session detail page in the app.")