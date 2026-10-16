# Scan diff: nginx:1.25-bookworm vs rebuilt image

### Trivy

| | findings (pkg × ID) | unique IDs |
|---|---:|---:|
| baseline | 825 | 526 |
| rebuilt | 480 | 284 |
| removed | 345 | 242 |
| added | 0 | 0 |

### Grype

| | findings (pkg × ID) | unique IDs |
|---|---:|---:|
| baseline | 796 | 497 |
| rebuilt | 459 | 263 |
| removed | 337 | 234 |
| added | 0 | 0 |

### Target CVEs (package where reported, — = not reported)

| CVE | Trivy baseline | Trivy rebuilt | Grype baseline | Grype rebuilt | Grype rebuilt + VEX |
|---|---|---|---|---|---|
| CVE-2026-15176 | — | — | nginx | nginx | — |
| CVE-2025-15467 | libssl3, openssl | — | libssl3, openssl | — | — |
| CVE-2024-5535 | libssl3, openssl | — | libssl3, openssl | — | — |
| CVE-2026-93479 | — | — | nginx | nginx | — |
