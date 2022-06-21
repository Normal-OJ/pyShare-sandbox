import os
from zipfile import ZipFile
import logging
import shutil
import requests
import queue
import secrets
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from dispatcher.dispatcher import Dispatcher

logging.basicConfig(filename='logs/sandbox.log')

app = Flask(__name__)
if __name__ != '__main__':
    # let flask app use gunicorn's logger
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    logging.getLogger().setLevel(gunicorn_logger.level)
logger = app.logger

# data storage
SUBMISSION_DIR = Path(os.getenv(
    'SUBMISSION_DIR',
    'submissions',
))
SUBMISSION_BACKUP_DIR = Path(
    os.getenv(
        'SUBMISSION_BACKUP_DIR',
        'submissions.bk',
    ))
SUBMISSION_HOST_DIR = os.getenv(
    'SUBMISSION_HOST_DIR',
    '/submissions',
)
# check
if SUBMISSION_DIR == SUBMISSION_BACKUP_DIR:
    logger.error('use the same dir for submission and backup!')
# create directory
SUBMISSION_DIR.mkdir(exist_ok=True)
SUBMISSION_BACKUP_DIR.mkdir(exist_ok=True)
# backend config
BACKEND_API = os.environ.get(
    'BACKEND_API',
    f'http://web:8080',
)
# sandbox token
SANDBOX_TOKEN = os.getenv(
    'SANDBOX_TOKEN',
    'KoNoSandboxDa',
)


def clean_data(submission_id):
    submission_dir = SUBMISSION_DIR / submission_id
    shutil.rmtree(submission_dir)


def backup_data(submission_id):
    submission_dir = SUBMISSION_DIR / submission_id
    dest = SUBMISSION_BACKUP_DIR / f'{submission_id}_{datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}'
    shutil.move(submission_dir, dest)


def recieve_result(
    submission_id: str,
    data: dict,
):
    data['token'] = SANDBOX_TOKEN
    # extract files
    files = [(
        'files',
        (f.name.split('/')[-1], f, None),
    ) for f in data['files']]
    del data['files']
    logger.info(f'send {submission_id} to BE server')
    resp = requests.put(
        f'{BACKEND_API}/submission/{submission_id}/complete',
        data=data,
        files=files,
    )
    logger.debug(f'get BE response: [{resp.status_code}] {resp.text}', )
    # clear
    if resp.status_code == 200 and app.logger.level != logging.DEBUG:
        clean_data(submission_id)
    # copy to another place
    else:
        backup_data(submission_id)
    return True


# setup dispatcher
DISPATCHER_CONFIG = os.environ.get(
    'DISPATCHER_CONFIG',
    '.config/dispatcher.json',
)
DISPATCHER = Dispatcher(
    dispatcher_config=DISPATCHER_CONFIG,
    on_complete=recieve_result,
)
DISPATCHER.start()


@app.route('/<submission_id>', methods=['POST'])
def submit(submission_id):
    token = request.values['token']
    if not secrets.compare_digest(token, SANDBOX_TOKEN):
        logger.debug(f'get invalid token: {token}')
        return 'invalid token', 403
    # make submission directory
    submission_dir = SUBMISSION_DIR / submission_id
    submission_dir.mkdir()
    # save attachments
    atts = request.files.getlist('attachments')
    for a in atts:
        a.save(submission_dir / a.filename)
    # save input and output
    testcase = request.files.get('testcase')
    if testcase is not None:
        with ZipFile(testcase, 'r') as z:
            z.extractall(submission_dir)
    # save source code
    code = request.values['src']
    if type(code) != type(''):
        return 'code should be string', 400
    (submission_dir / 'main.py').write_text(code)
    logger.debug(f'send submission {submission_id} to dispatcher')
    try:
        DISPATCHER.handle(submission_id)
    except queue.Full:
        return jsonify({
            'status': 'err',
            'msg': 'task queue is full now.\n'
            'please wait a moment and re-send the submission.',
            'data': None,
        }), 500
    return jsonify({
        'status': 'ok',
        'msg': 'ok',
        'data': 'ok',
    })


@app.route('/status', methods=['GET'])
def status():
    ret = {
        'load': DISPATCHER.queue.qsize() / DISPATCHER.max_task_count,
    }
    # if token is provided
    if secrets.compare_digest(SANDBOX_TOKEN, request.args.get('token', '')):
        ret.update({
            'queueSize': DISPATCHER.queue.qsize(),
            'maxTaskCount': DISPATCHER.max_task_count,
            'containerCount': DISPATCHER.container_count,
            'maxContainerCount': DISPATCHER.max_container_count,
            'submissions': [*DISPATCHER.submission_ids],
            'running': DISPATCHER.do_run,
        })
    return jsonify(ret), 200
