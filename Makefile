# One-command build of the nginx:1.25-bookworm drop-in replacement.
#   make all     -> debs from source, image, compatibility test
#   make scan    -> Trivy + Grype on the new image, diff vs baseline
#   make vex     -> Grype with the VEX document applied

ORIG_IMAGE ?= nginx:1.25-bookworm
IMAGE      ?= echo/nginx:1.25-bookworm
DEBS       := out/debs
BASELINE   := scan-result/start
FIXED      := scan-result/fixed
TARGET_CVES := CVE-2026-15176 CVE-2025-15467 CVE-2024-5535 CVE-2026-93479

export DOCKER_BUILDKIT=1

.PHONY: all deb image test scan vex sizes clean

all: deb image test

DOCKER_BUILD_FLAGS ?=
# OPENSSL_CHECK=1 runs OpenSSL's upstream test suite during `make deb` (slower).
# Default 0 keeps builds fast (DEB_BUILD_OPTIONS=nocheck).
OPENSSL_CHECK ?= 0

deb:
	rm -rf out/debs
	docker build $(DOCKER_BUILD_FLAGS) --build-arg OPENSSL_CHECK=$(OPENSSL_CHECK) -f build/Dockerfile --output type=local,dest=out/debs build/
	ls -l out/debs

image:
	docker pull $(ORIG_IMAGE)
	docker build -f Containerfile -t $(IMAGE) .

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

clean:
	rm -rf out test/.work
