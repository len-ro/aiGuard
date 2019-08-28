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

    def process_features(self, input_image, output_image, subdir, subdir_src, detections, action, action_message = None):
        self.store_detections_in_exif([input_image, output_image], detections)
        
        output_image = self.move_to_dir(output_image, subdir)
        self.move_to_dir(input_image, subdir_src)

        try:
            if action in self.config['actions']:
                action_instance = self.config['actions'][action]
                action_instance.action(action_message, output_image)
        except:
            self.logger.error("Unexpected error in action", exc_info=1)
            
        

    def process(self, input_image, output_image, detections):
        for c in self.config['classes']:
            self.logger.info("Processing class %s" % c)
            d = c['detections']
            #output_image is already in processed
            subdir = os.path.join(os.path.dirname(output_image), c['name'])
            subdir_src = os.path.join(subdir, 'src')
            action = c.get('action', None)

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
                        self.logger.info("[any] Feature %s found in %s, moving to %s" % (f_name, input_image, subdir))
                        msg = "[any] Feature %s found in" % f_name
                        self.process_features(input_image, output_image, subdir, subdir_src, detections, action, msg)
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
                    self.logger.info("[all] features found in %s, moving to %s" % (input_image, subdir))
                    msg = "[all] Features %s found in" % ','.join(detected_features)
                    self.process_features(input_image, output_image, subdir, subdir_src, detections, action, msg)
                    return
            
            if d['mode'] == 'move':
                self.logger.info("[move] %s, moving to %s" % (input_image, subdir))
                self.process_features(input_image, output_image, subdir, subdir_src, detections, action)
                return                


            
            
            