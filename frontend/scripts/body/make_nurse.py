"""Lena, the voice assistant: a nurse's head and shoulders (hair in a bun, nurse cap with a cross,
scrubs with a V-neck, stethoscope) as a point cloud.

    python make_nurse.py OUT_DIR  ->  nurse-points.json  {"points": [[x, y, z, region], ...], "regions": [...]}
Eyes, mouth and the cross are separate point groups so the app can animate them (blink, talk, glow).
Coordinates are centred and scaled to [-1, 1]; y up, face toward +z.
"""
import json
import sys
from pathlib import Path

import numpy as np
from skimage.measure import marching_cubes

from sdf import Shape, rot

REG = ["skin", "hair", "cap", "cross", "scrubs", "trim", "stethoscope", "eye", "mouth", "brow"]


def figure() -> Shape:
    S = Shape()
    S.ell("skin", (0, 0.56, 0.0), (0.235, 0.3, 0.26), k=0.05)                               # cranium
    S.ell("skin", (0, 0.42, 0.06), (0.17, 0.15, 0.17), k=0.08)                              # jaw
    S.ell("skin", (0, 0.33, 0.1), (0.07, 0.05, 0.06), k=0.05)                               # chin
    S.cone("skin", (0, 0.56, 0.24), (0, 0.48, 0.29), 0.022, 0.03, k=0.03, ends=False)       # nose
    S.mirror(lambda s: S.ell("skin", (s * 0.235, 0.52, -0.01), (0.03, 0.06, 0.04), k=0.02)) # ears
    S.ell("hair", (0, 0.62, -0.05), (0.255, 0.3, 0.27), k=0.03)                              # hair shell
    S.ell("hair", (0, 0.66, -0.31), (0.12, 0.11, 0.1), k=0.06)                               # bun
    S.ell("cap", (0, 0.86, 0.02), (0.2, 0.075, 0.15), k=0.04, R=rot(x=0.35))                 # nurse cap
    S.cone("skin", (0, 0.32, -0.02), (0, 0.04, -0.01), 0.082, 0.1, k=0.05, ends=False)      # neck
    S.ell("scrubs", (0, -0.32, -0.02), (0.46, 0.4, 0.21), k=0.12)                            # torso
    S.mirror(lambda s: S.ell("scrubs", (s * 0.33, -0.02, -0.02), (0.15, 0.1, 0.13), k=0.14, R=rot(z=s * 0.35)))  # shoulders
    S.mirror(lambda s: S.cone("scrubs", (s * 0.42, -0.1, -0.02), (s * 0.5, -0.9, 0.0), 0.12, 0.1, k=0.1))  # upper arms
    # stethoscope around the neck
    S.mirror(lambda s: S.cone("stethoscope", (s * 0.11, 0.1, -0.07), (s * 0.17, 0.0, 0.12), 0.014, 0.014, k=0.0, ends=False))
    S.mirror(lambda s: S.cone("stethoscope", (s * 0.17, 0.0, 0.12), (s * 0.12, -0.36, 0.19), 0.014, 0.014, k=0.0, ends=False))
    S.cone("stethoscope", (0.12, -0.36, 0.19), (0.15, -0.52, 0.2), 0.012, 0.012, k=0.0, ends=False)
    S.ell("stethoscope", (0.15, -0.56, 0.205), (0.042, 0.042, 0.02), k=0.0)                    # chest piece
    return S


def surface(S, h=0.012):
    lo, hi = np.array([-0.85, -0.95, -0.5]), np.array([0.85, 1.0, 0.45])
    xs, ys, zs = (np.arange(lo[i], hi[i], h) for i in range(3))
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    vol = S.field(G).reshape(len(xs), len(ys), len(zs))
    v, f, n, _ = marching_cubes(vol, 0.0, spacing=(h, h, h))
    return v + lo, f


def sample(v, f, n, rng, weight):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2 * weight((a + b + c) / 3)
    tri = rng.choice(len(f), n, p=area / area.sum())
    u, w = rng.random(n), rng.random(n)
    flip = u + w > 1
    u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
    return a[tri] * (1 - u - w)[:, None] + b[tri] * u[:, None] + c[tri] * w[:, None]


