# ACA Native deployment foundation

This folder contains a reviewable Bicep starting point for the standard EDIM
ACA Native deployment. It can be used to learn and validate the deployment
shape in a personal DEV subscription, but it is intentionally **not** a
complete production-ready one-click deployment.

The current template covers the basic ACA foundation and demonstrates
parameterization. Production deployment requires the additional controls in
[Production readiness](#production-readiness) and approval from the platform,
network, security, and data owners.

- `deployContainerApp` defaults to `false`;
- PostgreSQL is expected to be provisioned and backed up by the platform team;
- Key Vault is created empty and must receive secrets through an approved
  secret-management process;
- private VNet integration requires an existing delegated infrastructure
  subnet;
- the image must already be built, scanned, pushed, and approved.

No Azure resources are created by inspecting or compiling these files.

## Files

| File | Purpose |
|---|---|
| `main.bicep` | ACA environment, ACR, user-assigned identity, Key Vault, logging, and optional Container App |
| `dev.bicepparam.example` | Placeholder parameters for a DEV review |
| `prod.bicepparam.example` | Placeholder parameters showing the stricter PROD input expectations |

The `.example` suffix is intentional. Azure CLI requires an active parameter
file to end in `.bicepparam`, so copy the reviewed example before using it:

```bash
cp dev.bicepparam.example dev.bicepparam
# or:
cp prod.bicepparam.example prod.bicepparam
```

The copied file should remain local or be stored in the approved environment
configuration repository. It must not contain secrets.

## Prerequisites

- Azure CLI with the Bicep extension
- A selected subscription and resource group
- A globally unique ACR name
- Approved region and ACA workload profile
- Existing PostgreSQL Flexible Server and database URL secret plan
- Existing VNet/subnet plan for private production networking
- Key Vault naming and secret ownership approval
- Immutable image reference, preferably an ACR digest

Do not put passwords, API keys, database URLs, or license keys in the parameter
file. The template expects the database and Foundry secrets to be created
separately in Key Vault.

## What the current template does

The current `main.bicep` demonstrates these reusable, account-independent
building blocks:

- resource-group-scoped deployment;
- parameterized resource names and image reference;
- user-assigned managed identity;
- ACR with admin login disabled;
- ACR pull role assignment;
- RBAC-enabled Key Vault with public access disabled;
- Log Analytics workspace integration;
- ACA workload-profile environment;
- optional internal/external ingress;
- basic HTTP scaling;
- Key Vault references for database and Foundry secrets.

## Why these controls matter for EDIM agent deployments

An EDIM agent is not an isolated Python process. It is a stateful,
I/O-heavy coordinator that calls several governed services during one graph
run:

```text
Client
  → API ingress and identity
  → ACA agent runtime
      → Databricks / Unity Catalog
      → Azure AI Foundry
      → PostgreSQL StateStore
      → Key Vault
      → retrieval services
      → self-hosted LangSmith, when selected
```

That makes the deployment platform part of the agent’s correctness and safety
boundary, not just a place to run a container.

- **Networking protects data flows.** Agent prompts, telemetry, SQL results,
  state, and credentials cross service boundaries. Private connectivity,
  DNS, routing, and egress allowlists reduce accidental exposure and make
  those flows auditable.
- **Identity protects what an agent can do.** The runtime needs access to
  specific data, models, state, and secrets. Managed/workload identity and
  least-privilege grants prevent a compromised or misconfigured agent from
  inheriting broad subscription or data-platform access.
- **Ingress protects who can invoke an agent.** Authentication identifies the
  caller; authorization determines whether that caller may invoke a particular
  API, environment, or `agent_id`. Internal ACA ingress alone does not answer
  either question.
- **Egress protects where an agent can call.** Without outbound controls, a
  node, dependency, prompt, or accidental configuration could reach an
  unapproved endpoint. Explicit destinations also make private LangSmith and
  licensing connectivity predictable.
- **Persistence protects continuity.** Graph state, HITL decisions,
  recommendations, and audit information must survive replica replacement or
  process restarts. PostgreSQL, backups, and restore testing are therefore
  application requirements, not optional infrastructure extras.
- **Scaling protects correctness and service limits.** LLM, SQL, database, and
  retrieval calls have different latency, quota, and cost profiles. Separating
  API handling from workers and scaling on queue depth prevents a traffic spike
  from creating duplicate work or exhausting downstream quotas.
- **Reliability controls protect long-running workflows.** Retries,
  cancellation, idempotency, dead-letter handling, and HITL resume determine
  whether an agent run is safely recoverable instead of lost or executed
  twice.
- **Observability protects operability and evaluation.** Correlated logs,
  metrics, traces, token usage, tool calls, and quality results allow engineers
  to explain an agent decision, diagnose a failed graph node, and prove which
  version and configuration produced an outcome.
- **Security and supply-chain controls protect the artifact.** Image scanning,
  SBOMs, signing, policy, secret rotation, and immutable digests reduce the
  chance that an unreviewed dependency or image reaches a governed
  environment.
- **Cost controls protect sustainability.** Agent workloads can multiply
  spend through model tokens, retries, replicas, SQL warehouse time, storage,
  and trace retention. Budgets, quotas, retention, and per-environment
  ownership are needed before production traffic.
- **Environment parity protects portability.** The same YAML graph should
  behave consistently in personal DEV, enterprise DEV, and PROD. Separating
  parameters from the template lets teams test safely without embedding
  subscription-specific names, endpoints, or credentials.

The following production controls are **not** fully implemented by the current
template. Each item must be supplied by this template, an approved shared
module, or a platform service before PROD.

### Networking

The template accepts `infrastructureSubnetId`, but does not create the
complete network foundation:

- **VNet and delegated ACA subnet:** create the VNet, address ranges, subnet
  delegation, and IP capacity for ACA infrastructure and future scale.
- **Private endpoints:** create private endpoints for Key Vault, PostgreSQL,
  and any private Foundry, Databricks, or LangSmith service.
- **Private DNS zones and links:** link the zones to the VNet so private
  endpoint names resolve correctly from ACA.
- **Network security groups:** define permitted inbound and outbound flows
  for the ACA subnet and private endpoints.
- **Route tables/forced tunneling:** route outbound traffic through the
  enterprise inspection path when required.
- **Azure Firewall or NAT Gateway:** provide controlled outbound egress and a
  stable public source IP where an approved destination requires one.
- **Private service connectivity:** verify routes and DNS from ACA to
  PostgreSQL, Key Vault, Foundry, Databricks, and self-hosted LangSmith.
- **Egress allowlists and DNS controls:** permit only approved FQDNs/ports and
  prevent arbitrary outbound destinations.

### Ingress, authentication, and authorization

The `internalIngress` parameter controls ACA exposure only. It does not
authenticate callers or decide what they may do.

- **Authentication:** establishes who is calling, normally through Entra
  ID/OIDC at APIM or ACA authentication.
- **Authorization:** establishes what an authenticated caller may do, such as
  API operation, environment, agent, or approval permissions.
- **APIM:** provides the enterprise API boundary, policies, quotas, versioning,
  and integration with Entra where required.
- **Entra ID authentication:** register the API, issuer, audience, clients,
  and token validation policy.
- **OAuth scopes/app roles:** define delegated scopes and application roles
  for API consumers and service-to-service callers.
- **Easy Auth/ACA authentication:** configure only if it is the approved
  alternative to APIM; do not assume internal ingress provides this.
- **WAF and rate limiting:** protect public or partner-facing entry points
  against common web attacks and abusive request rates.
- **API authorization policies:** enforce role/scope checks before invoking an
  agent or accessing a data plane.
- **Per-agent access control:** maintain an allowlist mapping callers/roles to
  approved `agent_id` values.
- **CORS at the edge:** restrict browser origins at APIM/WAF and keep the
  application `EDIM_CORS_ORIGINS` allowlist aligned with it.

### Egress

The template does not control outbound traffic. The production topology should
look like:

```text
ACA → private VNet → NSG/UDR → Firewall or NAT → approved destinations
```

The egress design must explicitly cover:

- Azure AI Foundry endpoints;
- Databricks workspace and SQL warehouse endpoints;
- Key Vault;
- PostgreSQL;
- self-hosted LangSmith API;
- `beacon.langchain.com` or another vendor licensing endpoint when required;
- DNS resolvers, proxy requirements, and firewall logs.

Use private endpoints wherever supported. If a public endpoint is unavoidable,
document the FQDN, port, purpose, source identity/IP, TLS requirement, and
approval. `internalIngress=true` affects inbound traffic only and is not an
egress security control.

### Scaling and reliability

The current template has only a basic HTTP scale rule. Production also needs:

- **Queue-based ACA workers:** move long-running graph execution out of the
  request path.
- **ACA Jobs:** run scheduled, batch, or retryable work without keeping an API
  replica busy.
- **KEDA queue scaling:** scale workers on queue depth, not only HTTP request
  count.
- **Separate API and worker applications:** independently scale interactive
  requests and background execution.
- **Startup/readiness/liveness probes:** prevent traffic before startup is
  complete and remove unhealthy replicas safely.
- **Graceful shutdown:** stop accepting work, finish safe operations, and
  release connections during revision changes.
- **Revision and traffic splitting:** support controlled rollout, canary,
  rollback, and zero-downtime promotion.
- **Deployment concurrency limits:** protect Foundry, Databricks, PostgreSQL,
  and downstream systems from replica storms.
- **Quota protection:** define request limits, timeouts, concurrency, retry
  budgets, and backpressure for Foundry, Databricks, and PostgreSQL.
- **Retry/dead-letter/cancellation/idempotency:** make queue processing
  recoverable without duplicate recommendations or lost work.

For HITL and other long operations, persist state and return a correlation ID;
do not hold an HTTP request open while waiting for a human.

### Data and secrets

PostgreSQL is not provisioned by this template. It assumes the database and
Key Vault secrets already exist.

Production still requires:

- PostgreSQL Flexible Server;
- private endpoint and private DNS;
- high-availability policy;
- automated backups and point-in-time restore;
- database firewall/private access rules;
- database migration and connection-pool policy;
- Key Vault secret creation, rotation, versioning, and recovery;
- Databricks warehouse permissions and Unity Catalog grants;
- Foundry resource/data-plane permissions;
- retention and deletion rules for state, recommendations, and traces.

Database URLs, Foundry credentials, LangSmith keys, and license keys must be
injected at runtime. They must not be stored in Bicep parameters, YAML,
Dockerfiles, images, or source control.

### Security, operations, and cost

The current template does not yet provide the complete production operating
model:

- **Resource tags:** environment, application, owner, cost center, data
  classification, and business criticality.
- **Azure Policy:** allowed regions/SKUs, private networking, TLS, identity,
  diagnostic settings, and mandatory tags.
- **Diagnostic settings:** send ACA, ACR, Key Vault, networking, and database
  logs/metrics to the approved monitoring workspace.
- **Defender/image scanning:** scan images and dependencies before promotion.
- **SBOM and signing:** generate a software bill of materials, sign artifacts,
  and verify signatures at deployment.
- **ACR retention and geo-replication:** remove old images safely and replicate
  according to recovery objectives.
- **Alerts and SLOs:** define availability, latency, error rate, queue depth,
  replica health, database health, token/LLM failures, and trace-ingestion
  alerts with named responders.
- **Cost budgets:** set subscription/resource-group budgets, forecast alert
  thresholds, ACR/storage retention limits, and per-environment spend
  ownership.
- **Production workload profile:** select a production ACA profile, CPU/memory,
  minimum replicas, maximum replicas, and zone/resiliency policy based on load
  tests—not the DEV defaults.
- **Key Vault private endpoint:** include the endpoint and DNS path in the
  production network design.
- **Backup and disaster recovery:** document RPO/RTO, backup ownership,
  restore testing, and regional recovery.
- **Incident and rollback runbooks:** define alerts, escalation, revision
  rollback, image rollback, secret rollback, and post-incident evidence.

These omissions are deliberate. This folder provides a portable foundation and
review checklist; it is not evidence that the complete production topology
has been implemented.

## DEV versus PROD use

The same template can be used with different parameter files, but the
parameter file does not create missing enterprise services or permissions.

| Area | Personal DEV exercise | Enterprise PROD |
|---|---|---|
| Resource names | Personal, globally unique names | Enterprise naming standard |
| Region | Approved personal region | Approved enterprise region |
| Networking | May begin without private integration | VNet, private endpoints, private DNS, firewall/NAT required |
| Ingress | Internal or temporary controlled access | APIM/WAF/Entra policy required |
| Database | Existing DEV database or separately managed test service | HA PostgreSQL, backups, private access, restore testing |
| Identity | Personal subscription identity for testing | Dedicated workload identity and least-privilege roles |
| Scaling | Small replica limits | Load-tested limits tied to service quotas and SLOs |
| Observability | Basic Log Analytics | Application Insights, alerts, dashboards, retention, incident routing |

Personal DEV validates Bicep syntax, resource dependencies, naming, and basic
ACA mechanics. It cannot prove enterprise network isolation, SSO, APIM policy,
Databricks authorization, or production recovery.

## Production readiness

Before using this template for PROD, split or extend it into approved modules
for the following topology:

```text
Network foundation
  → VNet / delegated ACA subnet / private DNS / firewall or NAT
Identity foundation
  → managed identity / workload identity / Key Vault / RBAC
Data foundation
  → PostgreSQL / backups / private access / restore
Runtime foundation
  → ACA environment / workload profile / ACR / image policy
Application
  → API / workers or Jobs / probes / scaling / revisions
Edge and access
  → APIM / WAF / Entra authentication / authorization / rate limits
Operations
  → diagnostics / Application Insights / alerts / budgets / DR
```

Authentication and authorization must be designed separately:

- **Authentication** answers “who is calling?”—for example, Entra ID/OIDC
  through APIM or ACA authentication.
- **Authorization** answers “what may they do?”—for example, scopes, app roles,
  API policies, and per-agent allowlists.
- **Workload identity** answers “what may the running container access?”—for
  example, Key Vault, PostgreSQL, Databricks, and Foundry.

Egress should be explicit in the enterprise design:

```text
ACA → private VNet → Firewall/NAT → approved Foundry/Databricks/Key Vault/
      PostgreSQL/LangSmith destinations
```

Do not treat `internalIngress=true` as a complete security boundary. It
controls inbound ACA exposure only; it does not implement caller identity,
authorization, or outbound network restrictions.

## Review the template without deploying

Copy the example and replace only placeholders:

```bash
cd /path/to/edim/edim-dde-api/deploy/azure/aca-native
cp dev.bicepparam.example dev.bicepparam

az bicep build --file main.bicep
az deployment group what-if \
  --resource-group <dev-resource-group> \
  --parameters dev.bicepparam
```

The `what-if` output must be reviewed by the subscription owner before any
deployment. The initial review should keep `deployContainerApp=false`.

For a production-shaped review:

```bash
az deployment group what-if \
  --resource-group <enterprise-prod-resource-group> \
  --parameters prod.bicepparam
```

The PROD example intentionally keeps `deployContainerApp=false`; it is a
reference for required inputs, not approval to provision production resources.

## Deployment sequence after approval

1. Create or select the DEV resource group.
2. Apply the foundation with `deployContainerApp=false`.
3. Provision PostgreSQL Flexible Server and private DNS/networking.
4. Add the database URL and Foundry secrets to Key Vault.
5. Build, scan, and push the immutable API image to the created ACR.
6. Change `image` to the approved ACR digest and set
   `deployContainerApp=true`.
7. Run `az deployment group what-if` again.
8. Obtain explicit approval for the resource changes.
9. Deploy with `az deployment group create`.
10. Run `/health`, dry smoke, live SQL smoke, and rollback validation.

The template does not grant the ACA identity Databricks warehouse or Unity
Catalog permissions. Those are explicit platform/data-plane grants and are
documented in [Deployment targets](../../../../edim-dde-domain/docs/api/deployment-targets.md).

## Important review items

- `publicNetworkAccess` is disabled for Key Vault; private endpoint and DNS
  wiring must exist before the Container App needs the vault.
- `infrastructureSubnetId` is empty in the example and must not remain empty
  for the private production topology.
- The template creates a basic ACR suitable for a DEV exercise. Use the
  platform-approved SKU and geo-replication policy for higher environments.
- The default ACA scale values are placeholders. Tune them against Foundry,
  PostgreSQL, and Databricks quotas.
- Do not use `latest`; promote the same image digest between environments.
- Do not call the current template production-ready until the missing
  networking, edge authentication, egress, data, scaling, and operations
  controls have been implemented or supplied by approved shared modules.

## Recommended next implementation steps

1. Agree on the enterprise network pattern and create a reusable network
   module.
2. Add private endpoints and private DNS for Key Vault and PostgreSQL.
3. Add APIM/WAF/Entra authentication and authorization outside or in front of
   ACA.
4. Add PostgreSQL, backup, restore, and workload identity modules.
5. Add API/worker separation, probes, queue scaling, revisions, and rollout
   policies.
6. Add diagnostics, Application Insights, alerts, policy, budgets, and DR
   validation.
7. Keep the personal DEV deployment small and use `what-if` before every apply.

