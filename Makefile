# One-command build of the nginx:1.25-bookworm drop-in replacement.
#   make all     -> debs from source, image, compatibility test
#   make scan    -> Trivy + Grype on the new image, diff vs baseline
#   make vex     -> Grype with the VEX document applied

ORIG_IMAGE ?= nginx:1.25-bookworm
IMAGE      ?= echo/nginx:1.25-bookworm
DEBS       := out/debs
BASELINE   := scan-result/start
FIXED      := scan-result/fixed
APT_BASE   := scan-result/apt-upgrade
NT_OUT     := scan-result/nginx-tests
TARGET_CVES := CVE-2026-15176 CVE-2025-15467 CVE-2024-5535 CVE-2026-93479

export DOCKER_BUILDKIT=1

# Base image, pinned by digest (keep in sync with build/versions.env DEBIAN_BASE_DIGEST).
DEBIAN_BASE := debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587

# Target platform. Empty = Docker's default (this host = arm64). Set to build/run
# for another arch under QEMU emulation, e.g. `make deb PLATFORM=linux/amd64`.
# NOTE: amd64 is not verified locally (emulation is slow); CI runs it natively.
PLATFORM ?=
PLATFORM_FLAG := $(if $(PLATFORM),--platform $(PLATFORM),)

.PHONY: all deb image test scan vex sizes clean asan nginx-tests scan-apt-baseline \
        deb-amd64 image-amd64

all: deb image test

DOCKER_BUILD_FLAGS ?=
# OPENSSL_CHECK=1 runs OpenSSL's upstream test suite during `make deb` (slower).
# Default 0 keeps builds fast (DEB_BUILD_OPTIONS=nocheck).
OPENSSL_CHECK ?= 0

deb:
	rm -rf out/debs
	docker build $(PLATFORM_FLAG) $(DOCKER_BUILD_FLAGS) --build-arg OPENSSL_CHECK=$(OPENSSL_CHECK) -f build/Dockerfile --output type=local,dest=out/debs build/
	ls -l out/debs

image:
	docker pull $(PLATFORM_FLAG) $(ORIG_IMAGE)
	docker build $(PLATFORM_FLAG) -f Containerfile -t $(IMAGE) .

# amd64 convenience wrappers (QEMU emulation on an arm64 host; slow, unverified
# locally). Builds + installs for linux/amd64; `make test PLATFORM=linux/amd64`
# then compares against the amd64 original on the same platform.
deb-amd64:
	$(MAKE) deb PLATFORM=linux/amd64
image-amd64:
	$(MAKE) image PLATFORM=linux/amd64

test:
	cd test && ORIG_IMAGE=$(ORIG_IMAGE) NEW_IMAGE=$(IMAGE) python3 -m pytest -v

scan:
	mkdir -p $(FIXED)
	trivy image $(IMAGE) > $(FIXED)/trivy.txt
	grype $(IMAGE) > $(FIXED)/grype.txt
	python3 scripts/scan_diff.py $(BASELINE) $(FIXED) $(TARGET_CVES) > $(FIXED)/diff.md
	cat $(FIXED)/diff.md

vex:
	mkdir -p $(FIXED)
	grype $(IMAGE) --vex vex/nginx.openvex.json > $(FIXED)/grype-vex.txt
	python3 scripts/scan_diff.py $(BASELINE) $(FIXED) $(TARGET_CVES) > $(FIXED)/diff.md
	cat $(FIXED)/diff.md

sizes:
	@docker image inspect --format '{{index .RepoTags 0}}  {{.Size}} bytes' $(ORIG_IMAGE) $(IMAGE)

# --- Opt-in diagnostics (NOT part of `make all`) -------------------------------

# ASan proof: nginx 1.25.5 built with AddressSanitizer, with and without the
# backport, must report a memory error in ngx_http_map_uri_to_path() on /foo/1
# only when unpatched.
asan:
	mkdir -p scan-result/asan
	docker run --rm \
	  -v $(PWD)/build:/src:ro -v $(PWD)/scan-result/asan:/asan-out \
	  -e OUT=/asan-out $(DEBIAN_BASE) sh -c '\
	    apt-get update && apt-get install -y --no-install-recommends \
	      build-essential ca-certificates curl libpcre3-dev zlib1g-dev libssl-dev patch \
	    && /src/asan.sh'

# Upstream nginx-tests against the nginx binary shipped IN each image: run the
# http/alias/rewrite/map/ssl/module subset on the original and on ours, then diff.
# The only allowed new failure is the one caused by the CVE-2026-15176 backport.
nginx-tests:
	mkdir -p $(PWD)/$(NT_OUT)/orig $(PWD)/$(NT_OUT)/new
	docker pull $(ORIG_IMAGE)
	bash build/nginx-tests.sh $(ORIG_IMAGE) $(PWD)/$(NT_OUT)/orig
	bash build/nginx-tests.sh $(IMAGE) $(PWD)/$(NT_OUT)/new
	python3 scripts/nginx_tests_compare.py $(PWD)/$(NT_OUT)/orig/summary.txt $(PWD)/$(NT_OUT)/new/summary.txt

# Honest baseline: what OUR image removes beyond a plain `apt-get upgrade` of the
# original. If the OpenSSL CVEs also clear under apt upgrade, the diff shows it.
scan-apt-baseline:
	mkdir -p $(APT_BASE)
	docker pull $(ORIG_IMAGE)
	printf 'FROM %s\nRUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*\n' \
	  '$(ORIG_IMAGE)' | docker build -t echo/nginx-apt-upgraded:tmp -
	trivy image echo/nginx-apt-upgraded:tmp > $(APT_BASE)/baseline-trivy.txt
	grype echo/nginx-apt-upgraded:tmp > $(APT_BASE)/baseline-grype.txt
	SCAN_DIFF_TITLE="Scan diff: apt-upgraded nginx:1.25-bookworm vs our image" \
	SCAN_DIFF_BASE_LABEL="apt-upgraded" \
	  python3 scripts/scan_diff.py $(APT_BASE) $(FIXED) $(TARGET_CVES) > $(FIXED)/diff-vs-apt-upgrade.md
	cat $(FIXED)/diff-vs-apt-upgrade.md

clean:
	rm -rf out test/.work
