# `infra/` — declarative agent manifests

Desired-state descriptions of everything this project runs on AWS. They are the
**input** to a provisioner (Terraform, CDK, or an in-house service), not a record
of what is currently deployed.

```
infra/
  platform.yaml        # shared: registry, build, IAM, secrets, gateways, web console
  agents/
    intake.yaml        # kind: AgentRuntime
    coverage.yaml
    risk.yaml
    orchestrator.yaml
```

**Adding an agent is adding a file.** A provisioner discovers `infra/agents/*.yaml`
and iterates; there are no per-agent edits anywhere else.

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
