import os
import subprocess
import sys
import time
from pathlib import Path


class BuildTarget(object):

    def __init__(self, vm_sources):
        self.vmSources = vm_sources
        self.working_dir = 'aDirectory'
        self.iso_filename = 'some.iso'
        self.iso_url = 'https://example.com/some.iso'
        self.qcow2 = 'some.qcow2'
        self.chown = 'path/to chown'
        self.env_flags = ''
        self.cmake_build_options = ''
        # Defaults for x86 on x86
        self.qemu_binary = 'qemu-system-x86_64'
        self.use_kvm = True

    #
    #   Setting Up
    #

    def install_os_in_vm(self):
        self.download_iso()
        self.create_qcow()
        # This is manual
        self.install_os()
        # Automatic from here...
        self.boot()
        self.initialise_os()
        self.poweroff()
        self.wait_for_poweroff()

    def download_iso(self):
        if not os.path.exists(self.working_dir + '/' + self.iso_filename):
            # -L option for following redirects
            os.system('curl -L ' + self.iso_url + ' > ' + self.working_dir + '/' + self.iso_filename)

    def create_qcow(self):
        if not os.path.exists(self.working_dir + '/' + self.qcow2):
            os.system('qemu-img create -f qcow2 ' + self.working_dir + '/' + self.qcow2 + ' 16G')

    def install_os(self):
        print("Running OS Installer")
        self.run_qemu(with_cdrom=True)
        # manually install OS
        # When doing setup, remember
        # (1)
        # vi /etc/ssh/sshd_config and
        # PermitRootLogin yes
        # (2)
        # install vim (for xxd)
        # (3)
        # root:Pass123
        # (4)
        # change root shell to bash
        # e.g. chsh -s /path/to/bash root
        time.sleep(10)
        self.wait_for_poweroff()

    def initialise_os(self):
        # Add packages
        pass

    #
    #   Compiling
    #

    def compile(self):
        self.sync_sources()
        self.clean_log()
        self.per_run_setup()
        self.print_system_info()
        self.cmake()
        self.build_and_test_world()
        self.extract_built_vm()
        return self

    def per_run_setup(self):
        # Things we might want to do before each run
        pass

    def run_qemu(self, with_cdrom=False):
        cmd = self.qemu_binary
        if self.use_kvm:
            cmd = cmd + " --enable-kvm "
        cmd = cmd + " -nic user,hostfwd=tcp::8888-:22 -daemonize --m 4G -boot d "
        if with_cdrom:
            cmd = cmd + '-cdrom ' + self.working_dir + '/' + self.iso_filename
        cmd = cmd + " -pidfile " + self.working_dir + '/pid '
        cmd = cmd + " -hda " + self.working_dir + '/' + self.qcow2 + ' '
        print('QEMU: ' + cmd)
        subprocess.run(cmd, shell=True)  # , capture_output=True)

    def boot(self):
        print("Removing SSH Key")
        subprocess.run(["ssh-keygen", "-f", "/home/russell/.ssh/known_hosts", "-R", "[localhost]:8888"])
        print("Booting...")
        self.run_qemu()
        # Wait for ssh
        while subprocess.run('sshpass -p Pass123 ssh root@localhost -p 8888 -o "StrictHostKeyChecking=no" true',
                             shell=True, capture_output=True).returncode > 0:
            time.sleep(1)
        print("Connected")
        return self

    def sync_sources(self):
        print("Syncing Sources")
        # ignore-times because if vm is killed, corruption of NetBSD filesystem happens,
        # so we want to make sure files are correct
        cmd = """sshpass -p Pass123 rsync --ignore-times -raz -e 'ssh -p 8888' """ + \
              self.vmSources + """ root@localhost:/self"""
        print(cmd)
        subprocess.run(cmd, shell=True)
        # Change ownership inside VM
        self.do(self.chown + " -R root /self")

    def clean_log(self):
        # Clean output file
        os.remove(self.working_dir + '/' + self.working_dir + '.out.txt')

    def print_system_info(self):
        self.do("echo ------------------------------------------------------------", silent=True)
        self.do("echo BUILDING: $(date)", silent=True)
        self.do("echo OS: $(uname -a)", silent=True)
        self.do("echo GIT: $(git --version)", silent=True)
        self.do("echo CMAKE: $(cmake --version)", silent=True)
        self.do("echo ------------------------------------------------------------", silent=True)

    def cmake(self):
        self.do("rm -rf /root/build ; mkdir /root/build")
        self.do("cd /root/build ; " + self.env_flags + "  cmake " + self.cmake_build_options + " /self")
        self.do("cd /root/build ; cmake --build .")

    def extract_built_vm(self):
        subprocess.run(
            """sshpass -p Pass123 scp -P 8888 root@localhost:/root/build/vm/Self """ + self.working_dir + """/.""",
            shell=True,
            capture_output=False)

    def build_and_test_world(self):
        self.do(
            "cd /self/objects ; echo 'tests runVMSuite. benchmarks suite do: [|:b| b printLine. b run]. _Quit' | " +
            "/root/build/vm/Self -f worldBuilder.self -o morphic")

    def poweroff(self):
        print("Shutting down")
        self.do("/sbin/shutdown -p now")
        return self

    def wait_for_poweroff(self):
        p = Path(self.working_dir + '/pid').read_text()
        while not os.system('kill -0 ' + p):
            time.sleep(1)
        os.remove(self.working_dir + '/pid')
        return self

    def wait_for_user(self):

        input("Press Enter Key to Continue...")
        return self

    #
    #   Support
    #
    def do(self, command, silent=False):
        if not silent:
            msg = "\n> " + command + '\n\n'
            print(msg)
            with open(self.working_dir + "/" + self.working_dir + ".out.txt", 'a') as f:
                f.write(msg)
        b = bytes(command, 'ascii').hex()
        c = "echo " + b + " | xxd -r -p | bash"
        subprocess.run(
            "sshpass -p Pass123 ssh root@localhost -q -p 8888 'source ~/.profile > /dev/null; " + c + "' 2>&1 | " +
            "tee -a " + self.working_dir + "/" + self.working_dir + ".out.txt",
            shell=True,
            capture_output=silent)


