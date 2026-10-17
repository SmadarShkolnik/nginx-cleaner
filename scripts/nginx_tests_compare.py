#!/usr/bin/env python3
"""Compare nginx-tests results between the original and the new image.

usage: nginx_tests_compare.py <orig-summary> <new-summary>
Each summary is `PASS <test>` / `FAIL <test>` lines (from build/nginx-tests.sh).

Exit 0 only if the new image regresses nowhere that the original passed, EXCEPT
for test cases attributable to the CVE-2026-15176 backport (alias + rewrite without
break now yields an empty $request_filename + an alert). Those tests, if any, are
listed in ALLOWED_NEW_FAILURES and reported as expected, not as regressions.
"""
import sys

# The backport changes exactly one behaviour (no-break alias+rewrite). If an
# upstream test encodes that exact case it may newly fail on the patched binary;
# such a test is an EXPECTED difference. Populate from the first real run (keep it
# minimal and justified); an empty set means "no new failures allowed at all".
ALLOWED_NEW_FAILURES = {
    # e.g. "alias.t": "upstream case asserts the pre-fix leak; see CVE-2026-15176",
}


def load(path):
    res = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(("PASS ", "FAIL ")):
                status, name = line.split(" ", 1)
                res[name] = status
    return res


def main():
    orig, new = load(sys.argv[1]), load(sys.argv[2])
    all_tests = sorted(set(orig) | set(new))

    regressions, expected, improvements, other = [], [], [], []
    for t in all_tests:
        o, n = orig.get(t, "ABSENT"), new.get(t, "ABSENT")
        if o == n:
            continue
        if o == "PASS" and n == "FAIL":
            (expected if t in ALLOWED_NEW_FAILURES else regressions).append(t)
        elif o == "FAIL" and n == "PASS":
            improvements.append(t)
        else:
            other.append((t, o, n))

    def show(title, items):
        if items:
            print(f"\n{title}:")
            for it in items:
                print(f"  {it}")

    print(f"nginx-tests: {len(all_tests)} test files, "
          f"{sum(v=='PASS' for v in new.values())} pass on the new image")
    show("Expected new failures (CVE-2026-15176 backport)", expected)
    show("Improvements (now pass, failed on original)", improvements)
    show("Presence/other differences", [f"{t}: orig={o} new={n}" for t, o, n in other])
    show("UNEXPECTED REGRESSIONS", regressions)

    if regressions:
        print("\nFAIL: new image regresses on tests the original passed.")
        sys.exit(1)
    print("\nOK: no unexpected regressions.")


if __name__ == "__main__":
    main()
