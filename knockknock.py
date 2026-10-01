#!/usr/bin/env python

import argparse
import os
from pathlib import Path
import struct
import sys
from typing import List, NoReturn, Optional, Tuple

from knockknock.PacketSender import send_syn
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


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    port, host = parseArguments(argv)
    verifyPermissions()

    profile = getProfile(host)
    packed_port = struct.pack('!H', int(port))
    packetData = profile.encrypt(packed_port)
    knockPort = int(profile.getKnockPort())

    idField, seqField, ackField, winField = struct.unpack('!HIIH', packetData)

    try:
        send_syn(host, knockPort, idField, seqField, ackField, winField)
        print('Knock sent.')
    except (PermissionError, OSError) as e:
        print(f"Error sending knock packet: {e}")
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
