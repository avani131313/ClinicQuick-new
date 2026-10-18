"""
prepare.py — FIXED harness for the DDX autoresearch loop. The agent must NOT edit this file.

  python prepare.py                         # pull ddx.patients from Tiger once, build the cache in data/
  python prepare.py log "<change>" keep     # log the last run (keep | discard | crash)
  python prepare.py final                   # ONE-TIME locked test-set evaluation (human only)

The task: given age, sex and symptom/history answers (DDXPlus evidence codes), rank 59 conditions.

PRIMARY METRIC  top3_short = macro recall@3 after a SHORT interview: the patient's history (antecedents),
                the opening complaint, and about 30% of the remaining symptom questions. That is what Lena
                knows a few questions in. Macro = every condition counts equally (the 10 demo conditions too).
Also reported:  top1/top5 after the short interview, top1_full (all answers), ddr5 (overlap with the
                DDXPlus reference differential), recall@3 per sex and age band (fairness guardrail), and
                per data source.
"""
import json
import os
import pickle
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

TIME_BUDGET = 90          # seconds of training per experiment (wall clock)
K = 3                     # primary metric: is the true condition in the top 3?
KEEP_FRACTION = 0.3       # short interview: share of non-opening symptom questions that were asked
MIN_TOKEN_COUNT = 5       # answer codes seen fewer times than this in train are dropped
SEED = 42

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RESULTS_TSV = os.path.join(HERE, "results.tsv")
LAST_RUN = os.path.join(DATA, "last_run.json")
LAST_MODEL = os.path.join(DATA, "last_model.pkl")
AGE_BANDS = [(-1, 17, "0-17"), (18, 39, "18-39"), (40, 64, "40-64"), (65, 200, "65+")]


# ------------------------------------------------------------------ database
def database_url():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path) and "DATABASE_URL" not in os.environ:
        for line in open(path, encoding="utf-8"):
            if line.strip().startswith("DATABASE_URL="):
                os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("DATABASE_URL")


def connect():
    import psycopg2
    url = database_url()
    if not url:
        sys.exit("DATABASE_URL not set. Put DATABASE_URL=postgres://... in a .env file in this folder.")
    return psycopg2.connect(url)


# ------------------------------------------------------------------ features
def _meta():
    return json.load(open(os.path.join(DATA, "meta.json"), encoding="utf-8"))


def tokens_of(evidences, numeric_codes):
    """'E_55_@_V_187' -> binary token; 'E_56_@_6' -> numeric feature E_56=6; 'E_302' -> binary token."""
    binary, numeric = [], {}
    for e in evidences:
        if "_@_" in e:
            base, val = e.split("_@_", 1)
            if base in numeric_codes:
                try:
                    numeric[base] = float(val)
                    continue
                except ValueError:
                    pass
        binary.append(e)
    return binary, numeric


def col(token):
    return token.replace("_@_", "__")


def featurize(raw, meta=None):
    """raw: DataFrame with AGE, SEX, EVIDENCES (list of codes). Returns the model's input DataFrame.
    Public helper: train.py may call it (e.g. on masked copies of the training data)."""
    meta = meta or _meta()
    vocab, numeric_codes = meta["vocab"], set(meta["numeric_codes"])
    index = {t: i for i, t in enumerate(vocab)}
    B = np.zeros((len(raw), len(vocab)), dtype=np.int8)
    N = np.full((len(raw), len(meta["numeric_codes"])), np.nan, dtype=np.float32)
    nidx = {c: i for i, c in enumerate(meta["numeric_codes"])}
    for r, evs in enumerate(raw["EVIDENCES"]):
        binary, numeric = tokens_of(evs, numeric_codes)
        for t in binary:
            j = index.get(t)
            if j is not None:
                B[r, j] = 1
        for c, v in numeric.items():
            N[r, nidx[c]] = v
    X = pd.DataFrame(B, columns=[col(t) for t in vocab])
    for c, i in nidx.items():
        X[c] = N[:, i]
    X.insert(0, "SEX", pd.Categorical(raw["SEX"].values, categories=["F", "M"]))
    X.insert(0, "AGE", raw["AGE"].values.astype(np.float32))
    return X


def mask(raw, keep=KEEP_FRACTION, seed=0, meta=None):
    """Simulate a partial interview: keep history answers + the opening complaint, and each other
    symptom QUESTION (all its answers together) with probability `keep`. Public helper for train.py."""
    meta = meta or _meta()
    antecedent = set(meta["antecedent_codes"])
    rng = np.random.default_rng(seed)
    out = []
    for evs, init in zip(raw["EVIDENCES"], raw["INITIAL_EVIDENCE"]):
        questions = sorted({e.split("_@_")[0] for e in evs} - antecedent - {init})
        kept_q = {q for q in questions if rng.random() < keep} | antecedent | {init}
        out.append([e for e in evs if e.split("_@_")[0] in kept_q])
    raw = raw.copy()
    raw["EVIDENCES"] = out
    return raw


