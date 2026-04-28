# INFRA — Infrastructure & cloud resources

> Provisioning, networking, DNS, environments, cloud-resource lifecycle.

## Scope

### Owns
- Infrastructure-as-code (Terraform / Pulumi / CDK / etc.)
- Cloud resource provisioning (compute, storage, networking, secrets)
- DNS records (non-mail; mail DNS may belong to a dedicated EMAIL epic if you add one)
- Environment topology (dev / staging / prod)
- Networking (VPC/VNet, subnets, peering, firewalls)
- TLS certificates and renewal automation
- Backup and disaster-recovery infrastructure

### Does NOT own
- CI/CD pipelines (build, test, deploy automation) → **CICD**
- Application code being deployed → that feature's epic
- Observability stack itself (Sentry / Grafana / etc. as a *tool*) → **OBS** owns it once provisioned
- Security audit of infra (CSP, headers, etc.) → **SEC** audits, INFRA implements

### Interfaces with
- **CICD** — CICD calls into the infra layer to deploy; INFRA exposes stable contracts (image tags, env vars, secrets)
- **SEC** — secret management lives in INFRA but secret-rotation policy comes from SEC
- **OBS** — observability resources live in INFRA-managed accounts; OBS owns the agent/config layer

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Multi-region strategy: when does it become a real requirement?
- DR target RPO/RTO?

## External dependencies

- Cloud provider(s).
