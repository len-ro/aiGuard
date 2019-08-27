import logging, time, os
from pushover import Client

class pushover:
    """Very simple implementation of pushover message with image"""

    def __init__(self, config):
        self.logger = logging.getLogger("pushover")
        self.config = config
        self.pushover_api = Client(config['user-key'], api_token=config['api-token'])
        self.last_time = int(time.time())
        if 'lock-file' not in self.config:
            self.config['lock-file'] = 'pushover.disable'
        self.config['lock-file'] = os.path.join(os.getcwd(), self.config['lock-file'])

    def action(self, message, image_file):
        if self.config.active == 'true':
            t = int(time.time())
            delta = t - self.last_time
            self.last_time = t
            if os.path.exists(self.config['lock-file']):
                if delta > self.config.timeout:
                    if not message:
                        message = 'Feature detected in %s!' % image_file
                    with open(image_file, 'rb') as image:
                        self.logger.info("Sending pushover notification %s %s" % (message, image_file))
                        self.pushover_api.send_message(message, attachment=image)
                else:
                    self.logger.info("Not sending pushover notification %s %s, timeout window is %s of %s" % (message, image_file, delta, self.config.timeout))
            else:
                self.logger.info("Not sending pushover notification %s %s, lock file exists %s!" % (message, image_file, self.config['lock-file']))
