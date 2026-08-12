#!/bin/sh
set -eu

printf '%s\n' '{"ok":false,"error":{"code":"HOST_MANAGED_INSTALL","message":"zhihu-cli is bundled and managed by Officev3; repair or reinstall Officev3"}}'
exit 7
