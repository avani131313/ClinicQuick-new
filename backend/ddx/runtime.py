"""Loads the trained DDX model exactly as the autoresearch loop saved it, and ranks conditions.

Model files live in ddx/model/ (copied from the ddx_autoresearch folder):
  best_model.pkl, train.py, prepare.py, data/meta.json
"""
from __future__ import annotations

import importlib.util
import json
import logging
import pickle
import sys
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger("prelude.ddx")
HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "model"
DATA_DIR = HERE / "data"

_lock = threading.Lock()
_state: dict = {}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Unpickler(pickle.Unpickler):
    """train.py runs as __main__ when the loop saves the model, so map __main__/train to the loaded module."""

    def find_class(self, module, name):
        if module in ("__main__", "train"):
            return getattr(_state["train"], name)
        return super().find_class(module, name)


def load() -> dict:
    with _lock:
        if _state.get("ready"):
            return _state
        missing = [p for p in ("best_model.pkl", "train.py", "prepare.py", "data/meta.json") if not (MODEL_DIR / p).exists()]
        if missing:
            raise FileNotFoundError(f"DDX model files missing in {MODEL_DIR}: {', '.join(missing)}")
        # train.py may `import prepare`, so register it under that name (it only reads data/meta.json next to it)
        _state["prepare"] = _load_module("prepare", MODEL_DIR / "prepare.py")
        _state["train"] = _load_module("ddx_train", MODEL_DIR / "train.py")
        sys.modules.setdefault("train", _state["train"])
        with open(MODEL_DIR / "best_model.pkl", "rb") as f:
            saved = _Unpickler(f).load()
        _state["model"], _state["labels"] = saved["model"], saved["labels"]
        _state["meta"] = json.loads((MODEL_DIR / "data" / "meta.json").read_text(encoding="utf-8"))
        _state["ready"] = True
        log.info("DDX model loaded: %d conditions", len(_state["labels"]))
        return _state


def available() -> bool:
    try:
        load()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("DDX model unavailable: %s", e)
        return False


def _features(rows: list[dict]):
    import pandas as pd
    s = load()
    raw = pd.DataFrame({"AGE": [r["age"] for r in rows], "SEX": [r["sex"] for r in rows],
                        "EVIDENCES": [list(r["evidences"]) for r in rows]})
    return s["prepare"].featurize(raw, s["meta"])


def scores(rows: list[dict]) -> np.ndarray:
    """rows: [{"age": int, "sex": "F"|"M"|None, "evidences": [codes]}] -> (n, n_conditions) probabilities.
    Unknown/intersex sex: the average of the F and M predictions."""
    s = load()
    expanded, owners = [], []
    for i, r in enumerate(rows):
        for sex in ([r["sex"]] if r.get("sex") in ("F", "M") else ["F", "M"]):
            expanded.append({**r, "sex": sex})
            owners.append(i)
    raw = np.asarray(s["train"].predict(s["model"], _features(expanded)), dtype=float)
    raw = np.clip(raw, 0, None)
    raw = raw / np.maximum(raw.sum(axis=1, keepdims=True), 1e-12)
    out = np.zeros((len(rows), raw.shape[1]))
    counts = np.zeros(len(rows))
    for j, i in enumerate(owners):
        out[i] += raw[j]
        counts[i] += 1
    return out / counts[:, None]


def labels() -> list[str]:
    return load()["labels"]
