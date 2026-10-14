# Deploying KHelp to one EC2 instance

Everything runs from `docker compose`: Postgres, the API (with the agent and both MCP servers inside it),
and Caddy serving the web UI and proxying `/api`. The model is either Groq (open-weights `gpt-oss-120b`,
for synthetic-data demos) or Ollama (self-hosted, the production shape).

## 1. Pick the instance

| Model setup | Instance | Why |
|---|---|---|
| Groq, or Ollama on another machine | **t3.small** (2 vCPU, 2 GiB) | The app uses ~200 MB at rest; the 2 GiB covers image builds. About US$15–20/month |
| Ollama on the same box, GPU | **g4dn.xlarge** (NVIDIA T4, 16 GiB) | Runs `qwen2.5:7b-instruct` at a few seconds per step. About US$0.55–0.75/hour, so stop it when not demoing |
| Ollama on the same box, CPU only | c7i.2xlarge or larger | Works, but expect minutes per patient. Not recommended |

**Region:** use **af-south-1 (Cape Town)** if it is enabled on your account (it is opt-in). It is the
closest AWS region to Nigeria and keeps the "data stays on the continent" story straight for a
self-hosted model. Otherwise eu-west-1 is fine for a synthetic-data demo.

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
KHELP_MODEL_PROVIDER=groq
KHELP_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=gsk_...
```

```bash
docker compose up -d --build
```

**Self-hosted on this GPU instance:**

```
KHELP_MODEL_PROVIDER=ollama
KHELP_MODEL=qwen2.5:7b-instruct
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
