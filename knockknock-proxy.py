#!/usr/bin/env python

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import NoReturn

import knockknock.daemonize
from knockknock.Profiles import Profiles
from knockknock.proxy.SocksRequestHandler import SocksRequestHandler


class ProxyServer:
    def __init__(self, port: int, profiles: Profiles, host: str = "127.0.0.1") -> None:
        self.port = port
        self.profiles = profiles
        self.host = host
        self.server: asyncio.Server | None = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = SocksRequestHandler(reader, writer, self.profiles)
        await handler.handle()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)

    async def serve_forever(self) -> None:
        if self.server is None:
            await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    def close(self) -> None:
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass


def usage() -> NoReturn:
    print("knockknock-proxy <listenPort>")
    sys.exit(3)


class ProxyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        usage()


def getProfiles() -> Profiles:
    homedir = Path.home()
    profiles = Profiles(str(homedir / ".knockknock/"))
    profiles.resolveNames()

    return profiles


def checkPrivileges() -> None:
    if not os.geteuid() == 0:
        print("\nSorry, knockknock-proxy has to be run as root.\n")
        usage()


def checkProfiles() -> None:
    homedir = Path.home()

    if not (homedir / ".knockknock").is_dir():
        print("Error: you need to setup your profiles in " + str(homedir) + "/.knockknock/")
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = ProxyArgumentParser(add_help=False)
    parser.add_argument("listenPort", nargs="?", type=int)

    args, extra = parser.parse_known_args(argv)
    if extra or args.listenPort is None:
        usage()

    checkPrivileges()
    checkProfiles()

    profiles = getProfiles()
    server = ProxyServer(args.listenPort, profiles)

    knockknock.daemonize.createDaemon()

    asyncio.run(server.serve_forever())


if __name__ == "__main__":
    main(sys.argv[1:])
