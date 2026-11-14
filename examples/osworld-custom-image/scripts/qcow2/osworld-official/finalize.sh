#!/bin/sh
# Run via virt-customize --run after adapt.sh, inside the same working image.
set -eu
for file in /root/.aws/credentials /home/user/.aws/credentials \
 /root/.docker/config.json /home/user/.docker/config.json \
 /root/.config/gcloud/application_default_credentials.json \
 /home/user/.config/gcloud/application_default_credentials.json; do
 if test -s "$file"; then
  echo "Credential file requires review before export: $file" >&2
  exit 1
 fi
done
rm -f /home/user/.ssh/id_* /home/user/.ssh/authorized_keys /root/.ssh/id_* /root/.ssh/authorized_keys
if ! grep -q ssh-keygen /usr/local/sbin/osworld-container-init; then
 printf '\nif test -x /usr/bin/ssh-keygen; then /usr/bin/ssh-keygen -A; fi\n' >> /usr/local/sbin/osworld-container-init
fi
sed -i 's/^Before=systemd-logind.service display-manager.service$/Before=systemd-logind.service display-manager.service ssh.service/' /etc/systemd/system/osworld-container-init.service
test ! -f /home/user/server/out.log || truncate -s 0 /home/user/server/out.log
mkdir -p /var/lib/osworld-migration
dpkg-query -W -f='${Package} ${Version}\n' xserver-xorg-video-dummy x11vnc novnc websockify > /var/lib/osworld-migration/packages.txt
sha256sum /home/user/server/main.py > /var/lib/osworld-migration/server.sha256
truncate -s 0 /etc/machine-id
sync
