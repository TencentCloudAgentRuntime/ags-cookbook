#!/nix/swerex/nix-env/bin/bash

# Ensure /bin/bash exists for scripts that expect it
if [ ! -e /bin/bash ]; then
    mkdir -p /bin
    ln -s /nix/swerex/nix-env/bin/bash /bin/bash
fi

export PATH="/nix/swerex/venv/bin:/nix/swerex/nix-env/bin:$PATH"
export SSL_CERT_FILE="/nix/swerex/nix-env/etc/ssl/certs/ca-bundle.crt"


function shutdown() {
    if kill -0 ${ENVD_PID} 2>/dev/null; then
        echo "Shutting down 'envd'..."
        kill ${ENVD_PID}
        wait ${ENVD_PID}
        echo "Service 'envd' stopped."
    fi
}

trap shutdown SIGINT SIGTERM

envd -port 49983 & ENVD_PID=$!
echo "'envd' started with PID '$ENVD_PID'."

swerex-remote --auth-token '' $@

# Call shutdown to terminate the others cleanly before exiting the script.
shutdown
