import json
import os
import threading
import time
import queue
import logging
import textwrap
import docker
import docker.errors
from pathlib import Path
from flask import current_app
from sandbox import Sandbox
from .exception import *


class Dispatcher(threading.Thread):
    def __init__(
        self,
        on_complete,
        dispatcher_config='.config/dispatcher.json',
    ):
        super().__init__()
        self.testing = False
        # read config
        config = {}
        if os.path.exists(dispatcher_config):
            config = json.load(open(dispatcher_config))
        else:
            self.logger.warning(
                f'dispatcher config {dispatcher_config} not found')
        # flag to decided whether the loop should run
        self.do_run = True
        # submission location (inside container)
        self.base_dir = Path(config.get('base_dir', 'submissions'))
        self.base_dir.mkdir(exist_ok=True)
        # host dir must be the mount point of base dir
        self.host_dir = Path(config.get('host_dir', '/submissions'))
        # task queue
        self.max_task_count = config.get('queue_size', 16)
        # type Queue[Tuple[submission_id, task_no]]
        self.queue = queue.Queue(self.max_task_count)
        # task result
        # type: Dict[submission_id, Tuple[submission_info, List[result]]]
        self.result = set()
        # manage containers
        self.max_container_count = config.get('max_container_count', 8)
        self.container_count = 0
        # completion handler
        self.on_complete = on_complete
        # image used to judge
        self.image = config['image']

    @property
    def logger(self) -> logging.Logger:
        try:
            return current_app.logger
        except RuntimeError:
            return logging.getLogger('gunicorn.error')

    def ensure_image(self):
        client = docker.client.from_env()
        try:
            client.images.get(self.image)
        except docker.errors.ImageNotFound:
            self.logger.info(f'Image not found. Start pulling. [{self.image}]')
            client.images.pull(self.image)

    def get_path(self, submission_id) -> Path:
        return self.base_dir / submission_id

    def get_host_path(self, submission_id) -> Path:
        return self.host_dir / submission_id

    def handle(self, submission_id):
        '''
        handle a submission, save its config and push into task queue

        Args:
            submission_id -> str: the submission's unique id
        Returns:
            a bool denote whether the submission has successfully put into queue
        '''
        self.logger.info(f'receive submission {submission_id}.')
        submission_path = self.get_path(submission_id)
        # check whether the submission directory exist
        if not submission_path.exists():
            raise FileNotFoundError(
                f'submission id: {submission_id} file not found.')
        elif not submission_path.is_dir():
            raise NotADirectoryError(f'{submission_path} is not a directory')
        # duplicated
        if submission_id in self.result:
            raise DuplicatedSubmissionIdError(
                f'duplicated submission id {submission_id}.')
        self.result.add(submission_id)
        self.logger.debug(f'current submissions: {[*self.result]}')
        try:
            # put (submission_id, case_no)
            self.queue.put_nowait(submission_id)
        except queue.Full as e:
            self.result.remove(submission_id)
            raise e
        return True

    def idle(self):
        '''
        for debug(?
        '''
        msg = 'i\'m a teapot. :/'
        while True:
            logging.critical('logging: ' + msg)
            self.logger.critical('app logger: ' + msg)
            print('print: ' + msg)
            time.sleep(0.16)

    def run(self):
        self.do_run = True
        self.logger.debug('start dispatcher loop')
        while True:
            self.ensure_image()
            time.sleep(1)
            # end the loop
            if not self.do_run:
                self.logger.debug('exit dispatcher loop')
                break
            # no testcase need to be run
            if self.queue.empty():
                continue
            # no space for new cotainer now
            if self.container_count >= self.max_container_count:
                continue
            # get a case
            submission_id = self.queue.get()
            # assign a new runner
            threading.Thread(
                target=self.create_container,
                kwargs={
                    'submission_id': submission_id,
                    'mem_limit': 128000,  # 128 MB
                    'time_limit': 10,  # 10s
                    'file_size_limit': 64 * 10**6,
                    'output_size_limit': 4096,  # 4KB
                    'image': self.image,
                },
            ).start()

    def stop(self):
        self.do_run = False

    def create_container(
            self,
            submission_id: str,
            **ks,  # pass to sandbox
    ):
        if submission_id not in self.result:
            raise SubmissionIdNotFoundError(f'{submission_id} not found!')
        self.logger.info(f'Create container [submission_id={submission_id}]')
        self.container_count += 1
        res = Sandbox(
            src_dir=str(self.get_host_path(submission_id).absolute()),
            container_src_dir=str(self.get_path(submission_id).absolute()),
            ignores=[
                '__pycache__',
            ] + [f.name for f in self.get_path(submission_id).iterdir()],
            **ks,
        ).run()
        self.container_count -= 1
        self.logger.info(f'Finish task [submission_id={submission_id}]')
        # truncate long stdout/stderr
        _res = res.copy()
        for k in ('stdout', 'stderr'):
            _res[k] = textwrap.shorten(_res.get(k, ''), 37, placeholder='...')
        # extract filename
        if 'files' in _res:
            _res['files'] = [f.name for f in _res['files']]
        self.logger.debug(f'runner result: {_res}')
        # completion
        if self.testing:
            self.logger.info(
                'current in testing'
                f'skip submission [{submission_id}] completion', )
            return True
        # post data
        self.on_complete(submission_id, res)
        # remove this submission
        self.result.remove(submission_id)
