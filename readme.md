# Self VM Build System

This repo is a very simple framework to allow for semi-automatic buildss of the Self VM on different platforms.

It uses `qemu` to boot an OS in a virtual machine, then `ssh` to run the compile.

At the moment, it builds successfully on:

- FreeBD 13.2 on x86
- NetBSD 9.3 on x86
- Debian Bookworm on x86
- Fedora 38 on x64

I'm working on NetBSD on sparc and on macppc.