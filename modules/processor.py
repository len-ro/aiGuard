import logging, os
import piexif, piexif.helper, json
import numpy as np

class NumpyEncoder(json.JSONEncoder):
    """ Special json encoder for numpy types """
    def default(self, obj):
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
            np.int16, np.int32, np.int64, np.uint8,
            np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, 
            np.float64)):
            return float(obj)
        elif isinstance(obj,(np.ndarray,)): #### This is the fix
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

class Processor():
    def __init__(self, config):
        self.logger = logging.getLogger("processor")
        self.config = config
        self.cache = {}

    def move_to_dir(self, file_path, dir_path):
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        new_path = os.path.join(dir_path, os.path.basename(file_path))
        os.rename(file_path, new_path)
        return new_path

    def store_detections_in_exif(self, files, detections):
        """Stores detections map in exif for later usage"""
        detections_as_json = json.dumps(detections, indent=4, cls=NumpyEncoder)
        exif_dict = {
            "Exif": {
                piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(detections_as_json)
                }
            }
        exif_bytes = piexif.dump(exif_dict)
        for file_path in files:
            piexif.insert(exif_bytes, file_path)

    # throttle enabled
    def throttle(self, config, output_image, subdir, detections):
        if 'throttle' in config:
            throttle_config = config['throttle']
            #self.logger.info("Throttle on %s" % throttle_config)
            if 'active' in throttle_config and throttle_config['active'] == 'true':
                #check if the area si larger than the threshold
                if 'threshold_size' in throttle_config:
                    box = detections['box_points']
                    max_area = throttle_config['threshold_size']
                    #self.logger.info("Box %s" % box)
                    area = abs((box[0] - box[2]) * (box[1] - box[3]))
                    if area > max_area:
                        self.logger.info("Throttled %s which contains a bounding_box for %s which area %s is larger than the threshold %s." % (output_image, detections, area, max_area))
                        return True
                if 'delta' in throttle_config:
                    if subdir not in self.cache:
                        self.cache[subdir] = detections
                        return False 
                    else:
                        prev_detections = self.cache[subdir]
                        min_delta = throttle_config['delta']
                        box = detections['box_points']
                        prev_box = prev_detections['box_points']
                        delta = abs(box[0] + box[2] - prev_box[0] - prev_box[2]) + abs(box[1] + box[3] - prev_box[1] - prev_box[3])    
                        #self.logger.info("Delta %s" % delta)
                        self.cache[subdir] = detections
                        if delta < min_delta:
                            self.logger.info("Throttled %s which contains a bounding_box for %s which is not so different (%s) from the one of the previous image" % (output_image, detections, delta))
                            return True
        return False 

    def process_features(self, input_image, output_image, subdir, subdir_src, detections, feature, config, action_message = None):
        self.store_detections_in_exif([input_image, output_image], detections)
        
        output_image = self.move_to_dir(output_image, subdir)
        self.move_to_dir(input_image, subdir_src)

        try:
            action = config.get('action', None)
            if action in self.config['actions']:
                if not self.throttle(config, output_image, subdir, feature):
                    action_instance = self.config['actions'][action]
                    action_instance.action(action_message, output_image)
        except:
            self.logger.error("Unexpected error in action", exc_info=1)
            
        

    def process(self, input_image, output_image, detections):
        for c in self.config['classes']:
            #self.logger.info("Processing class %s" % c)
            d = c['detections']
            #output_image is already in processed
            subdir = os.path.join(os.path.dirname(output_image), c['name'])
            subdir_src = os.path.join(subdir, 'src')

            #nothing found
            if d['mode'] == 'none' and not detections:
                self.logger.info("[none] Nothing found in %s, moving to %s" % (input_image, subdir))
                self.move_to_dir(input_image, subdir)
                os.remove(output_image)
                return

            if d['mode'] == 'any':
                for feature in detections:
                    f_name = feature['name']
                    if f_name in d['keys']:
                        self.logger.info("[any] %s found in %s, moving to %s" % (f_name, input_image, subdir))
                        msg = "[any] %s found in" % f_name
                        self.process_features(input_image, output_image, subdir, subdir_src, detections, feature, c, msg)
                        return

            if d['mode'] == 'all':
                has_all_features = True
                detected_features = []
                for feature in detections:
                    f_name = feature['name']
                    detected_features.append(f_name)
                    if f_name not in d['keys']:
                        has_all_features = False
                if has_all_features:
                    features_msg = ','.join(detected_features)
                    self.logger.info("[all] %s found in %s, moving to %s" % (features_msg, input_image, subdir))
                    msg = "[all] %s found in" % features_msg
                    self.process_features(input_image, output_image, subdir, subdir_src, detections, None, c, msg)
                    return
            
            if d['mode'] == 'move':
                self.logger.info("[move] %s, moving to %s" % (input_image, subdir))
                self.process_features(input_image, output_image, subdir, subdir_src, detections, None, c)
                return                


            
            
            