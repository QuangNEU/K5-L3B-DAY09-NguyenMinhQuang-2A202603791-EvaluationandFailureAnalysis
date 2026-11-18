"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _check_ratchet(spec: dict, base_spec: dict, *, same_sha: bool = False) -> list[str]:
    problems: list[str] = []
    if not same_sha and spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems
    new_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in new_metrics:
            problems.append(f"ratchet: metric {mid!r} removed on same eval_set_version")
            continue
        nm = new_metrics[mid]
        if bm.get("blocking") and not nm.get("blocking"):
            problems.append(f"ratchet: metric {mid!r} changed from blocking to non-blocking")
        bth = bm.get("threshold") or {}
        nth = nm.get("threshold") or {}
        if "min" in bth and ("min" not in nth or nth["min"] < bth["min"]):
            problems.append(f"ratchet: metric {mid!r} min loosened ({nth.get('min')} < {bth['min']})")
        if "max" in bth and ("max" not in nth or nth["max"] > bth["max"]):
            problems.append(f"ratchet: metric {mid!r} max loosened ({nth.get('max')} > {bth['max']})")
        if "max_increase" in bth and ("max_increase" not in nth or nth["max_increase"] > bth["max_increase"]):
            problems.append(
                f"ratchet: metric {mid!r} max_increase loosened ({nth.get('max_increase')} > {bth['max_increase']})"
            )
        if bth.get("no_significant_drop") and not nth.get("no_significant_drop"):
            problems.append(f"ratchet: metric {mid!r} dropped no_significant_drop")

    new_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs["name"], bs["metric"])
        if key not in new_slices:
            problems.append(f"ratchet: slice {key[0]}/{key[1]} removed on same eval_set_version")
            continue
        ns = new_slices[key]
        if bs.get("blocking") and not ns.get("blocking"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} changed from blocking to non-blocking")
        if "min" in bs and ("min" not in ns or ns["min"] < bs["min"]):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} min loosened ({ns.get('min')} < {bs['min']})")
        if "max" in bs and ("max" not in ns or ns["max"] > bs["max"]):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} max loosened ({ns.get('max')} > {bs['max']})")
        if bs.get("no_significant_drop") and not ns.get("no_significant_drop"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} dropped no_significant_drop")
    return problems


def _check_metrics_match_rows(pr_metrics: dict, pr_rows: list[dict]) -> list[str]:
    problems: list[str] = []
    if not pr_rows:
        return problems
    by_item: dict[str, list[bool]] = {}
    has_pass_rate = all(r.get("pass_rate") is not None for r in pr_rows)
    if has_pass_rate:
        for r in pr_rows:
            by_item.setdefault(r["item_id"], []).append(bool(r["pass_rate"]))
    for mid, val in pr_metrics.items():
        if val is None or isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            continue
        if mid in ("secret_leak", "approval_bypass"):
            if all(r.get(mid) is not None for r in pr_rows):
                expected = sum(bool(r[mid]) for r in pr_rows)
                if abs(val - expected) > 1e-4:
                    problems.append(f"metric {mid!r} ({val}) disagrees with rows ({expected})")
        elif mid in GRADERS:
            if all(r.get(mid) is not None for r in pr_rows):
                expected = round(sum(bool(r[mid]) for r in pr_rows) / len(pr_rows), 4)
                if abs(val - expected) > 1e-3:
                    problems.append(f"metric {mid!r} ({val}) disagrees with rows ({expected})")
        elif mid == "pass_5" and has_pass_rate and by_item:
            expected = round(sum(all(v) for v in by_item.values()) / len(by_item), 4)
            if abs(val - expected) > 1e-3:
                problems.append(f"metric {mid!r} ({val}) disagrees with rows ({expected})")
        elif (mid.startswith("pass_at_") or mid.startswith("pass_hat_")) and has_pass_rate and by_item:
            try:
                k = int(mid.rsplit("_", 1)[1])
            except ValueError:
                continue
            if min(len(v) for v in by_item.values()) >= k:
                fn = stats.pass_at_k if mid.startswith("pass_at_") else stats.pass_hat_k
                expected = round(sum(fn(len(v), sum(v), k) for v in by_item.values()) / len(by_item), 4)
                if abs(val - expected) > 1e-3:
                    problems.append(f"metric {mid!r} ({val}) disagrees with rows ({expected})")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    pr_manifest = pr.get("manifest") or {}
    base_manifest = base.get("manifest") or {}
    pr_sha = pr_manifest.get("eval_set_sha")
    base_sha = base_manifest.get("eval_set_sha")
    if pr_sha is not None and base_sha is not None and pr_sha != base_sha:
        problems.append("PR eval_set_sha differs from baseline")

    pr_metrics = pr.get("metrics") or {}
    base_metrics = base.get("metrics") or {}
    for mid, val in pr_metrics.items():
        if val is None:
            problems.append(f"metric {mid!r} is None")
        elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            problems.append(f"metric {mid!r} is non-finite ({val})")
    for m in spec.get("metrics") or []:
        mid = m["id"]
        if base_metrics.get(mid) is not None and pr_metrics.get(mid) is None:
            problems.append(f"metric {mid!r} missing/None in PR")

    if pr.get("evaluator_failures"):
        problems.append(f"PR has {len(pr['evaluator_failures'])} evaluator_failure(s)")

    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    if not pr_rows:
        problems.append("PR has no rows")
    expected_rows = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(pr_rows) != expected_rows:
        problems.append(
            f"row count {len(pr_rows)} != manifest {pr_manifest.get('items')} x {len(pr_manifest.get('seeds') or [])}"
        )

    pr_keys = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(set(pr_keys)) != len(pr_keys):
        problems.append("duplicate (item_id, seed) rows in PR")

    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_keys) != base_keys:
        problems.append("PR (item_id, seed) set differs from baseline")

    row_metrics = {
        m["id"]
        for m in spec.get("metrics") or []
        if m["id"] in GRADERS or any(m["id"] in r for r in base_rows)
    }
    missing_cells = [
        f"{r.get('item_id')}@{r.get('seed')}:{mid}"
        for r in pr_rows
        for mid in sorted(row_metrics)
        if r.get(mid) is None
    ]
    if missing_cells:
        problems.append(f"{len(missing_cells)} missing/None metric cell(s), first: {missing_cells[0]}")

    for r in pr_rows:
        for k, v in r.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                problems.append(f"non-finite row value at {r.get('item_id')}@{r.get('seed')}:{k}")
                break

    base_slices = {(r.get("item_id"), r.get("seed")): set(r.get("slices") or []) for r in base_rows}
    for r in pr_rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and set(r.get("slices") or []) != base_slices[key]:
            problems.append(f"slice tags modified for {key[0]}@{key[1]}")
            break

    if not missing_cells:
        problems.extend(_check_metrics_match_rows(pr_metrics, pr_rows))

    if base_spec is not None:
        same_sha = bool(pr_sha and base_sha and pr_sha == base_sha)
        problems.extend(_check_ratchet(spec, base_spec, same_sha=same_sha))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        elif "max" in s and val > s["max"]:
            verdict = "fail"
        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(f"slice:{name}/{mid}")
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  slice:{name}/{mid:<14} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
