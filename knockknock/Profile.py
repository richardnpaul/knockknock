import binascii
import configparser
import os
from pathlib import Path
import stat
from typing import IO, Any, List, Optional, Union

from .CryptoEngine import CryptoEngine


class Profile:

    def __init__(
        self,
        directory: Union[str, Path],
        cipherKey: Optional[bytes] = None,
        macKey: Optional[bytes] = None,
        counter: Optional[int] = None,
        knockPort: Optional[Union[int, str]] = None,
    ) -> None:
        self.counterFile: Optional[IO[str]] = None
        self.path: Path = Path(directory)
        self.directory: str = str(self.path).rstrip('/')
        self.name: str = self.path.name
        self.ipAddressList: List[str] = []

        if cipherKey is None:
            self.deserialize()
        else:
            self.cipherKey: bytes = cipherKey
            self.macKey: bytes = macKey if macKey is not None else b""
            self.counter: int = counter if counter is not None else 0
            self.knockPort: Union[int, str] = knockPort if knockPort is not None else 0

        self.cryptoEngine = CryptoEngine(self, self.cipherKey, self.macKey, self.counter)

    def deserialize(self) -> None:
        self.cipherKey = self.loadCipherKey()
        self.macKey = self.loadMacKey()
        self.counter = self.loadCounter()
        self.knockPort = self.loadConfig()

    def serialize(self) -> None:
        self.storeCipherKey()
        self.storeMacKey()
        self.storeCounter()
        self.storeConfig()

    # Getters And Setters

    def getIPAddrs(self) -> List[str]:
        return self.ipAddressList

    def setIPAddrs(self, ipAddressList: List[str]) -> None:
        self.ipAddressList = ipAddressList

    def getName(self) -> str:
        return self.name

    def getDirectory(self) -> str:
        return self.directory

    def getKnockPort(self) -> Union[int, str]:
        return self.knockPort

    def setCounter(self, counter: int) -> None:
        self.counter = counter

    # Encrypt And Decrypt

    def decrypt(self, ciphertext: bytes, windowSize: int) -> int:
        return self.cryptoEngine.decrypt(ciphertext, windowSize)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self.cryptoEngine.encrypt(plaintext)

    # Serialization Methods

    def loadCipherKey(self) -> bytes:
        return self.loadKey(self.path / "cipher.key")

    def loadMacKey(self) -> bytes:
        return self.loadKey(self.path / "mac.key")

    def loadCounter(self) -> int:
        # Privsep bullshit...
        if self.counterFile is None:
            self.counterFile = open(self.path / "counter", 'r+')

        self.counterFile.seek(0)
        counter = self.counterFile.readline()
        counter = counter.rstrip("\n")

        return int(counter)

    def loadConfig(self) -> str:
        config = configparser.ConfigParser()
        config.read(self.path / "config")

        return config.get('main', 'knock_port')

    def loadKey(self, keyFile: Union[str, Path]) -> bytes:
        with open(keyFile, 'rb') as f:
            key = binascii.a2b_base64(f.readline())
        return key

    def storeCipherKey(self) -> None:
        self.storeKey(self.cipherKey, self.path / "cipher.key")

    def storeMacKey(self) -> None:
        self.storeKey(self.macKey, self.path / "mac.key")

    def storeCounter(self) -> None:
        # Privsep bullshit...
        if self.counterFile is None:
            self.counterFile = open(self.path / 'counter', 'w')
            self.setPermissions(self.path / 'counter')

        self.counterFile.seek(0)
        self.counterFile.write(str(self.counter) + "\n")
        self.counterFile.flush()

    def storeConfig(self) -> None:
        config = configparser.ConfigParser()
        config.add_section('main')
        config.set('main', 'knock_port', str(self.knockPort))

        config_path = self.path / "config"
        with open(config_path, 'w') as configFile:
            config.write(configFile)

        self.setPermissions(config_path)

    def storeKey(self, key: bytes, path: Union[str, Path]) -> None:
        with open(path, 'wb') as f:
            f.write(binascii.b2a_base64(key))

        self.setPermissions(path)

    # Permissions

    def setPermissions(self, path: Union[str, Path]) -> None:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    # Debug

    def printHex(self, val: Union[bytes, str]) -> None:
        for c in val:
            print("%#x" % (ord(c) if isinstance(c, str) else c), end=" ")

        print("")
