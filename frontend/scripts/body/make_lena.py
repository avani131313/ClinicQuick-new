"""Lena: a smooth human head and shoulders (no lips, no cheek bulges), simplified to a low-poly mesh.
    python make_lena.py OUT_DIR   ->  OUT_DIR/lena-mesh.json {"v": [...], "t": [...], "jaw": [...], "eyes": [[x,y,z],[x,y,z]]}
Needs numpy, scikit-image and pyfqmr. Coordinates are centred and scaled (about -1..1), y up, face toward +z."""
import json, sys
from pathlib import Path
import numpy as np
from skimage.measure import marching_cubes
import pyfqmr
from sdf import Shape, rot, ellipsoid

def build():
    S = Shape()
    S.ell("head", (0, 1.665, -0.012), (0.071, 0.092, 0.09), k=0.02)              # cranium
    S.ell("head", (0, 1.615, 0.022), (0.058, 0.076, 0.066), k=0.035)             # face, smooth
    S.ell("head", (0, 1.562, 0.036), (0.04, 0.03, 0.036), k=0.035)               # chin
    S.ell("head", (0, 1.664, 0.068), (0.044, 0.01, 0.014), k=0.02)               # soft brow
    S.cone("head", (0, 1.648, 0.08), (0, 1.62, 0.09), 0.0075, 0.0105, k=0.014, ends=False)  # small nose
    S.mirror(lambda s: S.ell("head", (s * 0.069, 1.634, -0.008), (0.008, 0.022, 0.016), k=0.008))  # ears
    S.cone("neck", (0, 1.56, -0.012), (0, 1.45, -0.004), 0.037, 0.043, k=0.03, ends=False)
    S.ell("body", (0, 1.33, -0.012), (0.135, 0.165, 0.085), k=0.045)
    S.mirror(lambda s: S.ell("body", (s * 0.068, 1.345, 0.052), (0.074, 0.054, 0.032), k=0.035, R=rot(z=s * 0.18)))
    S.mirror(lambda s: S.cone("body", (s * 0.03, 1.465, -0.022), (s * 0.155, 1.43, -0.012), 0.029, 0.023, k=0.035, ends=False))
    S.mirror(lambda s: S.ell("body", (s * 0.182, 1.4, 0.0), (0.05, 0.066, 0.056), k=0.04))
    S.mirror(lambda s: S.cone("body", (s * 0.195, 1.37, 0.0), (s * 0.21, 1.2, -0.005), 0.042, 0.037, k=0.035))
    return S

def field(S, P):
    d = S.field(P)
    for s in (-1, 1):  # shallow eye sockets so the face reads, without big features
        sock = ellipsoid(P, (s * 0.029, 1.642, 0.078), (0.016, 0.009, 0.01))
        h = np.clip(0.5 - 0.5 * (d + sock) / 0.01, 0, 1)
        d = d * (1 - h) + (-sock) * h + 0.01 * h * (1 - h)
    return d

def main(out):
    S = build()
    h = 0.003
    lo, hi = np.array([-0.28, 1.22, -0.13]), np.array([0.28, 1.775, 0.13])
    xs, ys, zs = (np.arange(lo[i], hi[i], h) for i in range(3))
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    vol = np.concatenate([field(S, G[i:i + 300000]) for i in range(0, len(G), 300000)])
    v, f, _, _ = marching_cubes(vol.reshape(len(xs), len(ys), len(zs)), 0.0, spacing=(h, h, h))
    v += lo
    f = f[v[f][:, :, 1].min(1) > lo[1] + 0.004]          # drop the flat cut at the bottom of the bust
    simp = pyfqmr.Simplify()
    simp.setMesh(v, f)
    simp.simplify_mesh(target_count=2600, aggressiveness=6, preserve_border=True, verbose=0)
    v2, f2, _ = simp.getMesh()
    used = np.unique(f2); remap = -np.ones(len(v2), int); remap[used] = np.arange(len(used))
    v2, f2 = v2[used], remap[f2]
    c = v2[f2].mean(1)                                     # triangles face outward
    nf = np.cross(v2[f2[:, 1]] - v2[f2[:, 0]], v2[f2[:, 2]] - v2[f2[:, 0]])
    g = np.stack([field(S, c + d) - field(S, c - d) for d in np.eye(3) * 0.002], 1)
    flip = (nf * g).sum(1) < 0
    f2[flip] = f2[flip][:, [0, 2, 1]]
    c0, s = np.array([0, 1.48, 0]), 0.34
    q = (v2 - c0) / s
    jaw = ((v2[:, 1] < 1.585) & (v2[:, 1] > 1.53) & (v2[:, 2] > 0.0)).astype(int)
    eyes = [((np.array([sx * 0.029, 1.642, 0.072]) - c0) / s).round(4).tolist() for sx in (-1, 1)]
    data = {"v": np.round(q, 4).ravel().tolist(), "t": f2.ravel().astype(int).tolist(), "jaw": np.where(jaw)[0].tolist(), "eyes": eyes}
    o = Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "lena-mesh.json").write_text(json.dumps(data, separators=(",", ":")))
    print(len(v2), "verts", len(f2), "tris")

if __name__ == "__main__":
    main(sys.argv[1])
