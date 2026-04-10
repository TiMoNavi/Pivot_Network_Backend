This directory holds archived Windows troubleshooting scripts that are no longer part of the public seller-client entry surface.

Current public entrypoints:

- `bootstrap/windows/install_and_check_seller_client.ps1`
- `bootstrap/windows/start_seller_client.ps1`

Current supported internal runners stay under `bootstrap/windows/`.

Archived material in this directory is split into two groups:

- `bootstrap/windows/legacy/`
  - Former internal runners and troubleshooting helpers kept for historical reference.
- `bootstrap/windows/legacy/root-scripts/`
  - Old root-level scripts that were moved out of the top-level seller-client directory during the Windows client cleanup.

Nothing in this directory should be treated as a supported user-facing entrypoint.