class NetBSD(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'NetBSD'
        self.iso_filename = 'NetBSD-9.3-i386.iso'
        self.iso_url = 'https://cdn.netbsd.org/pub/NetBSD/NetBSD-9.3/images/NetBSD-9.3-i386.iso'
        self.qcow2 = 'NetBSD-9.3-i386.qcow2'
        self.chown = '/sbin/chown'

    def initialise_os(self):
        # Add packages
        self.do('pkgin -y install rsync cmake git vim libX11 libXext bash')  # vim is for xxd

    def per_run_setup(self):
        # Turn off ASLR for clean build
        self.do("/sbin/sysctl -w security.pax.aslr.global=0")


class NetBSDmacppc(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'NetBSDmacppc'
        self.iso_filename = 'NetBSD-9.3-macppc.iso'
        self.iso_url = 'https://cdn.netbsd.org/pub/NetBSD/NetBSD-9.3/images/NetBSD-9.3-macppc.iso'
        self.qcow2 = 'NetBSD-9.3-macppc.qcow2'
        self.chown = '/sbin/chown'
        self.qemu_binary = 'qemu-system-ppc'
        self.use_kvm = False

    def initialise_os(self):
        # Add packages
        self.do('pkgin -y install rsync cmake git vim libX11 libXext bash')  # vim is for xxd

    def per_run_setup(self):
        # Turn off ASLR for clean build
        self.do("/sbin/sysctl -w security.pax.aslr.global=0")


class FreeBSD(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'FreeBSD'
        self.iso_filename = 'FreeBSD-13.1-RELEASE-i386-disc1.iso'
        self.iso_url = \
            'https://download.freebsd.org/releases/i386/i386/ISO-IMAGES/13.1/FreeBSD-13.1-RELEASE-i386-disc1.iso'
        self.qcow2 = 'FreeBSD-13.1-RELEASE-i386.qcow2'
        self.chown = '/usr/sbin/chown'
        self.env_flags = ' CC=gcc CPP=g++ '
        self.cmake_build_options = ' -DCMAKE_BUILD_TYPE=Release '

    def initialise_os(self):
        # Add packages
        self.do('pkg install -y rsync cmake git vim libX11 libXext gcc bash')  # vim is for xxd
        # So gcc works
        self.do('echo "libgcc_s.so.1		/usr/local/lib/gcc12/libgcc_s.so.1" >> /etc/libmap.conf')


class Debian(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'Debian'
        self.iso_filename = '/debian-11.6.0-i386-netinst.iso'
        self.iso_url = \
            'https://cdimage.debian.org/debian-cd/current/i386/iso-cd/debian-11.6.0-i386-netinst.iso'
        self.qcow2 = 'debian-11.6.0-i386.qcow2'
        self.chown = '/usr/bin/chown'

    def initialise_os(self):
        # Add packages
        self.do('apt install -y rsync cmake git vim build-essential xorg-dev libncurses5-dev')  # vim is for xxd

    def poweroff(self):
        print("Shutting down")
        # Capital -P
        self.do("/sbin/shutdown -P now")
        return self


if __name__ == "__main__":
    src = "/home/russell/unsynced/self/"
    # script all|target action
    # e.g. script all compile
    #    script NetBSD boot
    if len(sys.argv) == 3:
        target = sys.argv[1]
        if target == 'all':
            i = [NetBSD, FreeBSD, Debian]
        else:
            try:
                i = [getattr(sys.modules[__name__], target)]
            except AttributeError:
                print("Unknown target: " + target)
                sys.exit(1)
        action = sys.argv[2]
        if action == 'boot':
            for vm in i:
                vm(vm_sources=src).boot()
                os.system("sshpass -p Pass123 ssh root@localhost -p 8888")
                vm(vm_sources=src).poweroff().wait_for_poweroff()
        elif action == 'compile':
            for vm in i:
                vm(vm_sources=src).boot().compile().poweroff().wait_for_poweroff()
        elif action == 'install':
            for vm in i:
                vm(vm_sources=src).install_os_in_vm()
        else:
            print("Unknown action: " + action)
            sys.exit(1)
    else:
        print("Wrong! Try again! (No help for YOU!")
        sys.exit(1)
    sys.exit(0)
