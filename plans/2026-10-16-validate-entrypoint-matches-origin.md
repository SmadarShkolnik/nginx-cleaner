# Validate entrypoint scripts match the origin nginx repo

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- Add validation that the entrypoint scripts are exactly the same as in the origin repo of the nginx tag.

## Decisions I inferred

- "Origin repo of the nginx tag" = `nginxinc/docker-nginx` at commit `9abe4ae`, which is the commit the `Containerfile` header already says it mirrors (nginx 1.25.5 / njs 0.8.4-3). The official `nginx:1.25-bookworm` image is built from that repo at that commit, so its entrypoint files are the authoritative origin.
- Scope = the 5 entrypoint files: `docker-entrypoint.sh` and the four `docker-entrypoint.d/*` scripts.
- Upstream paths at that commit: `mainline/debian/docker-entrypoint.sh` and `entrypoint/<name>` for the `.d` scripts. I fetched all five and confirmed their sha256 equal our `rootfs/` copies.
- Validation has two layers:
  1. **Offline, pinned**: `test/test_entrypoint.py` pins the origin commit + sha256 of each file and asserts our `rootfs/` source files match. No network, no docker.
  2. **Image cross-check (docker)**: asserts the files actually installed in the rebuilt image equal the original `nginx:1.25-bookworm` image's files byte-for-byte, and that the set of entrypoint files is identical (none added or missing).
  3. **Opt-in remote re-pin**: a test gated on `ENTRYPOINT_VERIFY_REMOTE=1` re-fetches from GitHub and confirms the pinned hashes still match origin, so the pins stay honest without making normal runs hit the network.
- The pinned sha256 values (origin @ 9abe4ae, == our rootfs):
  - docker-entrypoint.sh: 3372fd90162da30d09f62c245e9c6bfd620fb0bb5b48ab54b16e804c2b9e8aae
  - 10-listen-on-ipv6-by-default.sh: 8c5d2c912416126c7d65651600b166c00ad9ca3e3af82487ddd5a5da94fb8fb5
  - 15-local-resolvers.envsh: 3659a4a271496f6a8f0785a1d7e57a9348803e90c08fe57431fe3ee19b010644
  - 20-envsubst-on-templates.sh: 253c8724acff9f5c0d0e8938e71fe7c33097d40031a5bc9c7f59dfd2ba5f1377
  - 30-tune-worker-processes.sh: 1f068aa49da8df46bfd5a917debf110af9b115370739e3be34af83ebf583fbce

## Environment note (not a decision)

- Docker Desktop on this machine is currently returning `input/output error` from its containerd content store, so the docker-dependent layer can't be run right now. The offline `rootfs/`-vs-origin check was run and passes. The image cross-check will run once Docker is healthy.
