# Assert the original image leaks a body for CVE-2026-15176

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- In `test/test_cve_2026_15176.py`, the original image's behaviour is only recorded, not asserted.
- Add an assertion that the original image returns a **non-empty body for `/foo/1`** (the leaked heap bytes), so the test proves it can detect the vulnerability, not only that the patched image is quiet.
- Keep the existing print output.
- All tests must still pass with `make test`.
- Explain why this makes the test stronger.

## Decisions I inferred

- The assertion goes in the existing `test_original_image_behaviour_recorded` test (the one that probes the original image), so there is still a single place that runs the original image.
- The assertion checks every `/foo/1` probe result, not just the first, so a flaky single response can't pass it. `/foo/1` results are `results[0:10]` because `PATHS[0]` is `/foo/1` with 10 repeats.
- I assert `r.body` is non-empty (`len > 0`). I do not assert exact bytes, because the leaked heap content varies between runs and builds; only "non-empty" is a stable invariant. The patched test already pins the patched body to `b""`, so non-empty vs empty is what discriminates vulnerable from fixed.
- The misleading docstring/line "Not asserted" is updated to describe the new assertion. The function keeps its name to avoid breaking references.
- Status is still asserted as 200 (the server answers; the leak is in the body, not the status).

## Findings while verifying `make test`

- The two new/changed CVE tests pass deterministically (`pytest test_cve_2026_15176.py` -> 2 passed), and the original image's `/foo/1` body is `b'\x00'*17 + b'/x'` (19 bytes).
- `make test` does **not** reliably go green: `test_compat.py::test_tls[...]` fails intermittently (0, 1 or 2 of its 4 params per run). This is **pre-existing and unrelated to this change**:
  - It fails the same way with my edit stashed (full suite: 1 failed, 58 passed).
  - The 4 TLS tests pass when run in isolation; they only flake under the full-suite load.
  - My edit only touches `test_cve_2026_15176.py`.
- Not fixed here (out of scope). The TLS test asserts the full `openssl s_client` text of the original and rebuilt images are byte-identical, which is fragile across the OpenSSL 3.0.11->3.0.22 bump and under load.
