import os
import subprocess
import sys
import time
from rich import print
from pathlib import Path
import random
import multiprocessing


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
        self.silent = False

    #
    #   Logging
    #


    def set_silent(self):
        self.silent = True
        return self

    def log_heading(self, msg: str):
        if not self.silent:
            print('[bold blue]' + msg + '[/bold blue]')
        with open(self.log_filename(), "a") as f:
            f.write('#### ' + msg + '\n')

    def log_note(self, msg: str):
        if not self.silent:
            print(msg)
        with open(self.log_filename(), "a") as f:
            f.write(msg + '\n')

    def log_filename(self) -> str:
        return self.working_dir + '/' + self.working_dir + '.out.txt'

    def clean_log(self):
        # Clean output file
        os.remove(self.log_filename())

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

    def compile_summary(self):
        self.silent = True
        self.compile()
        return self

    def print_summary(self):
        s = self.silent
        self.silent = False
        self.log_heading('Summary')
        #
        #   Was binary generated?
        #
        successful_build = False
        with open(self.log_filename(), "r") as f:
            successful_build = 'Built target Self' in f.read()
        if successful_build:
            self.log_note('[bold green]VM Built OK[/bold green]')
        else:
            self.log_note('[bold red]VM Build Failed[/bold red]')
        #
        #   Did tests run?
        #
        successful_test = False
        with open(self.log_filename(), "r") as f:
            successful_test = '---END-OF-TESTS---' in f.read()
        if successful_test:
            self.log_note('[bold green]VM Tested OK[/bold green]')
        else:
            self.log_note('[bold red]VM Tests Failed[/bold red]')
        self.silent = s
        return self

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
        self.log_note('QEMU: ' + cmd)
        subprocess.run(cmd, shell=True, capture_output=self.silent)

    def boot(self):
        self.log_heading("Removing SSH Key")
        subprocess.run(["ssh-keygen", "-f", "/home/russell/.ssh/known_hosts", "-R", "[localhost]:" + self.forwarded_ssh_port], capture_output=self.silent)
        self.log_heading("Booting...")
        self.run_qemu()
        # Wait for ssh
        while subprocess.run('sshpass -p Pass123 ssh -o IdentitiesOnly=yes root@localhost -p ' + self.forwarded_ssh_port + ' -o "StrictHostKeyChecking=no" true',
                             shell=True, capture_output=True).returncode > 0:
            time.sleep(1)
            print('.', end='', flush=True) if not self.silent else True
        self.log_note("Connected")
        return self

    def sync_sources(self):
        self.log_heading("Syncing Sources")
        # Full copy each time to make things more predictable
        self.do_on_qemu('rm -rf /self')
        # ignore-times because if vm is killed, corruption of NetBSD filesystem happens,
        # so we want to make sure files are correct
        cmd = """sshpass -p Pass123 rsync --ignore-times -raz -e 'ssh -o IdentitiesOnly=yes -p """ + self.forwarded_ssh_port + """' '""" + \
              self.vmSources + """' root@localhost:/self"""
        self.log_note(cmd)
        subprocess.run(cmd, shell=True)
        # Change ownership inside VM
        self.do_on_qemu(self.chown + " -R root /self")


    def print_system_info(self):
        # For Summary - print this out even if silent
        s = self.silent
        self.silent = False
        self.log_heading("Build System Info")
        self.do_on_qemu("echo $(date)")
        self.do_on_qemu("echo $(uname -a)")
        self.do_on_qemu("echo $(git --version)")
        self.do_on_qemu("echo $(cmake --version)")
        self.do_on_qemu("echo $(gcc --version)")
        self.do_on_qemu("echo $(g++ --version)")
        self.silent = s

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
        while not subprocess.run('kill -0 ' + p, shell=True, capture_output=True):
            time.sleep(1)
        os.remove(self.working_dir + '/pid')
        return self

    def wait_for_user(self):
        input("Press Enter Key to Continue...")
        return self

    #
    #   Support
    #
    def do_on_qemu(self, command):
        self.log_note("[green]> " + command + '[/green]')
        b = bytes(command, 'ascii').hex()
        c = "echo " + b + " | xxd -r -p > /tmp/qemu_cmd ; bash /tmp/qemu_cmd"
        subprocess.run(
            "sshpass -p Pass123 ssh -o IdentitiesOnly=yes root@localhost -t -t -q -p " + self.forwarded_ssh_port + " 'source " + self.bash_profile + " > /dev/null; " + c + "' 2>&1 | " +
            "tee -a " + self.log_filename(),
            shell=True,
            capture_output=self.silent)


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
        # self.iso_filename = 'FreeBSD-13.2-RELEASE-i386-disc1.iso'
        # self.iso_url = \
        #     'https://download.freebsd.org/releases/i386/i386/ISO-IMAGES/13.2/FreeBSD-13.2-RELEASE-i386-disc1.iso'
        # self.qcow2 = 'FreeBSD-13.2-RELEASE-i386.qcow2'
        self.iso_filename = 'FreeBSD-14.0-RELEASE-i386-disc1.iso'
        self.iso_url = \
            'https://download.freebsd.org/releases/i386/i386/ISO-IMAGES/14.0/FreeBSD-14.0-RELEASE-i386-disc1.iso'
        self.qcow2 = 'FreeBSD-14.0-RELEASE-i386.qcow2'
        self.chown = '/usr/sbin/chown'
        self.env_flags = ' CC=gcc CPP=g++ '
        self.cmake_build_options = ' -DCMAKE_BUILD_TYPE=Release '

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('pkg install -y rsync cmake git xxd libX11 libXext gcc bash')
        # So gcc works
        self.do_on_qemu('echo "libgcc_s.so.1  /usr/local/lib/gcc12/libgcc_s.so.1" >> /etc/libmap.conf')


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

