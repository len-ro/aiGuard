#!/usr/bin/env python3

import sys
import time
import json
import os, signal
import logging, logging.config

from watchdog.observers import Observer
from watchdog.events import RegexMatchingEventHandler

class SignalCatcher:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True

class DirectoryMonitor(RegexMatchingEventHandler):
    """ Single directory monitor """ 
    def __init__(self, name, config):
        self.name = name
        self.config = config
        if 'regexp' in self.config:
            super().__init__(self.config['regexp'])
        else:
            super().__init__()
        self.__event_handler = self
        self.__event_observer = Observer()
        self.logger = logging.getLogger("directoryMonitor")

    def on_created(self, event):
        """ wait for file to be complete, not perfect """
        file_size = -1
        while file_size != os.path.getsize(event.src_path):
            file_size = os.path.getsize(event.src_path)
            time.sleep(1)
        self.process(event)

    def start(self):
        if not os.path.isdir(self.config['path']):
            self.logger.error("Not a directory: %s" % self.config['path'])
            self.started = False
            return
        self.__event_observer.schedule(
            self.__event_handler,
            self.config['path'],
            recursive=False
        )
        self.__event_observer.start()
        self.started = True
        self.logger.info("start monitoring %s" % self.config['path'])

    def stop(self):
        if self.started:
            self.__event_observer.stop()
            self.__event_observer.join()
            self.logger.info("stop monitoring %s" % self.config['path'])


    def process(self, event):
        self.logger.info("Processing new file %s" % event.src_path)

class aiGuard:
    def __init__(self):
        self.config = json.load(open('config.json', 'r'))
        self.setup_logging()
        self.monitors = []

    def setup_logging(self):
        logging.config.dictConfig(self.config['logging'])
        self.logger = logging.getLogger('aiGuard')

    def monitor(self):
        self.logger.info('aiGuard start')
        killer = SignalCatcher()

        """ init monitors """
        for dir in self.config['directories']:
            monitor = DirectoryMonitor(dir, self.config['directories'][dir])
            monitor.start()
            self.monitors.append(monitor)

        """main loop"""
        while True:
            if killer.kill_now:
                break

            time.sleep(self.config['timeout'])

        for m in self.monitors:
            m.stop()
        self.logger.info('aiGuard stop')

if __name__ == "__main__":
    aiGuard = aiGuard()
    aiGuard.monitor()
