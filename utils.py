import sys
import json
import os

def getSettings():
    headers_file = 'settings.json'

    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)

    config_path = os.path.join(application_path, headers_file)

    # settings
    settings = []
    try:
        with open(config_path, 'r+') as f:
            settings = json.load(f)
    except:
        print('No settings.json file found!')

    return settings