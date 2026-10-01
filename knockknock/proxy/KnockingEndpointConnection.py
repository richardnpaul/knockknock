import os
import subprocess
import time
from struct import pack, unpack
from typing import Any

from .EndpointConnection import EndpointConnection


class KnockingEndpointConnection(EndpointConnection):

    def __init__(self, shuttle: Any, profile: Any, host: str, port: int) -> None:
        self.profile = profile
        self.host = host
        self.port = port

        self.sendKnock(profile, host, port)
        super().__init__(shuttle, host, port)

    def reconnect_hook(self) -> None:
        self.sendKnock(self.profile, self.host, self.port)

    def reconnect(self) -> None:
        self.sendKnock(self.profile, self.host, self.port)
        super().reconnect()

    def sendKnock(self, profile: Any, host: str, port: int) -> None:
        packed_port = pack('!H', int(port))
        packet_data = profile.encrypt(packed_port)
        knock_port = profile.getKnockPort()

        id_field, seq_field, ack_field, win_field = unpack('!HIIH', packet_data)

        command = [
            "hping3", "-q", "-S", "-c", "1",
            "-p", str(knock_port),
            "-N", str(id_field),
            "-w", str(win_field),
            "-M", str(seq_field),
            "-L", str(ack_field),
            host,
        ]

        with open(os.devnull, 'w') as devnull:
            subprocess.call(command, shell=False, stdout=devnull, stderr=subprocess.STDOUT)
        time.sleep(0.25)
