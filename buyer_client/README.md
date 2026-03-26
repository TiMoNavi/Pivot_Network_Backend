# Buyer Agent MVP

The buyer side does not pull a seller image back to the buyer machine.
It creates a temporary runtime session on a chosen seller node, then uses the local buyer process to talk to the platform backend.

Current local capabilities:

- upload and run one code file
- upload and run a local directory or zip
- download and run a public GitHub repository archive
- create a shell-style runtime session
- run one-off `exec` commands inside the runtime container
- renew a lease
- bootstrap and disconnect local `wg-buyer`

## CLI

Run one code file:

```powershell
python buyer_client\agent_cli.py run-code `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --seller-node-key 550w-c9dd8df557a4 `
  --code .\examples\main.py `
  --minutes 30
```

Run a local directory or zip:

```powershell
python buyer_client\agent_cli.py run-archive `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --seller-node-key 550w-c9dd8df557a4 `
  --source .\workspace `
  --run-command "python main.py" `
  --minutes 30
```

Run a public GitHub repository:

```powershell
python buyer_client\agent_cli.py run-github `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --seller-node-key 550w-c9dd8df557a4 `
  --repo-url https://github.com/example/repo `
  --ref main `
  --run-command "python main.py" `
  --minutes 30
```

Start a shell-style session:

```powershell
python buyer_client\agent_cli.py start-shell `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --seller-node-key 550w-c9dd8df557a4 `
  --minutes 60
```

Run one command inside the runtime container:

```powershell
python buyer_client\agent_cli.py exec `
  --service-name buyer-runtime-xxxxx `
  --command "python -V"
```

Renew a lease:

```powershell
python buyer_client\agent_cli.py renew `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --session-id 12 `
  --minutes 30
```

Bootstrap local buyer WireGuard:

```powershell
python buyer_client\agent_cli.py wireguard-bootstrap `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --session-id 12 `
  --state-dir .\.cache\buyer-cli
```

Disconnect local buyer WireGuard:

```powershell
python buyer_client\agent_cli.py wireguard-disconnect `
  --state-dir .\.cache\buyer-cli `
  --interface-name wg-buyer
```

Stop a session:

```powershell
python buyer_client\agent_cli.py stop `
  --backend-url http://127.0.0.1:8000 `
  --email buyer@example.com `
  --password super-secret-password `
  --session-id 12
```

## Local Web

Start the local buyer web:

```powershell
python buyer_client\agent_server.py
```

Default address:

```text
http://127.0.0.1:3857
```

The page only talks to the local buyer process.
The local buyer process then exchanges the minimum necessary data with the platform backend.
The page does not directly talk to Docker, WireGuard, seller nodes, or the remote host.

Current page actions:

- single-file execution
- archive / zip execution
- GitHub repository execution
- shell session creation
- container `exec`
- lease renew
- local `wg-buyer` bootstrap
- local `wg-buyer` disconnect

## Current Boundary

- This is still a buyer-agent MVP, not the final direct data-plane design.
- Seller nodes are already on platform WireGuard. Buyer WireGuard is now lease-scoped.
- Port forwarding and a true interactive terminal are still separate next steps.
