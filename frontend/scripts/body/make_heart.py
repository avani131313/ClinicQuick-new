"""An anatomical heart (ventricles, atria, aorta and its arch branches, pulmonary trunk, venae cavae)
as a signed distance field, sampled into a point cloud for the landing page and the body figure.

    python make_heart.py OUT_DIR   ->  heart-points.json  {"points": [[x, y, z, region], ...], "regions": [...]}
Coordinates are centred and scaled to fit in [-1, 1]; y up, front toward +z.
"""
import json
import sys
from pathlib import Path

import numpy as np
from skimage.measure import marching_cubes

from sdf import Shape, rot

REG = ["muscle", "atrium", "artery", "pulmonary", "vein"]


def heart() -> Shape:
    S = Shape()
    S.ell("muscle", (0.06, -0.18, 0.02), (0.4, 0.6, 0.4), k=0.12, R=rot(z=-0.5))                 # left ventricle, apex down-left
    S.ell("muscle", (-0.16, -0.06, 0.2), (0.36, 0.5, 0.28), k=0.12, R=rot(z=-0.4))               # right ventricle
    S.ell("atrium", (0.2, 0.36, -0.16), (0.28, 0.21, 0.24), k=0.1)                                # left atrium
    S.ell("atrium", (0.4, 0.3, 0.08), (0.12, 0.08, 0.1), k=0.06)                                  # left auricle
    S.ell("atrium", (-0.36, 0.33, 0.0), (0.26, 0.28, 0.25), k=0.1)                                # right atrium
    S.ell("atrium", (-0.2, 0.5, 0.2), (0.12, 0.08, 0.1), k=0.06)                                  # right auricle
    S.cone("artery", (0.0, 0.34, 0.05), (-0.02, 0.85, 0.0), 0.14, 0.125, k=0.08)                  # ascending aorta
    S.cone("artery", (-0.02, 0.85, 0.0), (0.2, 0.98, -0.06), 0.125, 0.115, k=0.06)                # arch
    S.cone("artery", (0.2, 0.98, -0.06), (0.36, 0.84, -0.13), 0.115, 0.11, k=0.06)
    S.cone("artery", (0.36, 0.84, -0.13), (0.4, 0.35, -0.2), 0.11, 0.1, k=0.06)                   # descending
    S.cone("artery", (0.04, 0.95, -0.01), (0.0, 1.22, 0.01), 0.05, 0.042, k=0.04)                 # brachiocephalic
    S.cone("artery", (0.15, 1.0, -0.05), (0.16, 1.24, -0.05), 0.042, 0.036, k=0.04)               # left common carotid
    S.cone("artery", (0.26, 0.95, -0.09), (0.32, 1.19, -0.09), 0.045, 0.038, k=0.04)              # left subclavian
    S.cone("pulmonary", (-0.08, 0.28, 0.3), (0.1, 0.7, 0.22), 0.13, 0.11, k=0.08)                 # pulmonary trunk
    S.cone("pulmonary", (0.1, 0.7, 0.22), (0.48, 0.72, 0.06), 0.085, 0.07, k=0.05)                # left pulmonary artery
    S.cone("pulmonary", (0.1, 0.7, 0.22), (-0.22, 0.76, 0.04), 0.08, 0.07, k=0.05)                # right pulmonary artery
    S.cone("vein", (-0.4, 0.5, -0.04), (-0.4, 1.08, -0.06), 0.1, 0.095, k=0.06)                   # superior vena cava
    S.cone("vein", (-0.32, 0.1, -0.12), (-0.32, -0.36, -0.16), 0.1, 0.095, k=0.06)                # inferior vena cava
    return S


def main(out: Path, n=1400, seed=3):
    S = heart()
    h = 0.012
    lo, hi = np.array([-0.9, -0.85, -0.6]), np.array([0.9, 1.35, 0.7])
    xs, ys, zs = (np.arange(lo[i], hi[i], h) for i in range(3))
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    vol = S.field(G).reshape(len(xs), len(ys), len(zs))
    v, f, _, _ = marching_cubes(vol, 0.0, spacing=(h, h, h))
    v += lo
    # area-weighted surface sample
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    rng = np.random.default_rng(seed)
    tri = rng.choice(len(f), n, p=area / area.sum())
    u, w = rng.random(n), rng.random(n)
    flip = u + w > 1
    u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
    pts = a[tri] * (1 - u - w)[:, None] + b[tri] * u[:, None] + c[tri] * w[:, None]
    reg = np.array([REG.index(S.prims[i]["region"]) for i in S.nearest(pts)])
    ctr = (pts.max(0) + pts.min(0)) / 2
    pts = (pts - ctr) / (np.abs(pts - ctr).max())
    data = {"regions": REG, "points": [[round(float(x), 3), round(float(y), 3), round(float(z), 3), int(r)] for (x, y, z), r in zip(pts, reg)]}
    (out / "heart-points.json").write_text(json.dumps(data, separators=(",", ":")))
    print("heart:", n, "points", {r: int((reg == i).sum()) for i, r in enumerate(REG)})


if __name__ == "__main__":
    o = Path(sys.argv[1]); o.mkdir(parents=True, exist_ok=True)
    main(o)
