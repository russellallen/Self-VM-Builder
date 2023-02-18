import os
import subprocess
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
        self.cmake_flags = ''

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
        self.print_system_info()
        self.cmake()
        self.build_and_test_world()
        self.extract_built_vm()
        return self

    def run_qemu(self, with_cdrom=False):
        cmd = "qemu-system-x86_64 --enable-kvm -nic user,hostfwd=tcp::8888-:22 -daemonize --m 4G -boot d "
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
        self.do("echo ---------------------------------------------------------------------------------")
        self.do("echo BUILDING: $(date)")
        self.do("echo OS: $(uname -a)")
        self.do("echo GIT: $(git --version)")
        self.do("echo CMAKE: $(cmake --version)")
        self.do("echo ---------------------------------------------------------------------------------")

    def cmake(self):
        self.do("rm -rf /root/build")
        self.do("mkdir /root/build")
        self.do("cd /root/build ; " + self.cmake_flags + " cmake -DCMAKE_BUILD_TYPE=Release /self")
        self.do("export PATH=$PATH:/sbin:/usr/sbin ; cd /root/build ; cmake --build .")

    def extract_built_vm(self):
        subprocess.run(
            """sshpass -p Pass123 scp -P 8888 root@localhost:/root/build/vm/Self """ + self.working_dir + """/.""",
            shell=True,
            capture_output=False)

    def build_and_test_world(self):
        self.do(
            "cd /self/objects ; echo 'benchmarks suite do: [|:b| b printLine. b run]. _Quit' | " +
            "/root/build/vm/Self -f worldBuilder.self -o morphic")

    def open_ssh(self):
        self.do('/bin/sh', silent=False)

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
        msg = "\n> " + command + '\n\n'
        print(msg)
        with open(self.working_dir + "/" + self.working_dir + ".out.txt", 'a') as f:
            f.write(msg)
        b = bytes(command, 'ascii').hex()
        c = "echo " + b + " | xxd -r -p | /bin/sh"
        subprocess.run(
            "sshpass -p Pass123 ssh root@localhost -p 8888 '" + c + "' 2>&1 | " +
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
        self.do('pkgin -y install rsync cmake git vim libX11 libXext')  # vim is for xxd


class FreeBSD(BuildTarget):

    def __init__(self, vm_sources):
        super().__init__(vm_sources)
        self.vm_sources = vm_sources
        self.working_dir = 'FreeBSD'
        self.iso_filename = 'FreeBSD-13.1-RELEASE-i386-disc1.iso'
        self.iso_filename = 'FreeBSD-13.1-RELEASE-i386-disc1.iso'
        self.iso_url = \
            'https://download.freebsd.org/releases/i386/i386/ISO-IMAGES/13.1/FreeBSD-13.1-RELEASE-i386-disc1.iso'
        self.qcow2 = 'FreeBSD-13.1-RELEASE-i386.qcow2'
        self.chown = '/usr/sbin/chown'
        self.cmake_flags = ' CC=gcc CPP=g++ '

    def initialise_os(self):
        # Add packages
        self.do('pkg install -y rsync cmake git vim libX11 libXext gcc')  # vim is for xxd
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


def main():
    src = "/home/russell/unsynced/nbuwe/self/git/"
    for i in [FreeBSD]:  # NetBSD, FreeBSD, Debian]:
        # i(vm_sources=src).install_os_in_vm()
        i(vm_sources=src).boot().compile().wait_for_user().poweroff().wait_for_poweroff()


if __name__ == "__main__":
    main()
