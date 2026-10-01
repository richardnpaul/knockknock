import configparser
from pathlib import Path
from typing import Union


class DaemonConfiguration:

    def __init__(self, file: Union[str, Path]) -> None:
        try:
            parser = configparser.ConfigParser({'delay': '15', 'error_window': '20'})
            parser.read(file)

            self.delay: int = int(parser.get('main', 'delay'))
            self.window: int = int(parser.get('main', 'error_window'))
        except configparser.NoSectionError:
            print("knockknock-daemon: config file not found, assuming defaults.")
            self.delay = 15
            self.window = 20

    def getDelay(self) -> int:
        return self.delay

    def getWindow(self) -> int:
        return self.window
