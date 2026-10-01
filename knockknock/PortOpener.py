import os
import shutil
import subprocess
import syslog
from collections.abc import Callable
from typing import Any, Union


class PortOpener:
    def __init__(
        self,
        stream: Any,
        openDuration: Union[int, float],
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self.stream = stream
        self.openDuration: Union[int, float] = openDuration
        self.on_exit = on_exit
        nft_bin = shutil.which("nft")
        self.nft_path: str = nft_bin if nft_bin else "nft"

    @staticmethod
    def _is_valid_ipv4(ip: str) -> bool:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            if str(int(part)) != part:
                return False
            if int(part) > 255:
                return False
        return True

    @staticmethod
    def _is_valid_port(port_str: str) -> bool:
        if not port_str.isdigit():
            return False
        val = int(port_str)
        return 1 <= val <= 65535

    def _terminate(self, msg: str) -> None:
        syslog.syslog(msg)
        if self.on_exit is not None:
            self.on_exit()
        os._exit(4)

    def waitForRequests(self) -> None:
        while True:
            sourceIP = self.stream.readline().rstrip("\n")
            port = self.stream.readline().rstrip("\n")

            if sourceIP == "" or port == "":
                self._terminate("knockknock.PortOpener: Parent process is closed.  Terminating.")

            if not self._is_valid_ipv4(sourceIP):
                self._terminate("knockknock.PortOpener: Invalid source IP received.  Terminating.")

            if not self._is_valid_port(port):
                self._terminate("knockknock.PortOpener: Invalid port received.  Terminating.")

            duration = int(self.openDuration)
            element = f"{{ {sourceIP} . {port} timeout {duration}s }}"
            command_list = [
                self.nft_path,
                "add",
                "element",
                "inet",
                "knockknock",
                "open_ports",
                element,
            ]

            subprocess.call(command_list, shell=False)

    def open(self, sourceIP: str, port: Union[int, str]) -> None:
        try:
            self.stream.write(sourceIP + "\n")
            self.stream.write(str(port) + "\n")
            self.stream.flush()
        except Exception:
            syslog.syslog("knockknock:  Error, PortOpener process has died.  Terminating.")
            os._exit(4)
