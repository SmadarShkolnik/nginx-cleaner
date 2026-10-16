# Scan diff: nginx:1.25-bookworm vs rebuilt image

**Result:** Trivy High+Critical 62→32 (345 findings removed); Grype High+Critical 326→153 (337 findings removed). **0 added (no regressions)**.

_A finding is one package x CVE pair; the same CVE in several packages counts once per package. Severity columns count findings._

### Trivy

| state | findings | unique IDs | Critical | High | Medium | Low | other |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 825 | 526 | 14 | 48 | 63 | 48 | 652 |
| rebuilt | 480 | 284 | 4 | 28 | 43 | 41 | 364 |
| removed | 345 | 242 | 11 | 28 | 32 | 6 | 268 |
| added | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Grype

| state | findings | unique IDs | Critical | High | Medium | Low | other |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 796 | 497 | 47 | 279 | 269 | 39 | 162 |
| rebuilt | 459 | 263 | 25 | 128 | 128 | 21 | 157 |
| removed | 337 | 234 | 25 | 149 | 140 | 18 | 5 |
| added | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**What drove the removals (top packages, Grype):**

| package | findings removed |
|---|---:|
| openssl | 42 |
| libssl3 | 42 |
| libexpat1 | 30 |
| libgnutls30 | 21 |
| libxml2 | 20 |
| curl | 14 |
| libcurl4 | 14 |
| libde265-0 | 12 |

### Target CVEs

Package(s) where each CVE is reported (`—` = not reported); verdict is derived only from these scans.

| CVE | Trivy baseline | Trivy rebuilt | Grype baseline | Grype rebuilt | Grype rebuilt + VEX | Verdict |
|---|---|---|---|---|---|---|
| CVE-2026-15176 | — | — | nginx | nginx | — | Cleared by VEX |
| CVE-2025-15467 | libssl3, openssl | — | libssl3, openssl | — | — | No longer reported |
| CVE-2024-5535 | libssl3, openssl | — | libssl3, openssl | — | — | No longer reported |
| CVE-2026-93479 | — | — | nginx | nginx | — | Cleared by VEX |

