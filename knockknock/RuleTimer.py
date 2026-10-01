import subprocess
import threading
import time
from typing import Union


class RuleTimer(threading.Thread):

    def __init__(self, openDuration: Union[int, float], description: str) -> None:
        self.openDuration: Union[int, float] = openDuration
        self.description: str = description
        threading.Thread.__init__(self)

    def run(self) -> None:
        time.sleep(self.openDuration)
        command = 'iptables -D ' + self.description
        command_list = command.split()

        subprocess.call(command_list, shell=False)