# ------------------------------------------------------------------ cache
def build_cache():
    t0 = time.time()
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM ddx.conditions ORDER BY name")
    labels = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT code, data_type, is_antecedent, answer_values FROM ddx.evidences")
    ev = cur.fetchall()
    numeric_codes = sorted(c for c, t, a, v in ev if t == "C" and not v)
    antecedent_codes = sorted(c for c, t, a, v in ev if a)

    print("pulling ddx.patients from Tiger ...")
    named = conn.cursor(name="pull")  # server-side cursor: streams rows instead of loading all at once
    named.itersize = 20000
    named.execute("SELECT split, source, age, sex, pathology, initial_evidence, evidences, differential FROM ddx.patients")
    rows = named.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["SPLIT", "SOURCE", "AGE", "SEX", "PATHOLOGY", "INITIAL_EVIDENCE",
                                     "EVIDENCES", "DIFFERENTIAL"])
    unknown = set(df.PATHOLOGY) - set(labels)
    if unknown:
        sys.exit(f"Pathologies missing from ddx.conditions: {sorted(unknown)[:5]}")
    print(f"  {len(df):,} patients in {time.time() - t0:.1f}s")

    train = df[df.SPLIT == "train"]
    counts = pd.Series([t for evs in train.EVIDENCES for t in tokens_of(evs, set(numeric_codes))[0]]).value_counts()
    vocab = sorted(counts[counts >= MIN_TOKEN_COUNT].index)
    meta = {"labels": labels, "vocab": vocab, "numeric_codes": numeric_codes,
            "antecedent_codes": antecedent_codes, "keep_fraction": KEEP_FRACTION}
    os.makedirs(DATA, exist_ok=True)
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8"))

    lab = {n: i for i, n in enumerate(labels)}
    for split in ["train", "val", "test"]:
        part = df[df.SPLIT == split].reset_index(drop=True)
        raw = part[["AGE", "SEX", "EVIDENCES", "INITIAL_EVIDENCE"]]
        d = {"raw": raw, "y": part.PATHOLOGY.map(lab).values, "labels": labels,
             "X_full": featurize(raw, meta),
             "groups": pd.DataFrame({
                 "sex": part.SEX.values,
                 "age": [next(n for lo, hi, n in AGE_BANDS if lo <= a <= hi) for a in part.AGE],
                 "source": part.SOURCE.values}),
             "ref_top5": [[x[0] for x in (dd or [])[:5]] for dd in part.DIFFERENTIAL]}
        if split != "train":
            d["X_short"] = featurize(mask(raw, seed=SEED + (1 if split == "val" else 2), meta=meta), meta)
        pickle.dump(d, open(os.path.join(DATA, f"{split}.pkl"), "wb"))
        print(f"  {split:5s}: {len(part):7,} patients")
    print(f"features: {len(vocab)} answer codes + {len(numeric_codes)} numeric + age, sex")
    print(f"cache written to {DATA} ({time.time() - t0:.1f}s)")


def _load(name):
    if name == "test" and os.environ.get("_ALLOW_TEST") != "1":
        raise PermissionError("The test split is locked. The human runs `python prepare.py final`.")
    return pickle.load(open(os.path.join(DATA, f"{name}.pkl"), "rb"))


def load_split(name="train"):
    """Returns (X, y, labels): full-evidence features, integer labels, the 59 condition names."""
    d = _load(name)
    return d["X_full"], d["y"], d["labels"]


def load_raw(name="train"):
    """Returns the raw DataFrame (AGE, SEX, EVIDENCES, INITIAL_EVIDENCE) and y, e.g. for augmentation."""
    d = _load(name)
    return d["raw"], d["y"]


