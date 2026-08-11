# `infra/` — declarative agent manifests

Desired-state descriptions of everything this project runs on AWS. They are the
**input** to a provisioner (Terraform, CDK, or an in-house service), not a record
of what is currently deployed.

Agent-level config lives **with the agent**; `infra/` holds only what is genuinely
cross-cutting.

```
agents/
  intake/
    agent.yaml         # kind: AgentRuntime — how to build & provision it
    agent-card.yaml    # kind: AgentCard    — what it is to a caller (A2A-style)
    main.py            # AgentCore entrypoint
    intake.py          # the agent's logic
    Dockerfile
    requirements.txt
  coverage/  risk/  orchestrator/

infra/
  bootstrap.yaml       # kind: Bootstrap       — remote state + locking (apply first, once)
  platform.yaml        # kind: Platform        — registry, build, IAM, secrets, gateways, console
  governance.yaml      # kind: GovernanceStore — cert signing key, cert store, policy enforcement
  release.yaml         # kind: Release         — GENERATED: pinned digests + runtime versions
  import.yaml          # kind: ImportMap       — GENERATED: logical name -> existing resource id
  envs/{dev,prod}.yaml # kind: Environment     — the values that differ per environment
  schemas/*.json       # JSON Schema per kind — structural validation, not convention
  validate.py          # drift check — run in CI and before every apply
```

### Hand-authored vs generated

`release.yaml` and `import.yaml` are produced by
`scripts/snapshot-deployment.py`, which reads the live account. **Do not edit
them** — re-run the script after every deploy; the diff is your release note.

| | Hand-authored | Generated |
|---|---|---|
| Says | what you *want* | what is *actually deployed* |
| Files | `agents/*/agent.yaml`, `platform.yaml`, `governance.yaml`, `bootstrap.yaml`, `envs/*` | `release.yaml`, `import.yaml` |

They exist because Terraform needs two things a desired-state manifest cannot
supply: a **content digest** for `container_uri` (the toolkit tags images with a
timestamp, which is not a stable identifier) and a **pinned `target_version`**
for the runtime endpoint (an unset target floats, so the endpoint keeps serving
an old version with no error). `validate.py` fails if either is missing.

`import.yaml` exists because every resource already exists. Without importing
them, a first `terraform apply` tries to create duplicates.

**Adding an agent is adding a directory.** A provisioner discovers
`agents/*/agent.yaml` and iterates; nothing else changes. The directory name must
equal `metadata.name` — `validate.py` enforces that, so an agent can never be
split across two identities.

### agent.yaml vs agent-card.yaml

| | `agent.yaml` | `agent-card.yaml` |
|---|---|---|
| Answers | *How do I build and run this?* | *What is this, and how do I call it?* |
| Read by | the provisioner | callers, other agents, the console |
| Contains | build context, platform, model, memory, network, lifecycle, dependencies | identity, version, skills, input/output schema, capabilities, security scheme |
| Changes when | infrastructure changes | the agent's contract changes |

### Apply order

| # | Stack | Why it must come first |
|---|---|---|
| 1 | `bootstrap.yaml` | Creates the state bucket + lock table everything else stores state in. Keeps its own state locally, then migrates. |
| 2 | `governance.yaml` | The KMS key and certificate store must exist before the console can be given their identifiers. |
| 3 | `platform.yaml` | Registry, build, IAM, secrets and the console service. Console env is resolved from (2). |
| 4 | `agents/*.yaml` | Runtimes and memory. **Sequentially** — see non-negotiable 4 below. |

Step 4 must run after 3 (images need the registry) and step 3's console
`agentBindings` are resolved from 4's outputs — so the console's env is written in
a second pass once the runtime ARNs exist. A provisioner that models this as one
graph gets the ordering for free; one that runs stacks independently needs an
explicit two-phase apply for the console.

---

## Who consumes these

Manifests are only a source of truth if something breaks when reality drifts.

| Consumer | What it reads |
|---|---|
| `infra/validate.py` | All manifests + `policies/allowlist.yaml` + each agent's code. **Run in CI and before every apply** — exits non-zero on drift. |
| `control-plane/app/main.py` | `infra/agents/*.yaml` → `spec.console` builds the specialist and orchestrator registries at startup. No hardcoded agent list. |
| Your provisioner | Everything else. |

The toolkit-generated `.bedrock_agentcore.yaml` files are **gitignored** — they are
account-specific outputs of `agentcore configure`, not inputs.

```bash
python infra/validate.py     # 0 = consistent, 1 = drift
```

It catches: a model or framework missing from the allow-list, a manifest whose
model disagrees with the `DEFAULT_MODEL` literal in its own code, a dependency on
an agent that doesn't exist, colliding console keys or env var names, a
`platform.yaml` binding that injects a different variable than the agent declares,
and any account ID / ARN / absolute path that creeps into a manifest.

---

## What is deliberately absent

These manifests contain **no account ID, no ARN, no absolute path, and no
resource ID**. That is the point — they must apply unchanged to any account.

