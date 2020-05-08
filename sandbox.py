import logging
import tarfile
import shutil
from io import BytesIO
from uuid import uuid1
from pathlib import Path

import docker
from docker.errors import APIError
from requests.exceptions import ReadTimeout


class Sandbox:
    def __init__(
        self,
        time_limit: int,
        mem_limit: int,
        src_dir: str,
        ignores: list,
    ):
        self.time_limit = time_limit  # int:ms
        self.mem_limit = mem_limit  # int:kb
        # filenames should be ignored
        self.ignores = {*ignores}
        self.image = 'sandbox'  # str
        self.src_dir = src_dir
        self.client = docker.DockerClient.from_env()
        self.container = None

    def run(self):
        # docker container settings
        volume = {
            self.src_dir: {
                'bind': '/sandbox',
                'mode': 'rw'
            },
        }
        # create container
        logging.debug(f'base dir: {self.src_dir}')
        self.container = self.client.containers.create(
            image=self.image,
            command='python3 main.py',
            volumes=volume,
            network_disabled=True,
            working_dir='/sandbox',
        )
        # if self.container.get('Warning'):
        #     docker_msg = self.container.get('Warning')
        #     logging.warning(f'Warning: {docker_msg}')
        try:
            # start and wait container
            self.container.start()
            exit_status = self.container.wait(timeout=5 * self.time_limit)
            logging.debug(f'get docker response: {exit_status}')
        except APIError as e:
            self.container.remove(force=True)
            logging.error(e)
            return {'Status': 'JE'}
        # no other process needed
        except ReadTimeout:
            pass
        # result retrive
        try:
            stdout = self.container.logs(
                stdout=True,
                stderr=False,
            ).decode('utf-8')
            stderr = self.container.logs(
                stdout=False,
                stderr=True,
            ).decode('utf-8')
            files = self.get_files()
        except APIError as e:
            self.container.remove(force=True)
            logging.error(e)
            return {'Status': 'JE'}
        # remove containers
        self.container.remove(force=True)
        return {
            'stdout': stdout,
            'stderr': stderr,
            'files': files,
            'error': exit_status['Error'],
            'exitCode': exit_status['StatusCode'],
        }

    def get_files(self):
        if self.container is None:
            return []
        # get user dir archive
        bits, stat = self.container.get_archive('/sandbox')
        # extract files
        tarbits = b''.join(chunk for chunk in bits)
        tar = tarfile.open(fileobj=BytesIO(tarbits))
        extract_path = f'/tmp/{uuid1()}'
        tar.extractall(extract_path)
        extract_path = Path(extract_path) / 'sandbox'
        # save files {name: data}
        ret = []
        for f in extract_path.iterdir():
            # ignored files
            if f.name in self.ignores:
                continue
            ret.append(f.open('rb'))
        # remove tmp data
        shutil.rmtree(extract_path)
        logging.info(f'extract files {[f.name for f in ret]}')
        return ret
