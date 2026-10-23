#!/bin/sh
# Check that a DSH image matches the versions this plugin is built for.
# Usage: docker run --rm --platform linux/amd64 --entrypoint sh -v "$PWD/check-dsh-image.sh:/check.sh:ro" <image> /check.sh
ok() { echo "OK    $1"; }
bad() { echo "FAIL  $1"; fail=1; }

command -v npm >/dev/null && ok "npm $(npm -v)" || bad "npm not found"
case "$(node -v 2>/dev/null)" in
  v24.*) ok "Node.js $(node -v)" ;;
  *) echo "WARN  Node.js $(node -v 2>/dev/null || echo 'not installed'); this example is verified on Node.js 24 only" ;;
esac

root="$(npm root -g 2>/dev/null)/@deepseek-ai"
dsh="$root/dsh"
if [ -f "$dsh/package.json" ]; then
  version=$(node -p "require('$dsh/package.json').version")
  [ "$version" = 0.2.1-rc.2 ] && ok "@deepseek-ai/dsh $version" || bad "@deepseek-ai/dsh must be 0.2.1-rc.2, found $version"
else
  bad "@deepseek-ai/dsh not found under $root"
fi
command -v dsh >/dev/null && ok "dsh command on PATH" || bad "dsh command not on PATH"

# npm 11 installs DSH's packages under the dsh package; older layouts keep them beside it.
modules="$dsh/node_modules/@deepseek-ai"
[ -d "$modules/cordis" ] || modules="$root"
echo "INFO  DSH_MODULES=$modules"
for pair in cordis:4.0.5 dsh-session:0.2.1-rc.2 dsh-session-persistence:0.2.1-rc.2 schemastery:3.18.5; do
  name=${pair%%:*}
  want=${pair#*:}
  have=$(node -p "require('$modules/$name/package.json').version" 2>/dev/null) || have="not installed"
  [ "$have" = "$want" ] && ok "@deepseek-ai/$name $have" || bad "@deepseek-ai/$name must be $want, found $have"
done
exit ${fail:-0}
