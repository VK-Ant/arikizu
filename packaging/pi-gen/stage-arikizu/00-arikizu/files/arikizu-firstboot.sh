#!/bin/bash -e
# First-boot: user, config, worker venv, GPU auto-detect + runtime install,
# default model fetch. Then disable this unit so it never runs again.

STATE_DIR=/var/lib/arikizu
VENV=/opt/arikizu/venv
WHEELS=/opt/arikizu/wheels
MODELS_DIR="$STATE_DIR/models"

log() { echo "[firstboot] $*"; }

# 1. User and state dir
if ! getent passwd arikizu >/dev/null; then
    adduser --system --home "$STATE_DIR" --no-create-home \
            --group --disabled-password --disabled-login --quiet arikizu
fi
install -d -o arikizu -g arikizu "$STATE_DIR" "$MODELS_DIR"
install -d -o arikizu -g arikizu /run/arikizu

# 2. Config (idempotent)
if [ ! -f /etc/arikizu/arikizu.yaml ]; then
    cp /usr/share/arikizu/arikizu.yaml.default /etc/arikizu/arikizu.yaml
fi
if [ ! -f /etc/arikizu/capabilities.toml ]; then
    cp /usr/share/arikizu/capabilities.toml.default /etc/arikizu/capabilities.toml
fi
chown -R arikizu:arikizu /etc/arikizu

# 3. Worker venv from pre-built wheels (offline-safe)
if [ ! -d "$VENV" ]; then
    log "creating worker venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-index --find-links "$WHEELS" \
        arikizu_worker_sdk \
        test_worker vision_worker audio_worker docs_worker \
        reasoning_worker timeseries_worker memory_worker guard_worker eval_worker \
        2>/dev/null || log "worker wheel install had errors (continuing)"
fi

# 4. GPU auto-detect + install matching ONNX runtime (needs network)
if [ -x /usr/lib/arikizu/install-runtime.sh ]; then
    log "running install-runtime.sh (GPU auto-detect)"
    PYTHON="$VENV/bin/python" /usr/lib/arikizu/install-runtime.sh || \
        log "install-runtime.sh had errors (continuing)"
fi

# 5. Default model fetch (needs network)
if [ -x /usr/lib/arikizu/download-default-models.sh ]; then
    if [ ! -f "$MODELS_DIR/yolov8n.onnx" ]; then
        log "downloading default models to $MODELS_DIR"
        ARIKIZU_MODELS_DIR="$MODELS_DIR" /usr/lib/arikizu/download-default-models.sh || \
            log "model download failed (continuing; worker will use placeholders)"
    fi
fi
chown -R arikizu:arikizu "$MODELS_DIR"

# 6. Disable this unit so it never runs again.
systemctl disable arikizu-firstboot.service
log "firstboot complete"