The toolkit-generated `.bedrock_agentcore.yaml` mixes desired state with realized
state. Everything in the right-hand column below is an **output** of provisioning
and must never be hand-written into a manifest:

| Desired state (belongs here) | Realized state (provisioner output) |
|---|---|
| `model.id`, `runtime.protocol`, `networkMode` | `agent_id`, `agent_arn` |
| `memory.mode`, `memory.eventExpiryDays`, `memory.name` | `memory_id`, `memory_arn` |
| `build.context`, `build.platform` | `ecr_repository` URI, image digest |
| `identity.inbound.type` | `execution_role` ARN |
| `dependencies[].agent` | the resolved target ARN + the IAM grant |

`spec.dependencies` is the mechanism that keeps ARNs out. The orchestrator
declares *"I invoke intake"*; the provisioner resolves that to an ARN, injects it
as `INTAKE_ARN`, **and** grants `bedrock-agentcore:InvokeAgentRuntime` on it to the
orchestrator's execution role. Never hand-maintain those grants.

---

## Field reference (`kind: AgentRuntime`)

| Field | Values | Notes |
|---|---|---|
| `spec.source.framework` | `gcp-adk`, `claude-agent-sdk`, `langchain`, … | Informational; does not change provisioning |
| `spec.source.entrypoint` | path | **Relative to `build.context`** |
| `spec.source.build.type` | `container`, `direct_code_deploy` | `container` builds remotely |
| `spec.source.build.platform` | `linux/arm64` | AgentCore requires arm64 |
| `spec.model.id` | Bedrock model or inference-profile id | |
| `spec.model.provider.requiresInferenceProfileDiscovery` | bool | Claude Agent SDK only — see gotcha below |
| `spec.runtime.protocol` | `HTTP`, `MCP`, `A2A`, `AGUI` | Server protocol the runtime speaks |
| `spec.runtime.networkMode` | `PUBLIC`, `VPC` | `VPC` additionally needs subnets + security groups |
| `spec.memory.mode` | `STM_ONLY`, `STM_AND_LTM` | |
| `spec.identity.inbound.type` | `IAM`, `JWT`, `OAUTH` | Who may invoke the runtime |
| `spec.identity.outbound.credentialProviders` | list of names | Egress auth, defined in `platform.credentialProviders` |
| `spec.tools.mcpServers` | list | Outbound MCP servers the agent may call |
| `spec.tools.gateways` | list of names | AgentCore Gateway targets from `platform.gateways` |
| `spec.dependencies[]` | `{agent, injectAs, grant}` | Agent-to-agent edges |
| `spec.data[]` | `{name, type, source, mountPath}` | Datasets baked into the image |

---

## Terraform mapping

Field names are provider-neutral so a non-Terraform consumer isn't reading
Terraform vocabulary. The mapping below is mechanical:

| Manifest | Terraform |
|---|---|
| `infra/agents/*.yaml` | `for_each = fileset("infra/agents", "*.yaml")` → `yamldecode()` |
| `kind: AgentRuntime` | `aws_bedrockagentcore_agent_runtime` |
| `spec.memory.*` | `aws_bedrockagentcore_agent_memory` |
| `spec.runtime.protocol` | `protocol_configuration.server_protocol` |
| `spec.runtime.networkMode` | `network_configuration.network_mode` |
| `spec.runtime.lifecycle.*` | `lifecycle_configuration.*` |
| `spec.identity.inbound.jwt` | `authorizer_configuration` |
| `spec.dependencies[]` | `aws_iam_role_policy` on the caller + an env var |
| `platform.services[].kind: container-service` | `aws_apprunner_service` |
| `platform.secrets[]` | `aws_secretsmanager_secret` + `runtime_environment_secrets` |

> Verify the exact attribute names against your pinned AWS provider version — the
> AgentCore resources are new and attribute naming has moved between releases.
> Treat this table as the intended target, not as verified provider schema.

---

## Non-negotiables for the provisioner

1. **Pin the endpoint to an explicit runtime version.** Versions are immutable; an
   endpoint left on an old version serves stale code indefinitely with no error.
2. **Pin images by digest.** Never deploy from `:latest`, and never use a
   timestamp to force a redeploy — it makes every plan dirty and defeats rollback.
3. **Merge platform env vars last**, so a manifest can't override
   platform-injected values (memory ids, dependency ARNs, region).
4. **Provision agents sequentially, not in parallel.** Concurrent first-time
   deploys race on the shared CodeBuild source bucket and fail with
   `OperationAborted: conflicting conditional operation`. Observed, not theoretical.
5. **Assert `platform.prerequisites` before apply.** Model access failures surface
   only at invoke time, long after a green apply.

---

## Gotcha worth encoding

`bedrock:ListInferenceProfiles` is **not** in the execution role the AgentCore
toolkit auto-creates, but the Claude Agent SDK calls it to discover models. Denied,
the bundled CLI silently falls back through a hardcoded model list and reports a
model unrelated to the one configured — which makes a model-access problem look
like a model-selection bug. Any agent with
`model.provider.requiresInferenceProfileDiscovery: true` needs that permission.
