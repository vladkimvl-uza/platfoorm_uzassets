# VM deploy — pull-based (SSH-independent)

## The problem

The usual deploy is **push-based**: from a laptop, `ssh ubuntu@89.126.221.64` →
`git pull` → `docker compose build`. That needs **inbound TCP 22** open on the VM.

Diagnosed 2026‑06‑24: inbound **port 22 is firewall‑blocked** (connection *times
out* → packets silently dropped, not "refused"). The VM itself is healthy —
nginx serves HTTP 200 on 443/80. So the box is up; only the SSH *entry door* is shut.
Because the block is at the network layer, it **cannot be opened from outside** —
you need either the cloud firewall rule changed, or out‑of‑band console access.

## Fix A — reopen SSH (fastest, if you have provider access)

Open **inbound TCP 22** in the VM's cloud firewall / security group (whitelist
your IP). If the block is host‑side (`ufw`/`iptables`) you can't SSH in to fix it —
use the provider's **web/serial console** and run e.g. `sudo ufw allow 22/tcp`.
Once 22 is reachable again, the normal push deploy works.

## Fix B — pull-based auto-deploy (durable; survives future SSH outages)

The VM's **outbound** access to `github.com:443` works through the firewall. So
instead of pushing code in, let the VM **pull** it: a systemd timer polls
`origin/master` every ~2 min and self-deploys. No inbound port is ever needed.

### One-time install

In **one** session on the VM (SSH if 22 is open, otherwise the provider's web
console), run:

```bash
/home/ubuntu/platfoorm_uzassets/ops/vm-autodeploy/install.sh
```

(If these files aren't on the VM yet, the installer pulls master first.)

### After that

Just `git push` to **master**. Within ~2 minutes the VM pulls and runs:

1. `git reset --hard origin/master` (preserving `backend/jwt_public.pem`)
2. rebuild + recreate the **nginx** container (frontend)
3. restart the **backend** container (runs runtime migrations + seeds)

Idempotent — when there's nothing new, it's a no-op.

### Operate

```bash
ops/vm-autodeploy/deploy.sh                       # deploy right now (manual)
systemctl status uza-autodeploy.timer --no-pager  # is the poller running?
tail -n 50 /home/ubuntu/uza-autodeploy.log        # what did it do?
sudo systemctl disable --now uza-autodeploy.timer # turn auto-deploy off
```

## Notes

- Tracks **master**. Feature branches (e.g. `feat/financials-ux-overhaul`) deploy
  only after they're merged to master — which keeps the review/rollback flow intact.
- `ubuntu` must be in the `docker` group (it already is — current deploys run as `ubuntu`).
- The 2‑minute cadence is in `uza-autodeploy.timer` (`OnUnitActiveSec`); raise it
  if polling feels too frequent.
