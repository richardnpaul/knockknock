import hashlib
import hmac
import struct
from typing import TYPE_CHECKING, Any

from Crypto.Cipher import AES

from .MacFailedException import MacFailedException

if TYPE_CHECKING:
    pass


class CryptoEngine:
    def __init__(self, profile: Any, cipherKey: bytes, macKey: bytes, counter: int) -> None:
        self.profile = profile
        self.counter: int = counter
        self.macKey: bytes = macKey
        self.cipherKey: bytes = cipherKey
        self.cipher = AES.new(self.cipherKey, AES.MODE_ECB)

    def calculateMac(self, port: bytes) -> bytes:
        hmacSha = hmac.new(self.macKey, port, hashlib.sha1)
        mac = hmacSha.digest()
        return mac[:10]

    def verifyMac(self, port: bytes, remoteMac: bytes) -> None:
        localMac = self.calculateMac(port)

        if not hmac.compare_digest(localMac, remoteMac):
            raise MacFailedException("MAC Doesn't Match!")

    def encryptCounter(self, counter: int) -> bytes:
        counterBytes = struct.pack("!IIII", 0, 0, 0, counter)
        return self.cipher.encrypt(counterBytes)

    def encrypt(self, plaintextData: bytes) -> bytes:
        plaintextData += self.calculateMac(plaintextData)
        counterCrypt = self.encryptCounter(self.counter)
        self.counter = self.counter + 1
        encrypted = bytes(b1 ^ b2 for b1, b2 in zip(plaintextData, counterCrypt))

        self.profile.setCounter(self.counter)
        self.profile.storeCounter()

        return encrypted

    def decrypt(self, encryptedData: bytes, windowSize: int) -> int:
        for x in range(windowSize):
            try:
                counterCrypt = self.encryptCounter(self.counter + x)
                decrypted = bytes(b1 ^ b2 for b1, b2 in zip(encryptedData, counterCrypt))

                port = decrypted[:2]
                mac = decrypted[2:]

                self.verifyMac(port, mac)
                self.counter += x + 1

                self.profile.setCounter(self.counter)
                self.profile.storeCounter()

                return int(struct.unpack("!H", port)[0])

            except MacFailedException:
                pass

        raise MacFailedException("Ciphertext failed to decrypt in range...")
