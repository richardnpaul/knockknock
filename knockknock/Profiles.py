from pathlib import Path
import socket
from typing import List, Optional, Union

from .Profile import Profile


class Profiles:

    def __init__(self, directory: Union[str, Path]) -> None:
        self.profiles: List[Profile] = []
        dir_path = Path(directory)

        for item in sorted(dir_path.iterdir()):
            if item.is_dir():
                self.profiles.append(Profile(str(item)))

    def getProfileForPort(self, port: Union[int, str]) -> Optional[Profile]:
        for profile in self.profiles:
            if int(profile.getKnockPort()) == int(port):
                return profile

        return None

    def getProfileForName(self, name: str) -> Optional[Profile]:
        for profile in self.profiles:
            if name == profile.getName():
                return profile

        return None

    def getProfileForIP(self, ip: str) -> Optional[Profile]:
        for profile in self.profiles:
            ips = profile.getIPAddrs()

            if ip in ips:
                return profile

        return None

    def resolveNames(self) -> None:
        for profile in self.profiles:
            name = profile.getName()
            address, alias, addrlist = socket.gethostbyname_ex(name)

            profile.setIPAddrs(addrlist)

    def isEmpty(self) -> bool:
        return len(self.profiles) == 0