# ------------------------------------------------------------------ metric
def evaluate(predict_fn, split="val", train_seconds=None, quiet=False):
    d = _load(split)
    y, labels, n_cls = d["y"], d["labels"], len(d["labels"])
    res = {"split": split, "time": datetime.now(timezone.utc).isoformat()}
    sp = np.asarray(predict_fn(d["X_short"]), dtype=float)
    sf = np.asarray(predict_fn(d["X_full"]), dtype=float)
    assert sp.shape == (len(y), n_cls), f"predict must return shape {(len(y), n_cls)}, got {sp.shape}"

    order = np.argsort(-sp, axis=1)
    hit_p = (order[:, :K] == y[:, None]).any(1)
    present = np.unique(y)
    per_class = {labels[c]: float(hit_p[y == c].mean()) for c in present}
    res["top3_short"] = float(np.mean(list(per_class.values())))             # PRIMARY (macro over conditions)
    res["top1_short"] = float((order[:, 0] == y).mean())
    res["top5_short"] = float((order[:, :5] == y[:, None]).any(1).mean())
    top_f = np.argsort(-sf, axis=1)[:, :5]
    res["top1_full"] = float((top_f[:, 0] == y).mean())
    res["top5_full"] = float((top_f == y[:, None]).any(1).mean())
    ddr = [len(set(labels[j] for j in top_f[i]) & set(ref)) / len(ref)
           for i, ref in enumerate(d["ref_top5"]) if ref]
    res["ddr5"] = float(np.mean(ddr)) if ddr else 0.0

    g = d["groups"]
    sub = {}
    for gcol in ["sex", "age"]:
        for val in sorted(g[gcol].unique()):
            m = (g[gcol] == val).values
            if m.sum() >= 30:
                sub[f"{gcol}={val}"] = (float(hit_p[m].mean()), int(m.sum()))
    worst = min(sub, key=lambda s: sub[s][0])
    res.update(worst_subgroup=sub[worst][0], worst_subgroup_name=worst, subgroups=sub,
               by_source={s: float(hit_p[(g.source == s).values].mean()) for s in sorted(g.source.unique())},
               train_seconds=train_seconds,
               over_budget=bool(train_seconds is not None and train_seconds > TIME_BUDGET * 1.1))
    if not quiet:
        print("---")
        print(f"top3_short:     {res['top3_short']:.4f}      <- PRIMARY (higher is better)")
        print(f"top1_short:     {res['top1_short']:.4f}")
        print(f"top5_short:     {res['top5_short']:.4f}")
        print(f"top1_full:      {res['top1_full']:.4f}")
        print(f"top5_full:      {res['top5_full']:.4f}")
        print(f"ddr5:           {res['ddr5']:.4f}   (overlap with DDXPlus reference differential)")
        print(f"worst_subgroup: {res['worst_subgroup']:.4f}  ({worst})")
        if train_seconds is not None:
            print(f"train_seconds:  {train_seconds:.1f}" + ("  ** OVER BUDGET - INVALID **" if res["over_budget"] else ""))
        print("subgroups (recall@3, short interview):")
        for s, (v, n) in sub.items():
            print(f"  {s:12s} {v:.4f}  (n={n})")
        print("by data source:", ", ".join(f"{s}={v:.4f}" for s, v in res["by_source"].items()))
        print("weakest conditions (recall@3, short interview):")
        for name, r in sorted(per_class.items(), key=lambda x: x[1])[:12]:
            print(f"  {r:.3f}  {name}")
    if split == "val":
        json.dump(res, open(LAST_RUN, "w", encoding="utf-8"), indent=1)
    return res


def run_experiment(fit, predict):
    """Called by train.py: fit within the time budget, save the model, score it on val."""
    X, y, labels = load_split("train")
    t0 = time.time()
    model = fit(X, y, deadline=t0 + TIME_BUDGET)
    secs = time.time() - t0
    pickle.dump({"model": model, "labels": labels}, open(LAST_MODEL, "wb"))
    return evaluate(lambda x: predict(model, x), split="val", train_seconds=secs)


# ------------------------------------------------------------------ logging
def log_last_run(change, status):
    assert status in ("keep", "discard", "crash"), "status must be keep | discard | crash"
    r = json.load(open(LAST_RUN, encoding="utf-8")) if (os.path.exists(LAST_RUN) and status != "crash") else {}
    n = sum(1 for _ in open(RESULTS_TSV, encoding="utf-8")) if os.path.exists(RESULTS_TSV) else 0
    if n == 0:
        open(RESULTS_TSV, "w", encoding="utf-8").write(
            "experiment\ttime\ttop3_short\ttop1_full\tddr5\tworst_subgroup\tstatus\tchange\n")
        n = 1
    exp = f"exp{n:03d}"
    row = [exp, datetime.now(timezone.utc).isoformat(timespec="seconds")] + \
          [f"{r.get(k, 0):.4f}" for k in ("top3_short", "top1_full", "ddr5", "worst_subgroup")] + \
          [status, change.replace("\t", " ")]
    open(RESULTS_TSV, "a", encoding="utf-8").write("\t".join(row) + "\n")
    print(f"logged {exp} to results.tsv")
    try:  # mirror to Tiger for the live dashboard; never block the loop on it
        conn = connect()
        with conn, conn.cursor() as c:
            c.execute("INSERT INTO ddx.results (experiment, change, status, top3_short, top1_full, ddr5, "
                      "worst_subgroup, worst_subgroup_name, train_seconds) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (exp, change, status, r.get("top3_short"), r.get("top1_full"), r.get("ddr5"),
                       r.get("worst_subgroup"), r.get("worst_subgroup_name"), r.get("train_seconds")))
        conn.close()
        print("logged to Tiger ddx.results")
    except Exception as ex:
        print(f"(Tiger logging skipped: {ex.__class__.__name__}: {str(ex).splitlines()[0][:100]})")


def final():
    import train
    os.environ["_ALLOW_TEST"] = "1"
    X, y, labels = load_split("train")
    t0 = time.time()
    model = train.fit(X, y, deadline=t0 + TIME_BUDGET)
    print("=== LOCKED TEST SET ===")
    evaluate(lambda x: train.predict(model, x), split="test", train_seconds=time.time() - t0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        build_cache()
    elif a[0] == "log":
        log_last_run(a[1], a[2])
    elif a[0] == "final":
        final()
    else:
        print(__doc__)
