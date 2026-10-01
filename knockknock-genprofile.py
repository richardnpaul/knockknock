#!/usr/bin/env python

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

from knockknock.Profile import Profile
from knockknock.Profiles import Profiles

DAEMON_PATH = Path("/etc/knockknock.d")
PROFILES_PATH = DAEMON_PATH / "profiles"


def usage() -> NoReturn:
    print("knockknock-genprofile <profileName> <knockPort>")
    sys.exit(3)


class GenProfileArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        usage()


def checkProfile(profileName: str) -> None:
    profile_dir = PROFILES_PATH / profileName
    if profile_dir.is_dir():
        print("Profile already exists.  First rm " + str(profile_dir) + "/")
        sys.exit(0)


def checkPortConflict(knockPort: str) -> None:
    if not PROFILES_PATH.is_dir():
        return

    profiles = Profiles(PROFILES_PATH)
    matchingProfile = profiles.getProfileForPort(knockPort)

    if matchingProfile is not None:
        print(
            "A profile already exists for knock port: "
            + str(knockPort)
            + " at this location: "
            + matchingProfile.getDirectory()
        )


def createDirectory(profileName: str) -> None:
    if not DAEMON_PATH.is_dir():
        DAEMON_PATH.mkdir(parents=True, exist_ok=True)

    if not PROFILES_PATH.is_dir():
        PROFILES_PATH.mkdir(parents=True, exist_ok=True)

    target_dir = PROFILES_PATH / profileName
    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = GenProfileArgumentParser(add_help=False)
    parser.add_argument("profileName", nargs="?")
    parser.add_argument("knockPort", nargs="?")

    args, extra = parser.parse_known_args(argv)
    if extra or not args.profileName or not args.knockPort:
        usage()

    profileName = args.profileName
    knockPort = args.knockPort

    checkProfile(profileName)
    checkPortConflict(knockPort)
    createDirectory(profileName)

    cipherKey = os.urandom(16)
    macKey = os.urandom(16)
    counter = 0

    profile_dir = PROFILES_PATH / profileName
    profile = Profile(str(profile_dir), cipherKey, macKey, counter, knockPort)
    profile.serialize()

    print("Keys successfully generated in " + str(profile_dir))


if __name__ == "__main__":
    main(sys.argv[1:])
