import os
import subprocess
import syslog
from typing import Any, Union

from .RuleTimer import RuleTimer


class PortOpener:

    def __init__(self, stream: Any, openDuration: Union[int, float]) -> None:
        self.stream = stream
        self.openDuration: Union[int, float] = openDuration

    def waitForRequests(self) -> None:
        while True:
            sourceIP = self.stream.readline().rstrip("\n")
            port = self.stream.readline().rstrip("\n")

            if sourceIP == "" or port == "":
                syslog.syslog("knockknock.PortOpener: Parent process is closed.  Terminating.")
                os._exit(4)

            description = (
                'INPUT -m limit --limit 1/minute --limit-burst 1 '
                '-m state --state NEW -p tcp -s '
                + sourceIP
                + ' --dport '
                + str(port)
                + ' -j ACCEPT'
            )
            command = 'iptables -I ' + description
            command_list = command.split()

            subprocess.call(command_list, shell=False)

            RuleTimer(self.openDuration, description).start()

    def open(self, sourceIP: str, port: Union[int, str]) -> None:
        try:
            self.stream.write(sourceIP + "\n")
            self.stream.write(str(port) + "\n")
            self.stream.flush()
        except Exception:
            syslog.syslog("knockknock:  Error, PortOpener process has died.  Terminating.")
            os._exit(4)
