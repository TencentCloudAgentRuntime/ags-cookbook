#!/bin/sh
# Tested input: xlangai/ubuntu_osworld revision a5d9c3eaae98eebf6e3a0beb84e7e47cf72ae133.
# Run inside the image via virt-customize --run; do not execute on the host.
set -eu
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 22.04
test -f /home/user/server/main.py
test "$(id -u user)" = 1000
export DEBIAN_FRONTEND=noninteractive
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 0755 /usr/sbin/policy-rc.d
# Do not refresh the source image's unrelated third-party repositories.
apt-get update -o Acquire::Retries=3 -o Acquire::http::Timeout=30 \
  -o Dir::Etc::sourcelist=sources.list -o Dir::Etc::sourceparts=-
apt-get install -y --no-install-recommends \
  xserver-xorg-video-dummy x11vnc novnc websockify

cp -a /etc/fstab /etc/fstab.vm-backup
printf '# Container mounts are supplied by the runtime.\n' > /etc/fstab
rm -f /swapfile
for unit in cloud-init-local.service cloud-init.service cloud-config.service cloud-final.service \
  open-vm-tools.service vmtoolsd.service qemu-guest-agent.service spice-vdagentd.service \
  acpid.service acpid.socket acpid.path systemd-modules-load.service console-getty.service \
  NetworkManager-wait-online.service systemd-networkd-wait-online.service; do
  ln -sf /dev/null "/etc/systemd/system/$unit"
done
mkdir -p /home/user/.config/autostart
for entry in vmware-user.desktop spice-vdagent.desktop; do
  if test -f "/etc/xdg/autostart/$entry"; then
    printf '[Desktop Entry]\nType=Application\nName=Disabled VM integration\nHidden=true\n' > "/home/user/.config/autostart/$entry"
    chown user:user "/home/user/.config/autostart/$entry"
  fi
done

cat > /etc/X11/xorg.conf <<'XORG'
Section "Device"
    Identifier "DummyDevice"
    Driver "dummy"
    VideoRam 256000
EndSection
Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync 28.0-80.0
    VertRefresh 48.0-75.0
    Modeline "1920x1080" 172.80 1920 2048 2248 2576 1080 1083 1088 1120
EndSection
Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080"
    EndSubSection
EndSection
Section "ServerFlags"
    Option "MaxClients" "2048"
EndSection
XORG
chmod 0644 /etc/X11/xorg.conf
# Source already enables user auto-login and disables Wayland; assert that contract.
grep -Eq '^AutomaticLoginEnable=[Tt]rue' /etc/gdm3/custom.conf
grep -Eq '^AutomaticLogin=user' /etc/gdm3/custom.conf
grep -Eq '^WaylandEnable=false' /etc/gdm3/custom.conf

mkdir -p /etc/systemd/system/osworld.service.d
cat > /etc/systemd/system/osworld.service.d/desktop.conf <<'UNIT'
[Unit]
After=display-manager.service
[Service]
Environment=XAUTHORITY=/run/user/1000/gdm/Xauthority
UNIT
cat > /etc/systemd/system/x11vnc.service <<'UNIT'
[Unit]
Description=Share the OSWorld X11 desktop
After=display-manager.service
Wants=display-manager.service
[Service]
Type=simple
User=user
Environment=DISPLAY=:0
Environment=XAUTHORITY=/run/user/1000/gdm/Xauthority
ExecStart=/usr/bin/x11vnc -display :0 -auth /run/user/1000/gdm/Xauthority -rfbport 5900 -forever -shared -noxdamage -noxfixes -noxrandr -nopw
Restart=always
RestartSec=3
[Install]
WantedBy=graphical.target
UNIT
cat > /etc/systemd/system/novnc.service <<'UNIT'
[Unit]
Description=OSWorld browser desktop access
After=x11vnc.service
Wants=x11vnc.service
[Service]
Type=simple
User=user
ExecStart=/usr/bin/websockify --web=/usr/share/novnc/ 5910 localhost:5900
Restart=on-failure
RestartSec=3
[Install]
WantedBy=graphical.target
UNIT
mkdir -p /usr/local/sbin
cat > /usr/local/sbin/osworld-container-init <<'INIT'
#!/bin/sh
set -eu
chown root:root /dev/null
chmod 0666 /dev/null
size=$(df -B1 --output=size /dev/shm | tail -n 1 | tr -d ' ')
if test "$size" -lt 4294967296; then
    mount -o remount,size=4294967296 /dev/shm
fi
INIT
chmod 0755 /usr/local/sbin/osworld-container-init
cat > /etc/systemd/system/osworld-container-init.service <<'UNIT'
[Unit]
Description=Prepare desktop container runtime devices
DefaultDependencies=no
After=systemd-tmpfiles-setup-dev.service
Before=systemd-logind.service display-manager.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/osworld-container-init
RemainAfterExit=yes
[Install]
WantedBy=sysinit.target
UNIT
systemctl enable osworld.service x11vnc.service novnc.service osworld-container-init.service
rm -f /usr/sbin/policy-rc.d
rm -f /etc/ssh/ssh_host_*
rm -f /var/lib/dbus/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
truncate -s 0 /etc/machine-id
rm -f /home/user/.config/google-chrome/Singleton*
rm -f /home/user/.bash_history /root/.bash_history
rm -rf /tmp/.X11-unix/* /tmp/.com.google.Chrome.*
find /var/log -type f -exec truncate -s 0 {} +
apt-get clean
rm -rf /var/lib/apt/lists/*
chmod 1777 /tmp /var/tmp
dpkg-query -W -f='${Package} ${Version}\n' xserver-xorg-video-dummy x11vnc novnc websockify
sync
