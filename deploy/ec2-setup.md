# Deploying Klaudesk to one EC2 instance

**Quick path, from your machine** (what the live demo uses):

1. Store the backend settings as one SSM SecureString parameter holding a JSON object:

   ```json
   {
     "POSTGRES_DB": "khelp", "POSTGRES_USER": "khelp",
     "POSTGRES_PASSWORD": "<openssl rand -hex 16>", "MCP_DB_PASSWORD": "<openssl rand -hex 16>",

     "KHELP_USE_LOCAL_MODEL": "false",
     "KHELP_HOSTED_PROVIDER": "groq",

     "OLLAMA_BASE_URL": "http://<gpu-private-ip>:11434", "OLLAMA_MODEL": "qwen2.5:14b-instruct",
     "GROQ_API_KEY": "<key>", "GROQ_MODEL": "openai/gpt-oss-120b", "KHELP_REASONING_EFFORT": "low",
     "BEDROCK_MODEL_ID": "openai.gpt-oss-120b-1:0", "BEDROCK_REGION": "eu-west-1",

     "KHELP_MAX_TOOL_CALLS": "12", "KHELP_RUN_TIMEOUT_SECONDS": "180",
     "KHELP_MAX_CONCURRENT_RUNS": "2", "KHELP_API_WORKERS": "1", "KHELP_SEED_COUNT": "8",
     "SITE_ADDRESS": ":80"
   }
   ```

   ```bash
   aws ssm put-parameter --name /khelp/prod/env --type SecureString --value file://khelp-env.json
   ```

   **Choosing the model is one switch.** `KHELP_USE_LOCAL_MODEL=true` uses the self-hosted Ollama at
   `OLLAMA_BASE_URL` (`http://ollama:11434` runs Ollama on the same GPU box). `false` uses
   `KHELP_HOSTED_PROVIDER`: `groq` (API key) or `bedrock` (instance role, `BEDROCK_REGION`). Every
   option's settings stay in the parameter; only the switch changes.

2. Give the instance an IAM role with:
   - `ssm:GetParameter` on `arn:aws:ssm:<region>:<account>:parameter/khelp/prod/*`, and `kms:Decrypt`
     with the condition `kms:ViaService = ssm.<region>.amazonaws.com`;
   - for Bedrock: `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on
     `arn:aws:bedrock:<region>::foundation-model/*`, and set the instance metadata hop limit to 2
     (`aws ec2 modify-instance-metadata-options --http-put-response-hop-limit 2`) so the API container
     can use the role.

3. Launch and deploy:

   ```bash
   AWS_REGION=eu-west-1 INSTANCE_TYPE=t3.small KEY_NAME=<key-pair> SECURITY_GROUP=<sg-id> deploy/launch-ec2.sh
   aws ec2 associate-iam-instance-profile --instance-id <id> --iam-instance-profile Name=<profile>
   ENV_SSM_PARAM=/khelp/prod/env deploy/remote-deploy.sh ubuntu@<public-ip> ~/.ssh/<key>.pem
   ```

   The instance fetches the parameter itself and writes `/opt/khelp/.env` (mode 600). A systemd timer
   (`khelp-env-sync.timer`) re-reads the parameter every minute and restarts only what changed, so
   **changing a setting in SSM needs no redeploy**; it is live within about a minute
   (`journalctl -u khelp-env-sync` shows each change). Database passwords only take effect when the
   database is first created.

The rest of this page explains the same steps by hand, and the Groq / CPU options.

Everything runs from `docker compose`: Postgres, the API (with the agent and both MCP servers inside it),
and Caddy serving the web UI and proxying `/api`. The model is either Groq (open-weights `gpt-oss-120b`,
for synthetic-data demos) or Ollama (self-hosted, the production shape).

## 1. Pick the instance

| Model setup | Instance | Why |
|---|---|---|
| Groq, or Ollama on another machine | **t3.small** (2 vCPU, 2 GiB) | The app uses ~200 MB at rest; the 2 GiB covers image builds. About US$15–20/month |
| Ollama on the same box, GPU | **g4dn.xlarge** (NVIDIA T4, 16 GiB) | Runs `qwen2.5:14b-instruct` (best on Pidgin/abbreviated notes) or the faster 7B. About US$0.59/hour in eu-west-1, so stop it when not demoing |
| Ollama on the same box, CPU only | c7i.2xlarge or larger | Works, but expect minutes per patient. Not recommended |

**Region:** the demo runs in **eu-west-1 (Ireland)**. For a real deployment with patient data, use
in-country hosting or **af-south-1 (Cape Town)** (opt-in), the closest AWS region to Nigeria.

**GPU quota:** new AWS accounts often have a limit of 0 vCPUs for G instances. Check
"Running On-Demand G and VT instances" in Service Quotas and request 4 (g4dn.xlarge) before launching.

**AMI:** Ubuntu Server 24.04 LTS (64-bit x86). For the GPU option use the
"Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)", which ships the NVIDIA driver and
container toolkit.

**Storage:** 20 GiB gp3 (40 GiB for the GPU option; model weights are ~5 GB).

**Security group:**

| Port | Source | Purpose |
|---|---|---|
| 22 | your IP only | SSH |
| 80 | 0.0.0.0/0 | web UI (and HTTP→HTTPS redirect when a domain is set) |
| 443 | 0.0.0.0/0 | HTTPS, only if you set a domain |

Do **not** open 5432 (Postgres) or 11434 (Ollama). They are only reachable inside the compose network.

Optionally attach an **Elastic IP** so the address survives stop/start.

## 2. Install Docker

```bash
ssh ubuntu@<instance-ip>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit        # log out and back in so the group applies
ssh ubuntu@<instance-ip>
docker compose version                        # should print v2.x

# t3.small only: add 2 GiB swap so the web build never runs out of memory
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Configure and start

```bash
git clone https://github.com/TheErujeje/KHelp.git && cd KHelp
cp .env.example .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env
sed -i "s/^MCP_DB_PASSWORD=.*/MCP_DB_PASSWORD=$(openssl rand -hex 16)/" .env
nano .env        # choose the model (below)
```

**Groq (demo, synthetic data only):**

```
KHELP_USE_LOCAL_MODEL=false
KHELP_HOSTED_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

