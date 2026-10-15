#!/bin/bash -e
# Install the Arikizu binary, worker wheels, config, and systemd unit
# into the image rootfs.

: "${ROOTFS_DIR:?pi-gen must set ROOTFS_DIR}"
: "${STAGE_DIR:?pi-gen must set STAGE_DIR}"

FILES="${STAGE_DIR}/00-arikizu/files"

# ---- 1. Binary -------------------------------------------------------------
if [ ! -f "${FILES}/arikizu" ]; then
    echo "ERROR: ${FILES}/arikizu missing. Drop the aarch64 build in before running pi-gen."
    exit 1
fi
install -D -m 0755 "${FILES}/arikizu" "${ROOTFS_DIR}/usr/bin/arikizu"

# ---- 2. Worker wheels ------------------------------------------------------
install -d "${ROOTFS_DIR}/opt/arikizu/wheels"
if ls "${FILES}/wheels/"*.whl >/dev/null 2>&1; then
    cp "${FILES}/wheels/"*.whl "${ROOTFS_DIR}/opt/arikizu/wheels/"
else
    echo "WARNING: no worker wheels in ${FILES}/wheels; first boot will try to pip install from source."
fi

# ---- 3. Config -------------------------------------------------------------
install -d -m 0755 "${ROOTFS_DIR}/etc/arikizu/policies"
install -D -m 0644 "${FILES}/arikizu.yaml.default"       "${ROOTFS_DIR}/usr/share/arikizu/arikizu.yaml.default"
install -D -m 0644 "${FILES}/capabilities.toml.default"  "${ROOTFS_DIR}/usr/share/arikizu/capabilities.toml.default"
install -D -m 0644 "${FILES}/no-outbound.yaml"           "${ROOTFS_DIR}/etc/arikizu/policies/no-outbound.yaml"

# ---- 4. systemd unit -------------------------------------------------------
install -D -m 0644 "${FILES}/arikizu.service" "${ROOTFS_DIR}/lib/systemd/system/arikizu.service"

# ---- 5. First-boot script (creates user, copies default config) ------------
install -D -m 0755 "${FILES}/arikizu-firstboot.sh" "${ROOTFS_DIR}/usr/lib/arikizu/firstboot.sh"
install -D -m 0644 "${FILES}/arikizu-firstboot.service" "${ROOTFS_DIR}/lib/systemd/system/arikizu-firstboot.service"

# ---- 5b. Runtime auto-detect + default model scripts (called by firstboot) --
install -D -m 0755 "${FILES}/install-runtime.sh" "${ROOTFS_DIR}/usr/lib/arikizu/install-runtime.sh"
install -D -m 0755 "${FILES}/download-default-models.sh" "${ROOTFS_DIR}/usr/lib/arikizu/download-default-models.sh"

# ---- 6. mDNS + enable the service on boot ---------------------------------
on_chroot <<'EOF'
set -e
# Default hostname is arikizu — pi-gen's TARGET_HOSTNAME should already match.
systemctl enable avahi-daemon.service
systemctl enable arikizu-firstboot.service
systemctl enable arikizu.service
EOF

echo "stage-arikizu: Arikizu installed into image rootfs"
