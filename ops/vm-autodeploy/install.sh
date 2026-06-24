#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-time installer for pull-based auto-deploy. Run ONCE on the VM (via SSH if
# port 22 is open, or via the cloud provider's web/serial console if it isn't).
#
# After this, every `git push` to master deploys automatically within ~2 min —
# no inbound SSH needed ever again.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="${UZA_REPO:-/home/ubuntu/platfoorm_uzassets}"
DIR="$REPO/ops/vm-autodeploy"

# If the ops files aren't in the repo yet (first install before the commit has
# been pulled), fetch master first.
if [ ! -f "$DIR/deploy.sh" ]; then
  echo "ops/vm-autodeploy not found — pulling master first ..."
  cd "$REPO"
  git fetch origin master
  git reset --hard origin/master
fi

chmod +x "$DIR/deploy.sh"

sudo cp "$DIR/uza-autodeploy.service" /etc/systemd/system/uza-autodeploy.service
sudo cp "$DIR/uza-autodeploy.timer"   /etc/systemd/system/uza-autodeploy.timer
sudo systemctl daemon-reload
sudo systemctl enable --now uza-autodeploy.timer

echo
echo "Installed. The VM will now poll origin/master every ~2 min and self-deploy."
echo "  • run once now:     $DIR/deploy.sh"
echo "  • timer status:     systemctl status uza-autodeploy.timer --no-pager"
echo "  • last run log:     tail -n 50 /home/ubuntu/uza-autodeploy.log"
echo "  • disable:          sudo systemctl disable --now uza-autodeploy.timer"
systemctl status uza-autodeploy.timer --no-pager || true
