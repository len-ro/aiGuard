#!/usr/bin/env python3

import sys
import time
import json
import os, signal, re
import logging, logging.config
import threading

from watchdog.observers import Observer
from watchdog.events import RegexMatchingEventHandler
from imageai.Detection import ObjectDetection
from queue import Queue

from modules.processor import Processor

class SignalCatcher:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


class DirEventHandler(RegexMatchingEventHandler):
    """ Single directory event handler """ 
    def __init__(self, config, process_function):
        self.logger = logging.getLogger("dirEventHandler")
        self.process_function = process_function
        if 'regexp' in config:
            super().__init__([config['regexp']])
        else:
            super().__init__()

    def on_created(self, event):
        """ wait for file to be complete, not perfect """
        self.logger.info("New file: " + event.src_path)
        file_size = -1
        while file_size != os.path.getsize(event.src_path):
            file_size = os.path.getsize(event.src_path)
            time.sleep(2)
        self.process_function(event.src_path)        

class aiGuard:
    def __init__(self):
        self.config = json.load(open('config.json', 'r'))
        self.setup_logging()
        self.observer = Observer()
        self.queue = Queue(10)
        self.setup_actions(self.config['actions'])
        self.processors = {}
        for p_name in self.config['processors']:
            p_config = self.config['processors'][p_name]
            p_config.actions = self.actions
            self.processors[p_name] = Processor(p_config)

    def plugin(self, plugin_type, plugin_name, config):
        loaded_plugins = self.__dict__[plugin_type]
        if not plugin_name in loaded_plugins:
            self.logger.info('creating plugin %s %s', plugin_type, plugin_name)
            #sys.path.append(plugin_type) #https://stackoverflow.com/questions/25997185/python-importerror-import-by-filename-is-not-supported
            module = __import__('%s.%s' % (plugin_type, plugin_name))
            p_class = getattr(module, plugin_name)
            p_instance = p_class[plugin_name](config)
            loaded_plugins[plugin_name] = p_instance 
            return p_instance
        else:
            p_instance = loaded_plugins[plugin_name]
            return p_instance

    def setup_actions(self, actions):
        self.actions = {}
        if actions:
            for a_name in actions:
                self.plugin('actions', a_name, actions[a_name])

    def setup_logging(self):
        logging.config.dictConfig(self.config['logging'])
        self.logger = logging.getLogger('aiGuard')

    def mk_subdir(self, base_dir, name):
        """ creates a new dir in base_dir if it does not exist """
        new_dir = os.path.join(base_dir, name)
        if not os.path.exists(new_dir):
            os.mkdir(new_dir)
        return new_dir

    def detector_thread(self, config):
        """Image detection in a single thread"""
        detector = ObjectDetection()

        if config['type'] == 'YOLOv3':
            detector.setModelTypeAsYOLOv3()
        elif self.config['type'] == 'RetinaNet':
            detector.setModelTypeAsRetinaNet()

        detector.setModelPath(config['model'])
        detector.loadModel()

        self.logger.info("Model loaded")

        while True:
            input_path = self.queue.get()
            if input_path == False: #termination condition 
                with self.queue.mutex:
                    self.queue.queue.clear()       
                self.queue.task_done()
                break
            if os.path.isfile(input_path):
                dirname, basename = os.path.split(input_path)
                output_image = os.path.join(self.mk_subdir(dirname, config['outdir']), basename)
                self.logger.info("Analysing new file %s -> %s" % (input_path, output_image))
                try:
                    detections = detector.detectObjectsFromImage(input_image=input_path, output_image_path=output_image)
                except:
                    self.logger.error("Unexpected error in detectObjectsFromImage", exc_info=1)
                #process file
                if dirname in self.processors:
                    processor = self.processors[dirname]
                    try:
                        processor.process(input_path, output_image, detections)
                    except:
                        self.logger.error("Unexpected error in process", exc_info=1)
                else:
                    self.logger.warn("No processor found for %s in %s" % (dirname, self.processors.keys())) 
            self.queue.task_done()

    def process_file(self, file_path):
        """
        In response to a file event, send the file for processing to the detector_thread
        see: https://github.com/OlafenwaMoses/ImageAI/issues/125 why a single thread is needed
        """
        self.queue.put(file_path)

    def monitor(self):
        """This is the main entry point"""
        self.logger.info('aiGuard start')
        killer = SignalCatcher()

        """ init detector thread """
        self.detector = threading.Thread(target=self.detector_thread, args=(self.config['detector'],))
        self.detector.start()
        self.logger.info("Detector thread started")

        """ init monitors """
        for dir in self.config['directories']:
            dir_config = self.config['directories'][dir]
            if not os.path.isdir(dir_config['path']):
                self.logger.error("Not a directory: %s" % dir_config['path'])
            else:
                dir_path = dir_config['path']

                processor_name = dir_config['processor']
                if processor_name in self.processors:
                    self.processors[dir_path] = self.processors[processor_name]
                else:
                    self.logger.warn('No processor %s defined' % processor_name)
                    #TODO error

                if dir_config.get('processFirst', 'true') == 'true':
                    #we will process all files in this dir first
                    list = os.listdir(dir_path)
                    file_re = re.compile(dir_config['regexp'])
                    for file_name in list:
                        file_path = os.path.join(dir_path, file_name)
                        if os.path.isfile(file_path) and file_re.match(file_name):
                            self.process_file(file_path)

                self.logger.info("start monitoring %s" % dir_path)
                self.observer.schedule(
                    DirEventHandler(dir_config, self.process_file),
                    dir_config['path'],
                    recursive=False
                )

        self.observer.start()

        """main loop"""
        while True:
            if killer.kill_now:
                break

            time.sleep(self.config['timeout'])

        self.logger.info("aiGuard stopping")

        self.queue.put(False)

        self.observer.stop()
        self.observer.join()
        
        self.queue.join()
        self.detector.join()
        self.logger.info('aiGuard stop')

if __name__ == "__main__":
    aiGuard = aiGuard()
    aiGuard.monitor()
