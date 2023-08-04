#!/usr/bin/env sh
#
# We run this as sudo so we can use KVM in qemu (assuming we're on Linux x86)
# If you don't want this, change self.use_kvm to False in compiler_framework.py
#

# -E "PATH+$PATH" will preserve the env when we are in root
sudo -E env "PATH=$PATH" poetry run python compile_framework.py "$@"