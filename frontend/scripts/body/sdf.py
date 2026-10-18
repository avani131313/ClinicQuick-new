"""Small signed-distance-field toolkit (numpy, vectorised over point arrays)."""
import numpy as np


def length(v):
    return np.sqrt(np.sum(v * v, axis=-1))


def ellipsoid(p, c, r, R=None):
    q = p - np.asarray(c, float)
    if R is not None:
        q = q @ R
    r = np.asarray(r, float)
    k0 = length(q / r)
    k1 = length(q / (r * r))
    return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -np.min(r))


def round_cone(p, a, b, r1, r2):
    """iq's round cone: capsule whose radius goes from r1 at a to r2 at b."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    x = pa * l2 - y[:, None] * ba
    x2 = np.sum(x * x, axis=1)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d1 = np.sqrt(x2 + z2) * il2 - r2
    d2 = np.sqrt(x2 + y2) * il2 - r1
    d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))


def axis_t(p, a, b):
    """0 at a, 1 at b: where each point sits along a segment."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    ba = b - a
    return np.clip(((p - a) @ ba) / float(ba @ ba), 0, 1)


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def rot(x=0.0, y=0.0, z=0.0):
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


class Shape:
    """A list of primitives, each tagged with a region name, fibre direction and tendon settings."""

    def __init__(self):
        self.prims = []

    def ell(self, region, c, r, fibre=(0, 1, 0), k=0.022, tendon=0.0, R=None):
        self.prims.append(dict(kind="ell", region=region, c=np.array(c, float), r=np.array(r, float), R=R,
                               fibre=np.array(fibre, float), k=k, tendon=tendon, ends=False))

    def cone(self, region, a, b, r1, r2, k=0.022, tendon=0.0, ends=True, fibre=None):
        a = np.array(a, float); b = np.array(b, float)
        f = (b - a) / np.linalg.norm(b - a) if fibre is None else np.array(fibre, float)
        self.prims.append(dict(kind="cone", region=region, a=a, b=b, r1=r1, r2=r2, fibre=f, k=k, tendon=tendon, ends=ends))

    def mirror(self, fn):
        fn(1.0)
        fn(-1.0)

    def prim_d(self, pr, p):
        if pr["kind"] == "ell":
            return ellipsoid(p, pr["c"], pr["r"], pr["R"])
        return round_cone(p, pr["a"], pr["b"], pr["r1"], pr["r2"])

    def field(self, p):
        d = None
        for pr in self.prims:
            di = self.prim_d(pr, p)
            d = di if d is None else smin(d, di, pr["k"])
        return d

    def nearest(self, p):
        best = np.full(len(p), np.inf)
        idx = np.zeros(len(p), int)
        for i, pr in enumerate(self.prims):
            di = self.prim_d(pr, p)
            m = di < best
            best[m] = di[m]
            idx[m] = i
        return idx
