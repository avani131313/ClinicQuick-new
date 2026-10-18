"""An anatomy-figure body (ecorché style) as a signed distance field: smoothly blended muscles,
standing with arms slightly away from the sides. Proportions change with sex.
Units are metres; feet at y=0, face toward +z."""
from sdf import Shape, rot
import numpy as np


def build(sex: str) -> Shape:
    f = sex == "female"
    S = Shape()
    # proportions
    H = 0.955 if f else 1.0           # overall height factor (applied at the end by the caller)
    sh = 0.168 if f else 0.19        # shoulder joint x
    hip = 0.092 if f else 0.088      # hip joint x
    m = 0.86 if f else 1.0           # muscle bulk factor
    waist = 0.105 if f else 0.122

    # ---- head --------------------------------------------------------------------
    S.ell("Head", (0, 1.655, -0.006), (0.077, 0.099, 0.094), fibre=(0, 1, 0.3), k=0.02)
    S.ell("Face", (0, 1.605, 0.03), (0.063, 0.074, 0.066), fibre=(1, 0.2, 0), k=0.03)
    S.ell("Face", (0, 1.552, 0.05), (0.034, 0.026, 0.03), fibre=(1, 0, 0), k=0.025)          # chin
    S.cone("Face", (0, 1.634, 0.086), (0, 1.607, 0.097), 0.009, 0.013, k=0.014, ends=False)   # nose
    S.mirror(lambda s: S.ell("Face", (s * 0.044, 1.585, 0.068), (0.026, 0.024, 0.02), fibre=(s, -0.4, 0), k=0.02))  # cheeks
    S.mirror(lambda s: S.ell("Ear", (s * 0.078, 1.632, -0.004), (0.011, 0.027, 0.019), k=0.01, tendon=0.3))
    S.mirror(lambda s: S.ell("Eye", (s * 0.031, 1.646, 0.078), (0.0125, 0.0085, 0.0085), k=0.004, tendon=1.0))
    S.mirror(lambda s: S.ell("Face", (s * 0.031, 1.662, 0.081), (0.022, 0.008, 0.012), fibre=(1, 0, 0), k=0.01))     # brow

    # ---- neck and shoulders ----------------------------------------------------
    S.cone("Neck", (0, 1.555, -0.01), (0, 1.455, 0.0), 0.046 * (0.9 if f else 1), 0.054 * (0.92 if f else 1), k=0.03, ends=False)
    S.mirror(lambda s: S.cone("Sternocleidomastoid", (s * 0.052, 1.6, -0.022), (s * 0.016, 1.452, 0.056), 0.014 * m, 0.012, k=0.016))
    S.mirror(lambda s: S.cone("Trapezius", (s * 0.03, 1.535, -0.03), (s * (sh - 0.03), 1.448, -0.012), 0.034 * m, 0.026, k=0.03, ends=False))
    S.ell("Trapezius", (0, 1.37, -0.07), (0.12 * m, 0.13, 0.04), fibre=(1, 0.4, 0), k=0.03)
    S.mirror(lambda s: S.cone("Clavicle", (s * 0.026, 1.456, 0.052), (s * (sh - 0.04), 1.462, 0.03), 0.0062, 0.007, k=0.018, tendon=0.6, ends=False))

    # ---- torso -------------------------------------------------------------------
    S.ell("Ribcage and intercostals", (0, 1.285, 0.0), (0.142 if not f else 0.128, 0.19, 0.1), fibre=(1, -0.3, 0), k=0.04)
    S.mirror(lambda s: S.ell("Pectoralis major", (s * 0.074, 1.338, 0.064), (0.083 * m, 0.062 * m, 0.04 * m), fibre=(s, 0.35, 0), k=0.03,
                             R=rot(z=s * 0.18)))
    S.mirror(lambda s: S.ell("Latissimus dorsi", (s * 0.118 * m, 1.235, -0.03), (0.055 * m, 0.14, 0.07), fibre=(-s * 0.35, 1, 0), k=0.035))
    S.mirror(lambda s: S.ell("Serratus anterior", (s * 0.112, 1.245, 0.045), (0.022, 0.05, 0.032), fibre=(s, -0.5, 0), k=0.03))
    S.ell("Rectus abdominis", (0, 1.115, 0.058), (0.078 * (0.9 if f else 1), 0.155, 0.045), fibre=(0, 1, 0), k=0.035)
    S.ell("Waist", (0, 1.07, -0.004), (waist, 0.12, 0.085), fibre=(1, 0, 0), k=0.045)
    S.mirror(lambda s: S.ell("External obliques", (s * (waist - 0.035), 1.07, 0.02), (0.042, 0.1, 0.065), fibre=(-s * 0.5, 1, 0.3), k=0.045))
    S.ell("Lower back", (0, 1.09, -0.06), (0.08, 0.12, 0.04), fibre=(0, 1, 0), k=0.03)
    if f:
        S.mirror(lambda s: S.ell("Breast tissue", (s * 0.066, 1.272, 0.082), (0.054, 0.05, 0.04), fibre=(s, 0.35, 0), k=0.05))

    # ---- pelvis --------------------------------------------------------------------
    S.ell("Pelvis", (0, 0.965, 0.0), (0.158 if f else 0.138, 0.085, 0.098 if f else 0.092), fibre=(1, 0, 0), k=0.045)
    S.mirror(lambda s: S.ell("Gluteus maximus", (s * (0.078 if f else 0.07), 0.925, -0.058), (0.082 if f else 0.075, 0.09, 0.065 if f else 0.06),
                             fibre=(s, -0.6, 0), k=0.035))
    S.ell("Groin", (0, 0.895, 0.04), (0.055, 0.05, 0.04), fibre=(0, 1, 0), k=0.04, tendon=0.0)

    # ---- arms (abducted a little, palms toward the thigh) --------------------------
    def arm(s):
        x0 = s * sh
        sho = (x0, 1.42, -0.005)
        elb = (s * (sh + 0.045), 1.14, -0.012)
        wri = (s * (sh + 0.075), 0.905, 0.02)
        S.ell("Deltoid", (s * (sh + 0.006), 1.405, 0.0), (0.058 * m, 0.08 * m, 0.064 * m), fibre=(s * 0.2, 1, 0), k=0.04)
        S.cone("Biceps brachii", (x0 + s * 0.012, 1.36, 0.022), (elb[0], 1.165, 0.018), 0.04 * m, 0.028 * m, k=0.025)
        S.cone("Triceps brachii", (x0 + s * 0.014, 1.37, -0.03), (elb[0], 1.16, -0.03), 0.043 * m, 0.03 * m, k=0.025)
        S.cone("Elbow", (elb[0], 1.16, -0.022), (elb[0], 1.125, -0.024), 0.026 * m, 0.026 * m, k=0.022, tendon=0.5, ends=False)
        S.cone("Brachioradialis", (elb[0] + s * 0.008, 1.16, 0.012), (wri[0], 0.97, 0.03), 0.032 * m, 0.02, k=0.022)
        S.cone("Forearm flexors", (elb[0] - s * 0.006, 1.12, 0.0), (wri[0], 0.915, 0.015), 0.036 * m, 0.021, k=0.022)
        S.cone("Wrist", (wri[0], 0.925, 0.02), (wri[0] + s * 0.004, 0.89, 0.022), 0.02, 0.019, k=0.016, tendon=0.6, ends=False)
        # hand: palm faces the body (thin in x)
        hx = wri[0] + s * 0.006
        S.ell("Hand", (hx, 0.838, 0.024), (0.017, 0.05, 0.041), fibre=(0, 1, 0), k=0.016, tendon=0.25)
        for i, dz in enumerate((-0.012, 0.004, 0.019, 0.033)):
            ln = (0.062, 0.07, 0.066, 0.052)[i]
            S.cone("Finger", (hx, 0.795, dz + 0.002), (hx - s * 0.006, 0.795 - ln, dz + 0.008), 0.0085, 0.0068, k=0.006, tendon=0.4, ends=False)
        S.cone("Finger", (hx - s * 0.004, 0.858, 0.052), (hx - s * 0.012, 0.81, 0.078), 0.011, 0.0085, k=0.008, tendon=0.4, ends=False)

    S.mirror(arm)

    # ---- legs -------------------------------------------------------------------------
    def leg(s):
        x = s * hip
        kx = s * (hip + 0.012)
        S.cone("Rectus femoris", (x, 0.88, 0.035), (kx, 0.545, 0.04), 0.062 * m, 0.04 * m, k=0.03)
        S.cone("Vastus lateralis", (x + s * 0.042, 0.84, 0.0), (kx + s * 0.02, 0.56, 0.012), 0.062 * m, 0.042 * m, k=0.03)
        S.ell("Vastus medialis", (kx - s * 0.03, 0.585, 0.03), (0.04 * m, 0.065 * m, 0.04 * m), fibre=(-s * 0.4, 1, 0), k=0.025)
        S.cone("Adductors", (x - s * 0.04, 0.88, -0.004), (kx - s * 0.03, 0.63, -0.004), 0.058 * m, 0.032, k=0.03)
        S.cone("Hamstrings", (x, 0.875, -0.042), (kx, 0.57, -0.035), 0.066 * m, 0.042 * m, k=0.03)
        S.ell("Patella", (kx, 0.505, 0.046), (0.024, 0.03, 0.016), k=0.016, tendon=0.95)
        S.cone("Knee", (kx, 0.53, 0.0), (kx + s * 0.002, 0.47, 0.0), 0.048 * m, 0.043 * m, k=0.03, tendon=0.12, ends=False)
        S.cone("Tibialis anterior", (kx + s * 0.012, 0.455, 0.028), (kx + s * 0.012, 0.13, 0.024), 0.032 * m, 0.02, k=0.02)
        S.ell("Gastrocnemius", (kx + s * 0.018, 0.365, -0.032), (0.046 * m, 0.1, 0.048 * m), fibre=(0, 1, 0), k=0.03)
        S.ell("Gastrocnemius", (kx - s * 0.016, 0.375, -0.032), (0.042 * m, 0.095, 0.046 * m), fibre=(0, 1, 0), k=0.03)
        S.cone("Soleus", (kx + s * 0.004, 0.41, -0.012), (kx + s * 0.01, 0.12, -0.02), 0.046 * m, 0.026, k=0.03)
        S.cone("Achilles tendon", (kx + s * 0.01, 0.15, -0.036), (kx + s * 0.01, 0.06, -0.04), 0.016, 0.017, k=0.015, tendon=1.0, ends=False)
        S.cone("Ankle", (kx + s * 0.01, 0.105, -0.004), (kx + s * 0.01, 0.06, -0.004), 0.03, 0.032, k=0.02, tendon=0.7, ends=False)
        S.ell("Foot", (kx + s * 0.012, 0.035, 0.04), (0.036, 0.032, 0.088), fibre=(0, 0, 1), k=0.025, tendon=0.45)
        S.ell("Foot", (kx + s * 0.016, 0.022, 0.118), (0.036, 0.018, 0.034), fibre=(0, 0, 1), k=0.02, tendon=0.55)

    S.mirror(leg)
    return S


def white_lines(p, n, region_names, sex):
    """Extra tendon/fascia marks painted on top of muscle: linea alba, ab inscriptions, shin, IT band, scalp."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    w = np.zeros(len(p))
    front = n[:, 2] > 0.25
    w += np.where(front & (np.abs(x) < 0.0055) & (y > 0.97) & (y < 1.37), 1.0, 0)            # linea alba
    for yy in (1.05, 1.115, 1.18):                                                            # ab inscriptions
        w += np.where(front & (np.abs(y - yy) < 0.0038) & (np.abs(x) < 0.068) & (z > 0.03), 0.9, 0)
    shin = np.isin(region_names, ["Tibialis anterior"])
    w += np.where(shin & (n[:, 2] > 0.55) & (np.abs(np.abs(x) - 0.088) < 0.0065), 0.9, 0)  # tibia edge
    lat = np.isin(region_names, ["Vastus lateralis"])
    w += np.where(lat & (np.abs(n[:, 0]) > 0.93) & (y > 0.62) & (y < 0.8), 0.45, 0)          # IT band
    w += np.where(np.isin(region_names, ["Head"]) & (y > 1.728), 0.8, 0)                     # galea aponeurosis
    return np.clip(w, 0, 1)
