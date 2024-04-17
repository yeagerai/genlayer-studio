import os
from math import ceil, floor
from config import Config
from flask import Flask
from flask_jsonrpc import JSONRPC
from urllib.parse import urlparse
from time import time

from request import get_webdriver, get_text

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv()

'''
def create_app():
   app = Flask('webrequest')
   app.config.from_object(Config)
   app.config['BASE_DIR'] = str(BASE_DIR)
   register_extensions(app)
   register_blueprints(app)
   return app

def register_extensions(app):
   return None

def register_blueprints(app):
   return None

app = create_app()
'''
app = Flask('genvm_api')
jsonrpc = JSONRPC(app, "/api", enable_web_browsable_api=True)


def return_success(data:str):
    return return_format('success', data)

def return_error(message:str):
    return return_format('error', message)

def return_format(status:str, data:str):
    return {
        'status': status,
        'response': data
    }

def is_valid_url(url):
    parsed_url = urlparse(url)
    return all([parsed_url.scheme, parsed_url.netloc])


@jsonrpc.method("get_webpage")
def get_webpage(url:str) -> dict:
    if not is_valid_url(url):
        return return_error('URL not in correct format')
    driver = get_webdriver()
    try:
        start_time = time()
        webpage_text = get_text(driver, url)
        end_time = time()
        print('Execution time: '+str(end_time - start_time)+'s')
    except Exception as e:
        if 'ERR_NAME_NOT_RESOLVED' in str(e):
            return return_error('URL does not exist')
        return return_error(str(e))
    return return_success(webpage_text)


@jsonrpc.method("get_webpage_chunks")
def get_webpage_chunks(url:str, chunk_sizes: int, overlap:float) -> dict:
    if not is_valid_url(url):
        return return_error('URL not in correct format')
    if overlap < 0 or overlap > 0.4:
        return return_error('Overlap should be between 0 and 0.4')
    chunks = []
    overlap_num = floor(chunk_sizes * overlap)
    driver = get_webdriver()
    try:
        start_time = time()
        webpage_text = get_text(driver, url)
        webpage_text_words = webpage_text.split(' ')
        num_chuncks = ceil(len(webpage_text_words) / chunk_sizes)
        for i in range(num_chuncks):
            start_chunck = i * chunk_sizes
            end_chunck = (i + 1) * chunk_sizes
            if i > 0:
                start_chunck -= overlap_num
            if i != num_chuncks - 1:
                end_chunck += overlap_num
            chunks.append(' '.join(webpage_text_words[start_chunck:end_chunck]))
        end_time = time()
        print('Execution time: '+str(end_time - start_time)+'s')
    except Exception as e:
        if 'ERR_NAME_NOT_RESOLVED' in str(e):
            return return_error('URL does not exist')
        return return_error(str(e))
    return return_success(chunks)


if __name__ == "__main__":
    app.run(debug=True, port=os.environ.get('SELENIUMPORT'), host='0.0.0.0')