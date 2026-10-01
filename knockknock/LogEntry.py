import struct
from typing import Dict


class LogEntry:

    def __init__(self, line: str) -> None:
        self.tokenMap: Dict[str, str] = {}
        self.buildTokenMap(line)

    def buildTokenMap(self, line: str) -> None:
        self.tokenMap = {}

        for token in line.split():
            index = token.find("=")
            if index != -1:
                exploded = token.split('=')
                self.tokenMap[exploded[0]] = exploded[1]

    def getDestinationPort(self) -> int:
        return int(self.tokenMap['DPT'])

    def getEncryptedData(self) -> bytes:
        return struct.pack(
            '!HIIH',
            int(self.tokenMap['ID']),
            int(self.tokenMap['SEQ']),
            int(self.tokenMap['ACK']),
            int(self.tokenMap['WINDOW']),
        )

    def getSourceIP(self) -> str:
        return self.tokenMap['SRC']