class Debian64(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'Debian64'
        self.iso_filename = 'debian-12.1.0-amd64-netinst.iso'
        self.iso_url = \
            'https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.1.0-amd64-netinst.iso'
        self.qcow2 = 'debian-12.1.0-amd64.qcow2'
        self.chown = '/usr/bin/chown'

    def initialise_os(self):
        # Add packages
        self.do_on_qemu('apt update')
        self.do_on_qemu('apt install -y rsync cmake git xxd build-essential libx11-dev:i386 libxext-dev:i386 libncurses-dev:i386 libx32stdc++-12-dev libc6-dev-i386-cross')

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
    r = ['git', 'sshpass', 'qemu-system-x86_64', 'curl', 'qemu-img']
    for b in r:
        if not subprocess.run('which ' + b, shell=True, capture_output=True).returncode == 0:
            print('While checking for prerequisites, could not find `' + b + '` in path.')
            sys.exit(1)


def compile_to_summary(vm):
    return vm.set_silent().boot().compile_summary().poweroff().wait_for_poweroff()


if __name__ == "__main__":
    print('Beginning Self-VM-Builder run...')
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
        elif action == 'install':
            for vm in i:
                vm(vm_sources=src).install_os_in_vm()
        elif action == 'compile':
            for vm in i:
                vm(vm_sources=src).boot().compile().poweroff().wait_for_poweroff()
        elif action == 'summary':
            for vm in i:
                vmi = vm(vm_sources=src) # Instantiate it
                #  Run for 10 minutes, then kill if not finished
                p = multiprocessing.Process(target=compile_to_summary,
                                            args=( vmi, ))
                p.start()
                p.join(10*60)
                if p.is_alive(): p.kill()
                vmi.print_summary()
        else:
            print("Unknown action: " + action)
            sys.exit(1)
    else:
        print("Wrong! Try again! (No help for YOU!")
        sys.exit(1)
    print('Task Finished')
    sys.exit(0)