def main(out: Path, n=3600, seed=11):
    S = figure()
    v, f = surface(S)
    rng = np.random.default_rng(seed)
    # denser on the face, sparser where the bust fades out
    def weight(p):
        face = np.exp(-((p[:, 1] - 0.55) ** 2) / 0.05) * (p[:, 2] > 0.0)
        fade = np.clip((p[:, 1] + 0.9) / 0.6, 0.08, 1)
        return (1 + 3.0 * face) * fade
    pts = sample(v, f, n, rng, weight)
    pts = pts[(pts[:, 2] > -0.42) & (pts[:, 1] > -0.8)]
    near = S.nearest(pts)
    reg = np.array([REG.index(S.prims[i]["region"]) for i in near])
    x, y, z = pts.T
    # hairline: hair covers the face only above the brow, and the sides behind the ears
    is_hair = reg == REG.index("hair")
    face_front = (z > 0.1) & (y < 0.7) & (np.abs(x) < 0.19)
    reg[is_hair & face_front] = REG.index("skin")
    # V-neck trim and collar on the scrubs
    sc = reg == REG.index("scrubs")
    vline = np.abs(np.abs(x) - (0.02 + (0.1 - y) * 0.42)) < 0.028
    reg[sc & vline & (z > 0.05) & (y < 0.06) & (y > -0.42)] = REG.index("trim")
    reg[sc & (np.abs(x) < (0.02 + (0.1 - y) * 0.42) - 0.028) & (z > 0.05) & (y > -0.4)] = REG.index("skin")  # skin inside the V

    feats = []
    def front(px, py):  # project a point onto the face surface along +z
        zz = np.linspace(0.45, 0.0, 200)
        P = np.stack([np.full_like(zz, px), np.full_like(zz, py), zz], 1)
        d = S.field(P)
        return zz[np.argmax(d < 0)] + 0.006
    for sgn in (-1, 1):  # eyes: almond outline + iris
        cx, cy = sgn * 0.085, 0.585
        for t in np.linspace(0, 2 * np.pi, 34, endpoint=False):
            ex, ey = cx + 0.045 * np.cos(t), cy + 0.018 * np.sin(t) * (1.2 if np.sin(t) > 0 else 0.8)
            feats.append([ex, ey, front(ex, ey), REG.index("eye")])
        for rr, k in ((0.016, 14), (0.007, 7)):
            for t in np.linspace(0, 2 * np.pi, k, endpoint=False):
                ex, ey = cx + rr * np.cos(t), cy + rr * np.sin(t)
                feats.append([ex, ey, front(ex, ey) + 0.004, REG.index("eye")])
        for t in np.linspace(-1, 1, 16):  # brows
            bx, by = cx + t * 0.05, 0.64 + 0.012 * (1 - t * t) - 0.004 * t * sgn
            feats.append([bx, by, front(bx, by), REG.index("brow")])
    for t in np.linspace(-1, 1, 30):  # mouth: upper and lower lip lines
        mx = t * 0.06
        feats.append([mx, 0.43 - 0.006 * (1 - t * t), front(mx, 0.43), REG.index("mouth")])
        feats.append([mx, 0.425 - 0.016 * (1 - t * t), front(mx, 0.42), REG.index("mouth")])
    # the red cross on the cap front
    capf = lambda px, py: (px, py, front(px, py))
    for i in range(70):
        u = rng.uniform(-1, 1); w = rng.uniform(-1, 1) * 0.28
        px, py = (u * 0.05, 0.86 + w * 0.05) if i % 2 else (w * 0.05, 0.86 + u * 0.05)
        feats.append([*capf(px, py), REG.index("cross")])
    allp = np.vstack([np.column_stack([pts, reg]), np.array(feats)])
    xyz = allp[:, :3]
    ctr = (xyz.max(0) + xyz.min(0)) / 2
    s = np.abs(xyz - ctr).max()
    xyz = (xyz - ctr) / s
    data = {"regions": REG, "points": [[round(float(a), 3), round(float(b), 3), round(float(c), 3), int(r)] for (a, b, c), r in zip(xyz, allp[:, 3])]}
    (out / "nurse-points.json").write_text(json.dumps(data, separators=(",", ":")))
    print("nurse:", len(allp), "points", {r: int((allp[:, 3] == i).sum()) for i, r in enumerate(REG)})


if __name__ == "__main__":
    o = Path(sys.argv[1]); o.mkdir(parents=True, exist_ok=True)
    main(o)
