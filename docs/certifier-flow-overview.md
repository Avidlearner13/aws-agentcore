# AgentCore Certifier — Executive Overview

> One idea: **no certificate, no deployment.** An agent must earn a signed certificate before the
> platform will let it run — and that certificate can be revoked to kill it instantly.

```mermaid
flowchart LR
  classDef earn fill:#1f7a1f,stroke:#0d3d0d,color:#fff;
  classDef gate fill:#c79100,stroke:#7a5800,color:#fff;
  classDef run  fill:#2b5797,stroke:#16315a,color:#fff;
  classDef stop fill:#8a1f1f,stroke:#4d0d0d,color:#fff;

  A["Agent<br/>submitted"]:::run
  B["CERTIFY<br/>check powers · score risk ·<br/>test the live agent · sign cert"]:::earn
  C{"Valid<br/>certificate?"}:::gate
  D["RUN on<br/>AWS AgentCore"]:::run
  E["BLOCKED"]:::stop

  A --> B --> C
  C -->|yes| D
  C -->|no / revoked / expired| E
```

**The three moves:**
1. **Earn it** — an agent is tested (capabilities, risk, live accuracy & safety) and, if it passes,
   gets a cryptographically signed certificate.
2. **Gate it** — every run is checked for a valid cert. No valid cert → blocked.
3. **Kill it** — revoke or expire the cert and the agent stops running immediately.

*(Detailed version: [`certifier-flow.md`](certifier-flow.md).)*
