import os
import stat
from struct import pack
import pytest

from knockknock.Profile import Profile


class TestProfile:

    def test_init_with_keys_and_serialize(self, temp_dir, sample_keys):
        cipher_key, mac_key = sample_keys
        profile = Profile(
            directory=temp_dir,
            cipherKey=cipher_key,
            macKey=mac_key,
            counter=0,
            knockPort=7777
        )

        assert profile.getName() == os.path.basename(temp_dir)
        assert profile.getDirectory() == temp_dir
        assert profile.getKnockPort() == 7777
        assert profile.cipherKey == cipher_key
        assert profile.macKey == mac_key
        assert profile.counter == 0

        profile.serialize()

        # Verify files exist on disk
        for filename in ["cipher.key", "mac.key", "counter", "config"]:
            file_path = os.path.join(temp_dir, filename)
            assert os.path.isfile(file_path)
            file_mode = stat.S_IMODE(os.stat(file_path).st_mode)
            assert file_mode == (stat.S_IRUSR | stat.S_IWUSR)

    def test_deserialize_from_disk(self, temp_dir, sample_keys):
        cipher_key, mac_key = sample_keys
        original = Profile(
            directory=temp_dir,
            cipherKey=cipher_key,
            macKey=mac_key,
            counter=42,
            knockPort=8888
        )
        original.serialize()

        # Load from disk without passing keys
        loaded = Profile(temp_dir)

        assert loaded.cipherKey == cipher_key
        assert loaded.macKey == mac_key
        assert loaded.counter == 42
        assert loaded.getKnockPort() == "8888"
        assert loaded.getName() == os.path.basename(temp_dir)

    def test_store_and_load_counter(self, temp_dir, sample_keys):
        cipher_key, mac_key = sample_keys
        profile = Profile(temp_dir, cipher_key, mac_key, counter=0, knockPort=7000)
        profile.serialize()

        profile.setCounter(100)
        profile.storeCounter()

        # Re-read counter directly via loadCounter
        loaded_profile = Profile(temp_dir)
        assert loaded_profile.loadCounter() == 100

        # Updating counter again via open file handle
        profile.setCounter(101)
        profile.storeCounter()
        assert profile.counter == 101

    def test_ip_addrs_getter_and_setter(self, sample_profile):
        ips = ["192.168.1.50", "10.0.0.1"]
        sample_profile.setIPAddrs(ips)
        assert sample_profile.getIPAddrs() == ips

    def test_encrypt_and_decrypt_wrappers(self, sample_profile):
        port = 22
        packed_port = pack('!H', port)

        ciphertext = sample_profile.encrypt(packed_port)
        assert isinstance(ciphertext, bytes)
        assert len(ciphertext) == 12

        # In sample_profile, counter became 1 after encrypt.
        # To decrypt on sample_profile, reset its crypto counter
        sample_profile.cryptoEngine.counter = 0
        decrypted = sample_profile.decrypt(ciphertext, windowSize=5)
        assert decrypted == port

    def test_print_hex(self, sample_profile, capsys):
        sample_profile.printHex(b"\x0a\x0b")
        captured = capsys.readouterr()
        assert "0xa 0xb" in captured.out

        sample_profile.printHex("AB")
        captured_str = capsys.readouterr()
        assert "0x41 0x42" in captured_str.out
