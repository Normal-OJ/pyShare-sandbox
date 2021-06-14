import logging
import tarfile
import shutil
from io import BytesIO
from uuid import uuid1
from pathlib import Path
import os

import docker
from docker.errors import APIError
from requests.exceptions import ReadTimeout


class OutputLimitExceed(Exception):
    pass


class SandboxResult:
    SUCCESS = 0
    OUTPUT_LIMIT_EXCEED = 1
    JUDGER_ERROR = 2


class Sandbox:
    def __init__(
        self,
        time_limit: int,
        mem_limit: int,
        output_size_limit: int,
        file_size_limit: int,
        src_dir: str,
        ignores: list,
        container_src_dir: str,
    ):
        self.time_limit = time_limit  # int:ms
        self.mem_limit = mem_limit  # int:kb
        self.file_size_limit = file_size_limit  # int:byte
        self.output_size_limit = output_size_limit  # int:byte
        # filenames should be ignored
        self.ignores = {*ignores}
        self.image = 'sandbox'  # str
        self.src_dir = src_dir
        self.working_dir = '/sandbox'
        self.client = docker.DockerClient.from_env()
        self.container = None
        self.container_src_dir = container_src_dir
        self.is_OJ = os.path.exists(f'{container_src_dir}/input')

    def run(self):
        # docker container settings
        volume = {
            self.src_dir: {
                'bind': self.working_dir,
                'mode': 'rw'
            },
        }
        # has input and output
        extra = ''
        if self.is_OJ:
            extra = '< input'
        command = f'timeout {self.time_limit} python3 main.py {extra}'
        self.container = self.client.containers.create(
            image=self.image,
            # FIXME: Use `sh` to include can correctly get the redirected input
            #   But...why?
            command=['sh', '-c', command],
            volumes=volume,
            network_disabled=True,
            working_dir=self.working_dir,
            mem_limit=f'{self.mem_limit}k',
            # storage_opt={
            #     'size': '64M',
            # },
        )
        try:
            # start and wait container
            self.container.start()
            exit_status = self.container.wait(timeout=self.time_limit)
            logging.debug(f'get docker response: {exit_status}')
        except APIError as e:
            self.container.remove(force=True)
            logging.error(e)
            return {'status': SandboxResult.JUDGER_ERROR}
        # no other process needed
        except ReadTimeout:
            pass
        # result retrive
        try:
            # assume judge successful
            status = SandboxResult.SUCCESS
            # check output size
            stdout = self.container.logs(
                stdout=True,
                stderr=False,
            )
            stderr = self.container.logs(
                stdout=False,
                stderr=True,
            )
            if len(stdout) > self.output_size_limit or \
                 len(stderr) > self.output_size_limit:
                stdout = ''
                stderr = '執行失敗: 輸出大小超過系統限制，無法評測！'
                files = []
                status = SandboxResult.OUTPUT_LIMIT_EXCEED
            else:
                stdout = stdout.decode('utf-8')
                stderr = stderr.decode('utf-8')
            # try to get files
            try:
                files = self.get_files()
            except OutputLimitExceed:
                stdout = ''
                stderr = '執行失敗: 輸出檔案大小超過系統限制，無法評測！'
                files = []
                status = SandboxResult.OUTPUT_LIMIT_EXCEED
        except APIError as e:
            self.container.remove(force=True)
            logging.error(e)
            return {'status': SandboxResult.JUDGER_ERROR}
        finally:
            # remove containers
            self.container.remove(force=True)
            ret = {
                'stdout': stdout,
                'stderr': stderr,
                'files': files,
                'error': exit_status['Error'],
                'exitCode': exit_status['StatusCode'],
                'status': status,
            }
            # add OJ result
            if self.is_OJ:
                if status == SandboxResult.OUTPUT_LIMIT_EXCEED:
                    ret['result'] = 3
                else:
                    ret['result'] = 1
                    with open(f'{self.container_src_dir}/output', 'r') as f:
                        if f.read() == stdout:
                            ret['result'] = 0
            return ret

    def get_files(self):
        if self.container is None:
            return []
        # get user dir archive
        bits, _ = self.container.get_archive('/sandbox')
        tarbits = b''.join(bits)
        tar = tarfile.open(fileobj=BytesIO(tarbits))
        # check file size
        total_size = sum(info.size for info in tar.getmembers())
        if total_size > self.file_size_limit:
            raise OutputLimitExceed
        # extract files
        extract_path = f'/tmp/{uuid1()}'
        tar.extractall(extract_path)
        extract_path = Path(extract_path) / 'sandbox'
        # save files {name: data}
        ret = []
        for f in extract_path.iterdir():
            # ignored files
            if f.name in self.ignores:
                continue
            # skip directory
            if f.is_dir():
                continue
            ret.append(f.open('rb'))
        # remove tmp data
        shutil.rmtree(extract_path)
        logging.info(f'extract files {[f.name for f in ret]}')
        return ret
