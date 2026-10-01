import os
import syslog
import time
from struct import pack, unpack
from typing import Any

from knockknock.PacketSender import send_syn
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
        knock_port = int(profile.getKnockPort())

        id_field, seq_field, ack_field, win_field = unpack('!HIIH', packet_data)

        try:
            send_syn(host, knock_port, id_field, seq_field, ack_field, win_field)
        except (PermissionError, OSError) as e:
            syslog.syslog(f"KnockingEndpointConnection: error sending knock packet: {e}")
            os._exit(3)

        time.sleep(0.25)
