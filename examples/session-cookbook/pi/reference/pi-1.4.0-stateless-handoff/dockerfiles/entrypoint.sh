#!/bin/sh
set -eu
: "${AGR_REGION:?AGR_REGION is required}"
node /opt/pi/extension/prepare.mjs
exec node /opt/pi/stateless/server.mjs
