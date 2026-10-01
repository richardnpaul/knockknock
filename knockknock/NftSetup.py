import shutil
import subprocess
import sys


class NftSetup:
    def __init__(self) -> None:
        nft_bin = shutil.which("nft")
        if not nft_bin:
            sys.stderr.write("knockknock-daemon: nft executable not found in PATH.\n")
            sys.exit(3)
        self.nft_path: str = nft_bin

    def initialise(self) -> None:
        table_cmd = [self.nft_path, "add", "table", "inet", "knockknock"]
        set_cmd = [
            self.nft_path,
            "add",
            "set",
            "inet",
            "knockknock",
            "open_ports",
            "{ type ipv4_addr . inet_service; flags timeout; }",
        ]
        chain_cmd = [
            self.nft_path,
            "add",
            "chain",
            "inet",
            "knockknock",
            "input",
            "{ type filter hook input priority filter - 1; policy accept; }",
        ]
        rule_cmd = [
            self.nft_path,
            "add",
            "rule",
            "inet",
            "knockknock",
            "input",
            "ct",
            "state",
            "new",
            "ip",
            "saddr",
            ".",
            "tcp",
            "dport",
            "@open_ports",
            "meter",
            "open_limit",
            "{ ip saddr limit rate 1/minute burst 1 packets }",
            "accept",
        ]

        subprocess.call(table_cmd, shell=False)
        subprocess.call(set_cmd, shell=False)
        subprocess.call(chain_cmd, shell=False)
        subprocess.call(rule_cmd, shell=False)

    def teardown(self) -> None:
        cmd = [self.nft_path, "delete", "table", "inet", "knockknock"]
        subprocess.call(cmd, shell=False)
