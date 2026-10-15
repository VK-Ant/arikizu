#!/bin/bash -e
# pi-gen stage prerun: copy the previous stage's rootfs as the base for this one.
if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi
