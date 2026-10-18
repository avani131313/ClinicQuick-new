"""
train.py — the ONLY file the agent edits.

Contract (prepare.py relies on it):
  fit(X, y, deadline) -> model     X: DataFrame with AGE, SEX ('F'/'M'), one 0/1 column per answer code
                                      (e.g. E_55__V_187 = pain in the belly) and a few numeric answers
                                      (e.g. E_56 = pain intensity 0-10, NaN if not asked)
                                   y: integer condition index (0..58); deadline: time.time() to stop by
  predict(model, X)   -> (n, 59) array of scores, higher = more likely
Helpers you may use: prepare.load_raw("train"), prepare.mask(raw, keep, seed), prepare.featurize(raw)

Run an experiment:  python exp.py run "<what you changed>"
"""
import time

import numpy as np

N_CLASSES = 59
MODEL = "lightgbm"        # "naive_bayes" (fast classic symptom-checker baseline) or "lightgbm"
AGE_EDGES = [5, 18, 40, 65]  # age bands used as features

# naive Bayes
NB_ALPHA = 1.0

# LightGBM
NUM_ROUNDS = 150
LEARNING_RATE = 0.1
NUM_LEAVES = 15
MIN_DATA_IN_LEAF = 20
FEATURE_FRACTION = 0.5
BAGGING_FRACTION = 0.8
LAMBDA_L2 = 1.0
SEED = 0


# ---------------------------------------------------------------- features
def binary_matrix(X):
    """0/1 matrix: every answer code, numeric answers as 'was asked', sex, age band."""
    codes = X.drop(columns=["AGE", "SEX"]).to_numpy(dtype=np.float32)
    parts = [np.nan_to_num(codes) != 0,
             (X["SEX"] == "M").values[:, None],
             np.eye(len(AGE_EDGES) + 1, dtype=bool)[np.digitize(X["AGE"].values, AGE_EDGES)]]
    return np.hstack(parts).astype(np.float32)  # float32: fast matrix maths (int8 is ~20x slower)


# ---------------------------------------------------------------- models
def fit(X, y, deadline):
    import prepare
    import pandas as pd
    raw, y_raw = prepare.load_raw("train")
    X_aug = [X]
    y_aug = [y]
    for seed in [1, 2]:
        X_aug.append(prepare.featurize(prepare.mask(raw, keep=0.3, seed=seed)))
        y_aug.append(y_raw)
    X = pd.concat(X_aug, ignore_index=True)
    y = np.concatenate(y_aug)

    present = np.unique(y)  # some conditions may be missing from the training data
    if MODEL == "naive_bayes":
        from sklearn.naive_bayes import BernoulliNB
        clf = BernoulliNB(alpha=NB_ALPHA).fit(binary_matrix(X), y)
        return {"kind": "nb", "clf": clf, "present": clf.classes_}

    import lightgbm as lgb
    remap = {c: i for i, c in enumerate(present)}
    params = dict(objective="multiclass", num_class=len(present), learning_rate=LEARNING_RATE,
                  num_leaves=NUM_LEAVES, min_data_in_leaf=MIN_DATA_IN_LEAF, feature_fraction=FEATURE_FRACTION,
                  bagging_fraction=BAGGING_FRACTION, bagging_freq=1, lambda_l2=LAMBDA_L2, max_bin=63,
                  seed=SEED, verbose=-1)

    def stop_at_deadline(env):
        if time.time() > deadline:
            raise lgb.callback.EarlyStopException(env.iteration, env.evaluation_result_list)

    booster = lgb.train(params, lgb.Dataset(X, np.array([remap[c] for c in y]), categorical_feature=["SEX"]),
                        num_boost_round=NUM_ROUNDS, callbacks=[stop_at_deadline])
    return {"kind": "lgbm", "booster": booster, "present": present}


def predict(model, X):
    if model["kind"] == "nb":
        p = model["clf"].predict_proba(binary_matrix(X))
    else:
        X = X.copy()
        X["SEX"] = X["SEX"].astype("category").cat.set_categories(["F", "M"])
        p = model["booster"].predict(X)
    out = np.zeros((len(X), N_CLASSES))
    out[:, model["present"]] = p
    return out


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    from prepare import run_experiment
    run_experiment(fit, predict)
