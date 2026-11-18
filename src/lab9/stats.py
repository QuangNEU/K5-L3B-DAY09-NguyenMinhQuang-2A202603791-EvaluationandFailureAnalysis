"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    # TODO M2
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        hp = h.strip().upper() == POS
        jp = j.strip().upper() == POS
        if hp and jp:
            tp += 1
        elif not hp and jp:
            fp += 1
        elif hp and not jp:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    # TODO M2: precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when the denominator is 0
    """precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when the denominator is 0."""
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    # TODO M2
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("cohen's kappa undefined for empty sequences")
    p_o = (cm["tp"] + cm["tn"]) / n
    h_pos = (cm["tp"] + cm["fn"]) / n
    j_pos = (cm["tp"] + cm["fp"]) / n
    p_e = h_pos * j_pos + (1.0 - h_pos) * (1.0 - j_pos)
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("cohen's kappa undefined when p_e == 1")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    # TODO M2: (p_obs + spec - 1) / (sens + spec - 1)
    denom = sensitivity + specificity - 1.0
    if abs(denom) < 1e-12:
        raise ValueError("Rogan-Gladen undefined when sensitivity + specificity == 1")
    est = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, est))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    # TODO M4
    import numpy as np
    from scipy.stats import bootstrap

    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.shape != arr_b.shape:
        raise ValueError("a and b must have the same length")
    if arr_a.size == 0 or np.allclose(arr_a, arr_b, atol=1e-12, rtol=0.0):
        return (0.0, 0.0, 0.0)
    diff = float(np.mean(arr_a - arr_b))
    res = bootstrap(
        (arr_a, arr_b),
        lambda x, y, axis=-1: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        method="percentile",
        confidence_level=confidence,
        rng=np.random.default_rng(rng),
    )
    return (diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _validate_nck(n: int, c: int, k: int) -> None:
    import numbers

    if any(isinstance(x, bool) or not isinstance(x, numbers.Integral) for x in (n, c, k)):
        raise ValueError("n, c, k must be integers")
    n, c, k = int(n), int(c), int(k)
    if n <= 0 or k <= 0 or k > n or c < 0 or c > n:
        raise ValueError(f"invalid (n={n}, c={c}, k={k}): require 0 <= c <= n and 1 <= k <= n")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    import math

    _validate_nck(n, c, k)
    n, c, k = int(n), int(c), int(k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    import math

    _validate_nck(n, c, k)
    n, c, k = int(n), int(c), int(k)
    return math.comb(c, k) / math.comb(n, k)
