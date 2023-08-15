import os
import subprocess
import sys
import time
from rich import print
from pathlib import Path
import random


class BuildTarget(object):

    def __init__(self, vm_sources: str = ''):
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
        self.vm_memory = '4G'
        self.forwarded_ssh_port = '0'
        self.bash_profile = '~/.profile'

    #
    #   Logging
    #
    @staticmethod
    def log_heading(msg: str):
        print('[bold blue]' + msg + '[/bold blue]')

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
            self.log_heading("Downloading ISO")
            # -L option for following redirects
            os.system('curl -L ' + self.iso_url + ' > ' + self.working_dir + '/' + self.iso_filename)

    def create_qcow(self):
        if not os.path.exists(self.working_dir + '/' + self.qcow2):
            self.log_heading("Creating qcow image")
            os.system('qemu-img create -f qcow2 ' + self.working_dir + '/' + self.qcow2 + ' 16G')

    def install_os(self):
        self.log_heading("Running OS Installer")
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
        self.forwarded_ssh_port = str(random.randint(10000, 65535))
        cmd = self.qemu_binary
        if self.use_kvm:
            cmd = cmd + " --enable-kvm "
        cmd = cmd + " -nic user,hostfwd=tcp::" + str(self.forwarded_ssh_port) + "-:22 -daemonize --m " + self.vm_memory + " -boot d "
        if with_cdrom:
            cmd = cmd + '-cdrom ' + self.working_dir + '/' + self.iso_filename
        cmd = cmd + " -pidfile " + self.working_dir + '/pid '
        cmd = cmd + " -hda " + self.working_dir + '/' + self.qcow2 + ' '
        print('QEMU: ' + cmd)
        subprocess.run(cmd, shell=True)  # , capture_output=True)

    def boot(self):
        self.log_heading("Removing SSH Key")
        subprocess.run(["ssh-keygen", "-f", "/home/russell/.ssh/known_hosts", "-R", "[localhost]:" + self.forwarded_ssh_port])
        self.log_heading("Booting...")
        self.run_qemu()
        # Wait for ssh
        while subprocess.run('sshpass -p Pass123 ssh -o IdentitiesOnly=yes root@localhost -p ' + self.forwarded_ssh_port + ' -o "StrictHostKeyChecking=no" true',
                             shell=True, capture_output=True).returncode > 0:
            time.sleep(1)
            print('.', end='', flush=True)
        print("Connected")
        return self

    def sync_sources(self):
        self.log_heading("Syncing Sources")
        # Full copy each time to make things more predictable
        self.do_on_qemu('rm -rf /self')
        # ignore-times because if vm is killed, corruption of NetBSD filesystem happens,
        # so we want to make sure files are correct
        cmd = """sshpass -p Pass123 rsync --ignore-times -raz -e 'ssh -o IdentitiesOnly=yes -p """ + self.forwarded_ssh_port + """' '""" + \
              self.vmSources + """' root@localhost:/self"""
        print(cmd)
        subprocess.run(cmd, shell=True)
        # Change ownership inside VM
        self.do_on_qemu(self.chown + " -R root /self")

    def clean_log(self):
        # Clean output file
        os.remove(self.working_dir + '/' + self.working_dir + '.out.txt')

    def print_system_info(self):
        self.log_heading("Build System Info")
        self.do_on_qemu("echo ------------------------------------------------------------", silent=True)
        self.do_on_qemu("echo BUILDING: $(date)", silent=True)
        self.do_on_qemu("echo OS: $(uname -a)", silent=True)
        self.do_on_qemu("echo GIT: $(git --version)", silent=True)
        self.do_on_qemu("echo CMAKE: $(cmake --version)", silent=True)
        self.do_on_qemu("echo CPP: $(cpp --version)", silent=True)
        self.do_on_qemu("echo ------------------------------------------------------------", silent=True)

    def cmake(self):
        self.do_on_qemu("rm -rf /root/build ; mkdir /root/build")
        self.do_on_qemu("cd /root/build ; " + self.env_flags + "  cmake " + self.cmake_build_options + " /self")
        self.do_on_qemu("cd /root/build ; cmake --build .")

    def extract_built_vm(self):
        subprocess.run(
            """sshpass -p Pass123 scp -o IdentitiesOnly=yes -P """ + self.forwarded_ssh_port + """ root@localhost:/root/build/vm/Self """ + self.working_dir + """/.""",
            shell=True,
            capture_output=False)

    def build_and_test_world(self):
        self.do_on_qemu(
            # --runAutomaticTests
            # "cd /self/objects ; echo 'tests runVMSuite. benchmarks measurePerformance: 100. _Quit' | " +
            "cd /self/objects ; /root/build/vm/Self -f worldBuilder.self -o morphic -headless --runAutomaticTests --snapshotActionPostRead ")

    def poweroff(self):
        self.log_heading("Telling VM to shut itself down")
        self.do_on_qemu("/sbin/shutdown -p now")
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
    def do_on_qemu(self, command, silent=False):
        if not silent:
            msg = "[green]> " + command + '[/green]'
            print(msg)
            with open(self.working_dir + "/" + self.working_dir + ".out.txt", 'a') as f:
                f.write(msg)
        b = bytes(command, 'ascii').hex()
        c = "echo " + b + " | xxd -r -p > /tmp/qemu_cmd ; bash /tmp/qemu_cmd"
        subprocess.run(
            "sshpass -p Pass123 ssh -o IdentitiesOnly=yes root@localhost -t -t -q -p " + self.forwarded_ssh_port + " 'source " + self.bash_profile + " > /dev/null; " + c + "' 2>&1 | " +
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
        self.do_on_qemu('pkgin -y install rsync cmake git vim libX11 libXext bash')  # vim is for xxd

    def per_run_setup(self):
        # Turn off ASLR for clean build
        self.do_on_qemu("/sbin/sysctl -w security.pax.aslr.global=0")


class NetBSDmacppc(BuildTarget):
    # Openfirmware:  boot cd:\ofwboot.xcg
    # Then follow NetBSD install


    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'NetBSDmacppc'
        self.iso_filename = 'NetBSD-9.3-macppc.iso'
        self.iso_url = 'https://cdn.netbsd.org/pub/NetBSD/NetBSD-9.3/images/NetBSD-9.3-macppc.iso'
        self.qcow2 = 'NetBSD-9.3-macppc.qcow2'
        self.chown = '/sbin/chown'
        self.qemu_binary = 'qemu-system-ppc -prom-env \'boot-device=hd:,ofwboot.xcf;1\' '
        self.use_kvm = False
        self.vm_memory = '1572'

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('pkgin -y install rsync cmake git vim libX11 libXext bash')  # vim is for xxd

    def per_run_setup(self):
        # Turn off ASLR for clean build
        self.do_on_qemu("/sbin/sysctl -w security.pax.aslr.global=0")


class NetBSDsparc(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'NetBSDsparc'
        self.iso_filename = 'NetBSD-9.3-sparc.iso'
        self.iso_url = 'https://cdn.netbsd.org/pub/NetBSD/NetBSD-9.3/images/NetBSD-9.3-sparc.iso'
        self.qcow2 = 'NetBSD-9.3-sparc.qcow2'
        self.chown = '/sbin/chown'
        self.qemu_binary = 'qemu-system-sparc'
        self.use_kvm = False
        self.vm_memory = '256M'

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('pkgin -y install rsync cmake git vim libX11 libXext bash')  # vim is for xxd

    def per_run_setup(self):
        # Turn off ASLR for clean build
        self.do_on_qemu("/sbin/sysctl -w security.pax.aslr.global=0")


class FreeBSD(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'FreeBSD'
        self.iso_filename = 'FreeBSD-13.2-RELEASE-i386-disc1.iso'
        self.iso_url = \
            'https://download.freebsd.org/releases/i386/i386/ISO-IMAGES/13.2/FreeBSD-13.2-RELEASE-i386-disc1.iso'
        self.qcow2 = 'FreeBSD-13.2-RELEASE-i386.qcow2'
        self.chown = '/usr/sbin/chown'
        self.env_flags = ' CC=gcc CPP=g++ '
        self.cmake_build_options = ' -DCMAKE_BUILD_TYPE=Release '

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('pkg install -y rsync cmake git xxd libX11 libXext gcc bash')
        # So gcc works
        self.do_on_qemu('echo "libgcc_s.so.1		/usr/local/lib/gcc12/libgcc_s.so.1" >> /etc/libmap.conf')


class Debian(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'Debian'
        # self.iso_filename = '/debian-11.6.0-i386-netinst.iso'
        self.iso_filename = '/debian-12.1.0-i386-netinst.iso'
        self.iso_url = \
            'https://cdimage.debian.org/debian-cd/current/i386/iso-cd/debian-12.1.0-i386-netinst.iso'
        self.qcow2 = 'debian-12.1.0-i386.qcow2'
        self.chown = '/usr/bin/chown'

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('apt install -y rsync cmake git vim build-essential xorg-dev libncurses5-dev')  # vim is for xxd

    def poweroff(self):
        self.log_heading("Shutting down")
        # Capital -P
        self.do_on_qemu("/sbin/shutdown -P now")
        return self


class Fedora64(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'Fedora64'
        self.iso_filename = 'Fedora-Workstation-Live-x86_64-38-1.6.iso'
        self.iso_url = \
            'https://download.fedoraproject.org/pub/fedora/linux/releases/38/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-38-1.6.iso'
        self.qcow2 = 'Fedora-Workstation-Live-x86_64-38-1.6.qcow2'
        self.chown = '/usr/bin/chown'
        # self.env_flags = 'CC="gcc -m32" CXX="g++ -m32"'
        self.bash_profile = '~/.bash_profile'

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('dnf -y groupinstall "Development Tools" ; dnf -y install glibc-devel.i686 libX11-devel.i686 libXext-devel.i686 ncurses-devel.i686 cmake clang')  # vim is for xxd

    def poweroff(self):
        self.log_heading("Shutting down")
        # Capital -P
        self.do_on_qemu("/sbin/shutdown -P now")
        return self


def check_for_prerequisites():
    BuildTarget().log_heading('Checking for Prerequisites...')
    r = ['git', 'sshpass', 'qemu-system-x86_64', 'curl', 'qemu-img']
    for b in r:
        if not subprocess.run('which ' + b, shell=True).returncode == 0:
            print('Could not find `' + b + '` in path.')
            sys.exit(1)


if __name__ == "__main__":
    BuildTarget().log_heading('Beginning Self-VM-Builder run...')
    check_for_prerequisites()
    src = "/media/russell/1TB Internal/self/"
    print("[bold dark_orange]Building from local source: " + src + '[/bold dark_orange]')
    # script all|target action
    # e.g. script all compile
    #    script NetBSD boot
    if len(sys.argv) == 3:
        target = sys.argv[1]
        if target == 'all':
            i = [NetBSD, FreeBSD, Debian, Fedora64]
        else:
            try:
                i = [getattr(sys.modules[__name__], target)]
            except AttributeError:
                print("Unknown target: " + target)
                sys.exit(1)
        action = sys.argv[2]
        if action == 'boot':
            for vm in i:
                v = vm(vm_sources=src).boot()
                os.system("sshpass -p Pass123 ssh -o IdentitiesOnly=yes root@localhost -p " + v.forwarded_ssh_port)
                v.poweroff().wait_for_poweroff()
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
    BuildTarget().log_heading('Task Finished')
    sys.exit(0)