```bash
docker compose up -d --build
```

**Self-hosted on this GPU instance:**

```
KHELP_USE_LOCAL_MODEL=true
OLLAMA_MODEL=qwen2.5:14b-instruct
OLLAMA_BASE_URL=http://ollama:11434
```

```bash
docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model up -d --build
docker compose logs -f ollama-pull          # wait for "success" (first start downloads the model)
```

**Self-hosted on a separate GPU instance:** run Ollama there
(`docker run -d --gpus all -p 11434:11434 -v ollama:/root/.ollama ollama/ollama`, then
`docker exec <id> ollama pull qwen2.5:7b-instruct`), allow port 11434 **only from the app
instance's security group**, and set `OLLAMA_BASE_URL=http://<gpu-private-ip>:11434` here.
Start the app without the profile.

The first start builds both images (a few minutes), runs the database migrations, creates the
restricted `khelp_mcp` database role, and seeds 8 synthetic patients.

## 4. Check it

```bash
docker compose ps                       # db healthy, api and web up
curl -s localhost/api/health            # {"ok":true,"model":"groq:openai/gpt-oss-120b"}
docker stats --no-stream                # memory per container
```

Open `http://<instance-ip>/`, sign in with any name, and press **Score** on a waiting patient.

## 5. HTTPS with a domain (optional)

Point a DNS A record (e.g. `triage.example.org`) at the instance's IP, then:

```bash
sed -i "s/^SITE_ADDRESS=.*/SITE_ADDRESS=triage.example.org/" .env
docker compose up -d web
```

Caddy obtains and renews the certificate itself (ports 80 and 443 must be open).

## Day-to-day

```bash
git pull && docker compose up -d --build        # deploy a new version
docker compose logs -f api                      # agent runs, tool errors
docker compose exec api python -m khelp_api.seed --force --count 8   # add more synthetic patients
docker compose exec db pg_dump -U khelp khelp > backup.sql           # back up the database
docker compose down                             # stop (data kept in volumes)
docker compose down -v                          # stop and DELETE all data
```

## Notes

- One API worker is the default (`KHELP_API_WORKERS=1`). Agent runs execute in a small background
  pool inside it (`KHELP_MAX_CONCURRENT_RUNS`, default 2); the live feed reads from the database, so
  adding workers is safe.
- If the API restarts mid-run, that run is marked failed and the patient is flagged for manual triage.
- Groq sends the note to a hosted service outside the country. That is acceptable only because every
  patient here is synthetic. With real patients, use the self-hosted Ollama option.
