import os
import json
import configparser
import subprocess
import signal
import shutil
import cv2
import io
import threading
import time
import numpy as np
from flask import Flask, jsonify, request, send_from_directory, render_template, Response
from flask_cors import CORS
from croniter import croniter
from datetime import datetime
import downloader

app = Flask(__name__)
CORS(app)

CONFIG_FILE = 'config.ini'
STATE_FILE = 'state.json'
HISTORY_FILE = 'history.json'
REMOVE_DIR = '/home/ram/removed/'

def get_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config

# Motion Detection State
motion_data = {
    "last_frame": None,
    "last_movement_time": time.time(),
    "screen_state": "on"
}
camera_lock = threading.Lock()

# [Keep the rest of the file - I will use the python script to combine or just overwrite]
