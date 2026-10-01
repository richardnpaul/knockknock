#!/usr/bin/env python
"""knockknock-daemon implements Moxie Marlinspike's port knocking protocol."""

import argparse
import grp
import os
from pathlib import Path
import pwd
import signal
import sys
from typing import IO, Any, List, NoReturn, Optional

from knockknock.DaemonConfiguration import DaemonConfiguration
from knockknock.KnockWatcher import KnockWatcher
from knockknock.LogFile import LogFile
from knockknock.NftSetup import NftSetup
from knockknock.PortOpener import PortOpener
from knockknock.Profiles import Profiles
import knockknock.daemonize

DAEMON_PATH = Path('/etc/knockknock.d')
PROFILES_PATH = DAEMON_PATH / 'profiles'


def usage() -> NoReturn:
    print("knockknock-daemon")
    sys.exit(3)


class DaemonArgumentParser(argparse.ArgumentParser):

    def error(self, message: str) -> NoReturn:
        usage()


def checkPrivileges() -> None:
    if not os.geteuid() == 0:
        print("Sorry, you have to run knockknock-daemon as root.")
        sys.exit(3)


def checkConfiguration() -> None:
    if not DAEMON_PATH.is_dir():
        print("/etc/knockknock.d/ does not exist.  You need to setup your profiles first..")
        sys.exit(3)

    if not PROFILES_PATH.is_dir():
        print("/etc/knockknock.d/profiles/ does not exist.  You need to setup your profiles first...")
        sys.exit(3)


def dropPrivileges() -> None:
    nobody = pwd.getpwnam('nobody')
    adm = grp.getgrnam('adm')

    os.setgroups([adm.gr_gid])
    os.setgid(adm.gr_gid)
    os.setuid(nobody.pw_uid)


def handleFirewall(input_stream: IO[str], config: DaemonConfiguration) -> None:
    nft_setup = NftSetup()
    nft_setup.initialise()

    def teardown_handler(signum: int, frame: Any) -> None:
        nft_setup.teardown()
        os._exit(0)

    signal.signal(signal.SIGTERM, teardown_handler)
    signal.signal(signal.SIGINT, teardown_handler)

    try:
        portOpener = PortOpener(input_stream, config.getDelay(), on_exit=nft_setup.teardown)
        portOpener.waitForRequests()
    finally:
        nft_setup.teardown()


def handleKnocks(output_stream: IO[str], profiles: Profiles, config: DaemonConfiguration) -> None:
    dropPrivileges()

    logFile = LogFile('/var/log/kern.log')
    portOpener = PortOpener(output_stream, config.getDelay())
    knockWatcher = KnockWatcher(config, logFile, profiles, portOpener)

    knockWatcher.tailAndProcess()


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = DaemonArgumentParser(add_help=False)
    args, extra = parser.parse_known_args(argv)
    if extra:
        usage()

    checkPrivileges()
    checkConfiguration()

    profiles = Profiles(str(PROFILES_PATH))
    config = DaemonConfiguration(str(DAEMON_PATH / 'config'))

    if profiles.isEmpty():
        print('WARNING: Running knockknock-daemon without any active profiles.')

    knockknock.daemonize.createDaemon()

    input_fd, output_fd = os.pipe()
    pid = os.fork()

    if pid:
        os.close(input_fd)
        handleKnocks(os.fdopen(output_fd, 'w'), profiles, config)
    else:
        os.close(output_fd)
        handleFirewall(os.fdopen(input_fd, 'r'), config)


if __name__ == '__main__':
    main(sys.argv[1:])
