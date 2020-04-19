import json
import os
import threading
import time
import requests
import queue
import logging
import textwrap
from pathlib import Path
from flask import current_app
from sandbox import Sandbox
from .exception import *


class Dispatcher(threading.Thread):
    def __init__(
        self,
        dispatcher_config='.config/dispatcher.json',
        base_dir='submissions',
        host_dir='/submissions',
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
        # flag to decided whether the thread should run
        self.do_run = True
        # submission location (inside container)
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        # host dir must be the mount point of base dir
        self.host_dir = Path(host_dir)
        # task queue
        # type Queue[Tuple[submission_id, task_no]]
        self.max_task_count = config.get('QUEUE_SIZE', 16)
        self.queue = queue.Queue(self.max_task_count)
        # task result
        # type: Dict[submission_id, Tuple[submission_info, List[result]]]
        self.result = set()
        # manage containers
        self.max_container_count = config.get('MAX_CONTAINER_COUNT', 8)
        self.container_count = 0

    @property
    def logger(self) -> logging.Logger:
        try:
            return current_app.logger
        except RuntimeError:
            return logging.getLogger('gunicorn.error')

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
        if not submission_path.exist():
            raise FileNotFoundError(
                f'submission id: {submission_id} file not found.')
        elif not submission_path.is_dir():
            raise NotADirectoryError(f'{submission_path} is not a directory')
        # duplicated
        if submission_id in self.result:
            raise DuplicatedSubmissionIdError(
                f'duplicated submission id {submission_id}.')
        # read submission meta
        with open(f'{submission_path}/meta.json') as f:
            submission_config = json.load(f)
        self.result.add(submission_id)
        self.logger.debug(f'current submissions: {[*self.result]}')
        try:
            # put (submission_id, case_no)
            self.queue.put_nowait(submission_id)
        except queue.Full as e:
            del self.result[submission_id]
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
            self.logger.info(f'create container for {submission_id}')
            # assign a new runner
            threading.Thread(
                target=self.create_container,
                kwargs={
                    'submission_id': submission_id,
                    'mem_limit': 128000,  # 128 MB
                    'time_limit': 10000,  # 10s
                },
            ).start()

    def stop(self):
        self.do_run = False

    def create_container(
        self,
        submission_id: str,
        mem_limit: int,
        time_limit: int,
    ):
        if submission_id not in self.result:
            raise SubmissionIdNotFoundError(f'{submission_id} not found!')
        self.container_count += 1
        base_dir = self.get_host_path(submission_id)
        res = Sandbox(
            time_limit=time_limit,
            mem_limit=mem_limit,
            src_dir=str(base_dir.absolute()),
            ignores=(f.name for f in base_dir.iterdir()),
        ).run()
        self.container_count -= 1
        self.logger.info(f'finish task {submission_id}')
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
                f'skip send {submission_id} result to http handler', )
            return True
        # post data
        self.logger.debug(f'{submission_id} send to http handler')
        resp = requests.post(
            f'{self.HTTP_HANDLER_URL}/result/{submission_id}',
            data=res,
        )
        self.logger.info(f'finish submission {submission_id}')
        # remove this submission
        self.result.remove(submission_id)
        # some error occurred
        if resp.status_code != 200:
            self.logger.warning(
                'dispatcher receive err\n'
                f'status code: {resp.status_code}\n'
                f'msg: {resp.text}', )
            return False
        return True
