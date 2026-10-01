#!/usr/bin/env python

import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
from typing import List, NoReturn, Optional, Tuple

from knockknock.Profile import Profile


def usage() -> NoReturn:
    print("Usage: knockknock.py -p <portToOpen> <host>")
    sys.exit(2)


class KnockArgumentParser(argparse.ArgumentParser):

    def error(self, message: str) -> NoReturn:
        usage()


def parseArguments(argv: List[str]) -> Tuple[int, str]:
    parser = KnockArgumentParser(add_help=False)
    parser.add_argument("-p", dest="port", type=int, default=0)
    parser.add_argument("host", nargs="?", default="")

    args, extra = parser.parse_known_args(argv)
    if extra or args.port <= 0 or not args.host:
        usage()

    return args.port, args.host


def getProfile(host: str) -> Profile:
    homedir = Path.home()
    knock_dir = homedir / ".knockknock"

    if not knock_dir.is_dir():
        print("Error: you need to setup your profiles in " + str(homedir) + '/.knockknock/')
        sys.exit(2)

    host_profile_dir = knock_dir / host
    if not host_profile_dir.is_dir():
        print('Error: profile for host ' + host + ' not found at ' + str(host_profile_dir))
        sys.exit(2)

    return Profile(str(host_profile_dir))


def verifyPermissions() -> None:
    if os.getuid() != 0:
        print('Sorry, you must be root to run this.')
        sys.exit(2)


def existsInPath(command: str) -> Optional[str]:
    def isExe(fpath: Path) -> bool:
        return fpath.is_file() and os.access(fpath, os.X_OK)

    for path_str in os.environ.get("PATH", "").split(os.pathsep):
        exe_file = Path(path_str) / command
        if isExe(exe_file):
            return str(exe_file)

    return None


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    port, host = parseArguments(argv)
    verifyPermissions()

    profile = getProfile(host)
    packed_port = struct.pack('!H', int(port))
    packetData = profile.encrypt(packed_port)
    knockPort = profile.getKnockPort()

    idField, seqField, ackField, winField = struct.unpack('!HIIH', packetData)

    hping = existsInPath("hping3")
    if hping is None:
        print("Error, you must install hping3 first.")
        sys.exit(2)

    command = [
        hping, "-S", "-c", "1",
        "-p", str(knockPort),
        "-N", str(idField),
        "-w", str(winField),
        "-M", str(seqField),
        "-L", str(ackField),
        host,
    ]

    try:
        with open('/dev/null', 'w') as devnull:
            subprocess.call(command, shell=False, stdout=devnull, stderr=subprocess.STDOUT)
        print('Knock sent.')

    except OSError:
        print("Error: Do you have hping3 installed?")
        sys.exit(3)


if __name__ == '__main__':
    main(sys.argv[1:])
