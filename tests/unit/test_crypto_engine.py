import os
from struct import pack
import pytest
from unittest.mock import MagicMock

from knockknock.CryptoEngine import CryptoEngine
from knockknock.MacFailedException import MacFailedException


class TestCryptoEngine:

    def test_init_attributes(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=5)

        assert engine.profile == mock_profile
        assert engine.cipherKey == cipher_key
        assert engine.macKey == mac_key
        assert engine.counter == 5
        assert engine.cipher is not None

    def test_calculate_mac(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=0)

        port_bytes = pack('!H', 22)
        mac1 = engine.calculateMac(port_bytes)
        mac2 = engine.calculateMac(port_bytes)

        assert isinstance(mac1, bytes)
        assert len(mac1) == 10
        assert mac1 == mac2

        # Different input produces different MAC
        different_port = pack('!H', 80)
        assert engine.calculateMac(different_port) != mac1

    def test_verify_mac_success(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=0)

        port_bytes = pack('!H', 443)
        valid_mac = engine.calculateMac(port_bytes)

        # Should execute cleanly without raising exception
        engine.verifyMac(port_bytes, valid_mac)

    def test_verify_mac_mismatch_raises_exception(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=0)

        port_bytes = pack('!H', 443)
        corrupted_mac = b"X" * 10

        with pytest.raises(MacFailedException, match="MAC Doesn't Match!"):
            engine.verifyMac(port_bytes, corrupted_mac)

    def test_encrypt_counter(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=0)

        crypt0 = engine.encryptCounter(0)
        crypt1 = engine.encryptCounter(1)

        assert isinstance(crypt0, bytes)
        assert len(crypt0) == 16
        assert len(crypt1) == 16
        assert crypt0 != crypt1

    def test_encrypt_flow_and_counter_advance(self, sample_keys):
        cipher_key, mac_key = sample_keys
        mock_profile = MagicMock()
        engine = CryptoEngine(mock_profile, cipher_key, mac_key, counter=10)

        port_bytes = pack('!H', 8080)
        ciphertext = engine.encrypt(port_bytes)

        assert isinstance(ciphertext, bytes)
        assert len(ciphertext) == 12  # 2 bytes port + 10 bytes MAC
        assert engine.counter == 11

        mock_profile.setCounter.assert_called_once_with(11)
        mock_profile.storeCounter.assert_called_once()

    def test_decrypt_exact_counter(self, sample_keys):
        cipher_key, mac_key = sample_keys
        sender_profile = MagicMock()
        receiver_profile = MagicMock()

        sender = CryptoEngine(sender_profile, cipher_key, mac_key, counter=0)
        receiver = CryptoEngine(receiver_profile, cipher_key, mac_key, counter=0)

        target_port = 22
        ciphertext = sender.encrypt(pack('!H', target_port))

        decrypted_port = receiver.decrypt(ciphertext, windowSize=5)

        assert decrypted_port == target_port
        assert receiver.counter == 1
        receiver_profile.setCounter.assert_called_once_with(1)
        receiver_profile.storeCounter.assert_called_once()

    def test_decrypt_within_sliding_window(self, sample_keys):
        cipher_key, mac_key = sample_keys
        sender_profile = MagicMock()
        receiver_profile = MagicMock()

        sender = CryptoEngine(sender_profile, cipher_key, mac_key, counter=0)
        receiver = CryptoEngine(receiver_profile, cipher_key, mac_key, counter=0)

        # Advance sender counter by 3 dropped knocks
        for _ in range(3):
            sender.encrypt(pack('!H', 1234))

        # sender counter is now 3
        assert sender.counter == 3

        target_port = 80
        valid_ciphertext = sender.encrypt(pack('!H', target_port))
        assert sender.counter == 4

        # Receiver counter is 0, window is 10 (offset x=3)
        decrypted_port = receiver.decrypt(valid_ciphertext, windowSize=10)

        assert decrypted_port == target_port
        # Receiver counter should advance to 0 + 3 + 1 = 4
        assert receiver.counter == 4
        receiver_profile.setCounter.assert_called_with(4)
        receiver_profile.storeCounter.assert_called()

    def test_decrypt_outside_window_fails(self, sample_keys):
        cipher_key, mac_key = sample_keys
        sender_profile = MagicMock()
        receiver_profile = MagicMock()

        sender = CryptoEngine(sender_profile, cipher_key, mac_key, counter=0)
        receiver = CryptoEngine(receiver_profile, cipher_key, mac_key, counter=0)

        # Advance sender by 10 knocks
        for _ in range(10):
            sender.encrypt(pack('!H', 1111))

        # Packet encrypted with counter 10
        ciphertext = sender.encrypt(pack('!H', 22))

        # Receiver windowSize is only 5 (checks counters 0..4)
        with pytest.raises(MacFailedException, match="Ciphertext failed to decrypt in range..."):
            receiver.decrypt(ciphertext, windowSize=5)

        # Receiver counter must remain untouched
        assert receiver.counter == 0

    def test_decrypt_tampered_payload_fails(self, sample_keys):
        cipher_key, mac_key = sample_keys
        sender_profile = MagicMock()
        receiver_profile = MagicMock()

        sender = CryptoEngine(sender_profile, cipher_key, mac_key, counter=0)
        receiver = CryptoEngine(receiver_profile, cipher_key, mac_key, counter=0)

        ciphertext = sender.encrypt(pack('!H', 22))

        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF  # Corrupt first byte

        with pytest.raises(MacFailedException, match="Ciphertext failed to decrypt in range..."):
            receiver.decrypt(bytes(tampered), windowSize=5)

        assert receiver.counter == 0
