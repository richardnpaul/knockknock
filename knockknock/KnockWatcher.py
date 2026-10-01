import syslog
from typing import Any

from .LogEntry import LogEntry
from .MacFailedException import MacFailedException


class KnockWatcher:
    def __init__(self, config: Any, logFile: Any, profiles: Any, portOpener: Any) -> None:
        self.config = config
        self.logFile = logFile
        self.profiles = profiles
        self.portOpener = portOpener

    def tailAndProcess(self) -> None:
        for line in self.logFile.tail():
            try:
                logEntry = LogEntry(line)
                profile = self.profiles.getProfileForPort(logEntry.getDestinationPort())

                if profile is not None:
                    try:
                        ciphertext = logEntry.getEncryptedData()
                        port = profile.decrypt(ciphertext, self.config.getWindow())
                        sourceIP = logEntry.getSourceIP()

                        self.portOpener.open(sourceIP, port)
                        syslog.syslog("Received authenticated port-knock for port " + str(port) + " from " + sourceIP)
                    except MacFailedException:
                        pass
            except Exception:
                syslog.syslog("knocknock skipping unrecognized line.")
