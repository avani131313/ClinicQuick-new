"""Build the male and female anatomy meshes and write them as compact binaries for the web app.

    python make_body.py OUT_DIR

Output per sex: body-<sex>.bin
  header: b"CQB2", u32 vertCount, u32 triCount, f32[3] min, f32[3] max
  u16[3*V] positions (quantised to the box), i16[2*V] striation coords (/8000), i8[3*V] normals, i8[3*V] fibre directions,
  u8[4*V] (region index, tendon 0-255, ambient occlusion 0-255, 0), padding to 4, u32[3*T] indices
and body-regions.json with the region names (index -> name), shared by both sexes.
"""
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
from skimage.measure import marching_cubes

import body
from sdf import axis_t

REGIONS = ["Head", "Face", "Ear", "Eye", "Neck", "Sternocleidomastoid", "Trapezius", "Clavicle", "Ribcage and intercostals",
           "Pectoralis major", "Latissimus dorsi", "Serratus anterior", "Rectus abdominis", "Waist", "External obliques",
           "Lower back", "Breast tissue", "Pelvis", "Gluteus maximus", "Groin", "Deltoid", "Biceps brachii", "Triceps brachii",
           "Elbow", "Brachioradialis", "Forearm flexors", "Wrist", "Hand", "Finger", "Rectus femoris", "Vastus lateralis",
           "Vastus medialis", "Adductors", "Hamstrings", "Patella", "Knee", "Tibialis anterior", "Gastrocnemius", "Soleus",
           "Achilles tendon", "Ankle", "Foot"]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def build(sex, out: Path, h=0.0068):
    t0 = time.time()
    S = body.build(sex)
    lo = np.array([-0.33, -0.015, -0.16]); hi = np.array([0.33, 1.785, 0.19])
    xs = np.arange(lo[0], hi[0], h); ys = np.arange(lo[1], hi[1], h); zs = np.arange(lo[2], hi[2], h)
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    vol = np.empty(len(G), np.float32)
    for i in range(0, len(G), 400_000):
        vol[i:i + 400_000] = S.field(G[i:i + 400_000])
    vol = vol.reshape(len(xs), len(ys), len(zs))
    verts, faces, _, _ = marching_cubes(vol, level=0.0, spacing=(h, h, h))
    verts += lo
    # normals from the field gradient (smoother than the voxel ones)
    e = 0.0015
    g = np.stack([S.field(verts + d) - S.field(verts - d) for d in (np.array([e, 0, 0]), np.array([0, e, 0]), np.array([0, 0, e]))], -1)
    n = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
    # region + fibre + tendon from the nearest primitive
    near = S.nearest(verts)
    names = np.array([S.prims[i]["region"] for i in near])
    # Eye and breast tissue get ids far from the rest, so values interpolated across a seam never hit them
    SPECIAL = {"Eye": 254, "Breast tissue": 253}
    rid = np.array([SPECIAL.get(nm, REGIONS.index(nm)) for nm in names], np.uint8)
    fib = np.stack([S.prims[i]["fibre"] for i in near])
    fib = fib - n * np.sum(fib * n, 1, keepdims=True)
    fib /= np.maximum(np.linalg.norm(fib, axis=1, keepdims=True), 1e-9)
    tend = np.array([S.prims[i]["tendon"] for i in near], float)
    for i, pr in enumerate(S.prims):
        if pr["kind"] == "cone" and pr["ends"]:
            m = near == i
            if m.any():
                tt = axis_t(verts[m], pr["a"], pr["b"])
                tend[m] = np.maximum(tend[m], smoothstep(0.8, 0.97, tt) * 0.9)
    tend = np.maximum(tend, body.white_lines(verts, n, names, sex))
    # striation coordinates: arc length around each muscle's own fibre axis (stripes run along the muscle)
    st = np.zeros((len(verts), 2))
    for i, pr in enumerate(S.prims):
        msk = near == i
        if not msk.any():
            continue
        if pr["kind"] == "cone":
            fa = (pr["b"] - pr["a"]); fa = fa / np.linalg.norm(fa); org = pr["a"]; rad = (pr["r1"] + pr["r2"]) / 2
        else:
            fa = pr["fibre"] / np.linalg.norm(pr["fibre"]); org = pr["c"]; rad = float(np.mean(pr["r"]))
        e1 = np.cross(fa, [0, 0, 1.0])
        if np.linalg.norm(e1) < 0.2:
            e1 = np.cross(fa, [1.0, 0, 0])
        e1 /= np.linalg.norm(e1); e2 = np.cross(fa, e1)
        d = verts[msk] - org
        st[msk, 0] = np.arctan2(d @ e2, d @ e1) * rad
        st[msk, 1] = d @ fa
    # ambient occlusion from the field
    occ = np.zeros(len(verts))
    for k, d in enumerate((0.006, 0.014, 0.028, 0.05)):
        occ += np.maximum(0, d - S.field(verts + n * d)) / d * (0.5 ** k)
    ao = np.clip(1 - occ * 0.9, 0, 1)
    # soften region edges: average tendon + AO with mesh neighbours (marching-cubes steps disappear)
    from scipy.sparse import coo_matrix, diags
    i0 = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 1], faces[:, 2], faces[:, 0]])
    i1 = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0], faces[:, 0], faces[:, 1], faces[:, 2]])
    A = coo_matrix((np.ones(len(i0)), (i0, i1)), shape=(len(verts), len(verts))).tocsr()
    A.data[:] = 1
    Dinv = diags(1 / np.maximum(np.asarray(A.sum(1)).ravel(), 1))
    W = Dinv @ A
    for _ in range(3):
        tend = 0.5 * tend + 0.5 * (W @ tend)
        ao = 0.5 * ao + 0.5 * (W @ ao)
    # write
    vmin, vmax = verts.min(0), verts.max(0)
    q = np.round((verts - vmin) / (vmax - vmin) * 65535).astype(np.uint16)
    nb = np.round(n * 127).astype(np.int8)
    fb = np.round(fib * 127).astype(np.int8)
    attr = np.stack([rid, np.round(tend * 255).astype(np.uint8), np.round(ao * 255).astype(np.uint8), np.zeros(len(rid), np.uint8)], 1)
    sq = np.clip(np.round(st * 8000), -32767, 32767).astype(np.int16)
    parts = [b"CQB2", struct.pack("<II", len(verts), len(faces)), struct.pack("<6f", *vmin, *vmax),
             q.tobytes(), sq.tobytes(), nb.tobytes(), fb.tobytes(), attr.tobytes()]
    blob = b"".join(parts)
    blob += b"\0" * ((4 - len(blob) % 4) % 4)
    blob += faces.astype(np.uint32).tobytes()
    (out / f"body-{sex}.bin").write_bytes(blob)
    print(f"{sex}: {len(verts):,} verts, {len(faces):,} tris, {len(blob) / 1e6:.2f} MB, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for sex in sys.argv[2:] or ["male", "female"]:
        build(sex, out)
    (out / "body-regions.json").write_text(json.dumps(REGIONS))
