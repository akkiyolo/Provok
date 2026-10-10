# Provok infrastructure (AWS)

One small server per environment in **Mumbai (`ap-south-1`)**, managed with Terraform and deployed by GitHub Actions.

```
users ──HTTPS──► Caddy (Let's Encrypt) ─┬─ /api/*, /ws/*, /health ──► api  (FastAPI + embedded ARQ worker)
           EC2 t3.small, Docker Compose └─ everything else ─────────► web  (Next.js standalone)
                                         redis · postgres (staging only; production uses RDS)
S3: media (avatars/ + clips/ public) and deploy bundles · ECR: api + web images · SES: email · SSM: server .env
```

Why this shape: it costs ~$20–25/month for staging (server ~$16, disk ~$3, public IPv4 ~$4), versus $60+ with a
load balancer, NAT gateway and managed Redis. The images are the same ones ECS would run, so moving to ECS
Fargate + RDS + ElastiCache later is a hosting change, not a code change.

- No SSH port is open. Get a shell with `infra/scripts/staging.sh shell` (SSM Session Manager).
- No AWS keys anywhere: the server uses its IAM role (S3, SES, ECR, SSM); GitHub uses OIDC.
- Secrets live in one SSM SecureString (`/provok/<env>/env`); the server pulls it on every deploy.
- Without a domain, the site runs at `https://<elastic-ip-with-dashes>.sslip.io` with a real certificate.

## First-time setup

Prerequisites: AWS CLI v2 signed in as a deploy-capable user (`aws configure sso`, then `aws sts get-caller-identity`
works), Terraform ≥ 1.10.

1. **State bucket** (once per account):
   ```bash
   infra/scripts/bootstrap-state.sh
   ```
2. **Create the staging stack** (from `infra/terraform`, using the `init` line the script printed):
   ```bash
   terraform init -backend-config="bucket=provok-tfstate-<account>" -backend-config="key=staging/terraform.tfstate" \
     -backend-config="region=ap-south-1" -backend-config="use_lockfile=true"
   echo 'ses_sender_emails = ["you@example.com"]' > staging.tfvars   # gitignored; keeps per-env settings
   terraform apply -var-file=staging.tfvars
   ```
   Confirm the SES verification email AWS sends to that address.
3. **Server env**: copy `infra/staging.env.example` to `.env.staging` (repo root, gitignored), fill it in from
   `terraform output`, then:
   ```bash
   infra/scripts/push-env.sh staging .env.staging
   ```
4. **GitHub**: Settings → Secrets and variables → Actions → *Variables* → `AWS_DEPLOY_ROLE_ARN` =
   `terraform output -raw deploy_role_arn`. (Optional: `NEXT_PUBLIC_SENTRY_DSN`.)
5. **Deploy**: Actions → *Deploy* → Run workflow (later deploys run automatically after CI passes on `main`).
6. **Google sign-in**: add `https://<site>/api/v1/auth/google/callback` (redirect URI) and `https://<site>`
   (JavaScript origin) to the OAuth client.
7. **Admin**: `infra/scripts/staging.sh shell`, then
   `cd /opt/provok && sudo docker compose exec api python -m backend.app.cli promote --username <you>`.

## Day to day

| Task | Command |
|---|---|
| Stop staging (save credits; data is kept) | `infra/scripts/staging.sh stop` |
| Start it again | `infra/scripts/staging.sh start` |
| Shell on the server | `infra/scripts/staging.sh shell` |
| Change env / secrets | edit `.env.staging` → `push-env.sh staging .env.staging` → run *Deploy* |
| Logs | shell, then `cd /opt/provok && sudo docker compose logs -f api` |

A stopped server still pays for its disk and Elastic IP (~$7/month). `terraform destroy` removes everything,
including the staging database.

If `staging.sh shell` or a deploy says the instance is not connected right after the first `apply`, the SSM agent
started before the instance role was ready and is backing off: `aws ec2 reboot-instances --instance-ids <id>`.

## Production (later)

Same Terraform with `-var environment=production -var domain=<your domain> -var create_github_oidc_provider=false`
and its own state key. Before launch: move Postgres to RDS (backups, point-in-time restore), set
`COMPOSE_PROFILES=` (empty) and point `DATABASE_URL` at RDS, request SES production access, and add the domain's
DKIM records (`terraform output ses_dkim_records`).
