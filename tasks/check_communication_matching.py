#!/usr/bin/env python3
"""Check that the communication matcher is neither too tight nor too loose.

The communication half of the reward is substring matching against hand-authored
surface forms, which fails in two opposite ways and needs guarding against both.

Too tight is the common one and it is invisible: an agent says the right thing in
words nobody enumerated, scores zero, and the failure looks like the agent's
fault. Bare figures exist to fix that - listing '15' finds "15 USD", "15.00
dollars" and "a total of 15" without anyone having to predict each phrasing.

Too loose is rarer and worse, because it credits a wrong answer. A bare '15'
matched as a plain substring would be found inside '$150', and a bare 'two'
inside 'network'. So bare forms are fenced, and this script asserts the fences
hold across every numeric requirement in every task by trying deliberately wrong
figures against each one.

Runs in under a second, needs no Docker, and imports the real matcher from the
graders rather than reimplementing it, so it cannot drift from what is scored.

    ./check_communication_matching.py

Exit status is 0 only when no requirement accepts a wrong figure.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import sys
import types
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
BARE_NUMBER = re.compile(r"^[$€£]?\d[\d,.]*$")


def load_matcher(task_dir: str):
    """Import grade.py from a task without its server-side dependencies."""
    stub = types.ModuleType("statecheck")
    stub.DEFAULT_BASE = "http://127.0.0.1:8080"
    stub.DEFAULT_TOKEN_FILE = "/dev/null"
    sys.modules["statecheck"] = stub
    spec = importlib.util.spec_from_file_location(
        "grade_under_test", os.path.join(task_dir, "tests", "grade.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def values_in(forms: list[str]) -> set[Decimal]:
    found = set()
    for form in forms:
        for token in NUMBER.findall(form):
            try:
                found.add(Decimal(token.replace(",", "")))
            except InvalidOperation:
                pass
    return found


def wrong_values(vals: set[Decimal]) -> list[Decimal]:
    """Figures that are genuinely different, not just written differently.

    62.00 and 62.000 are the same amount, so proposing one as a wrong answer
    would only ever produce a false alarm.
    """
    biggest = max(vals)
    candidates = {biggest * 10, biggest + 1, biggest + Decimal("0.09"),
                  biggest / 10, biggest - Decimal("0.5")}
    return [c for c in sorted(candidates) if c > 0 and c not in vals]


def main() -> int:
    tasks = sorted(glob.glob(os.path.join(HERE, "[0-9][0-9]-*")))
    if not tasks:
        print("no tasks found", file=sys.stderr)
        return 1

    failures = 0
    numeric = tried = 0
    for task_dir in tasks:
        slug = os.path.basename(task_dir)
        grade = load_matcher(task_dir)
        path = os.path.join(
            task_dir, "environment", "verifier-data", "communicate_info.json"
        )
        with open(path) as fh:
            required = json.load(fh)["required"]

        problems = []
        skipped: list[tuple[str, list[str]]] = []
        for entry in required:
            forms = [grade.normalize(f) for f in entry["any_of"] if f.strip()]
            vals = values_in(forms)
            if not vals:
                continue
            numeric += 1

            # Loose: a different figure must never satisfy the requirement.
            for wrong in wrong_values(vals):
                text = format(wrong.normalize(), "f").rstrip(".")
                for said in (f"the amount is ${text} in total",
                             f"that comes to {text} dollars"):
                    tried += 1
                    spoken = grade.normalize(said)
                    hit = next(
                        (f for f in forms if grade.form_matcher(f)(spoken)), None
                    )
                    if hit:
                        problems.append(
                            f"{entry['id']}: {text!r} wrongly matched form {hit!r}"
                        )

            # Tight: where a bare figure IS offered, it has to do its job - be
            # found regardless of the unit word around it. Not every requirement
            # gets one, and that is deliberate rather than an oversight: a bare
            # figure is only safe when the entry names a single value of ten or
            # more. '40,000 points' keeps its unit because a bare '40000' could be
            # dollars, and '2' is too common in prose to carry a fact alone.
            bare = [f for f in forms if BARE_NUMBER.match(f)]
            for figure in bare:
                for said in (f"that comes to {figure} in total",
                             f"the figure is {figure}"):
                    if not grade.form_matcher(figure)(grade.normalize(said)):
                        problems.append(
                            f"{entry['id']}: bare figure {figure!r} does not match "
                            f"its own plain use in {said!r}"
                        )
            if not bare:
                skipped.append((entry["id"], sorted(str(v) for v in vals)))

        note = f" ({len(skipped)} without a bare figure, by design)" if skipped else ""
        if problems:
            failures += len(problems)
            print(f"{slug}{note}")
            for problem in problems:
                print(f"    FAIL {problem}")
        else:
            print(f"{slug:46} ok{note}")
        for rid, vals in skipped:
            print(f"        - {rid} keeps its unit word (values {', '.join(vals)})")

    print()
    print(f"{numeric} numeric requirements; {tried} wrong-figure utterances tried")
    if failures:
        print(f"{failures} problem(s)")
        return 1
    print("no requirement accepts a wrong figure; every bare figure matches its "
          "own plain use")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
