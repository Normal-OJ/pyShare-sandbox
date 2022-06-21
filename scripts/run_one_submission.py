import shutil
import sys
import tempfile
from pprint import pprint
from pathlib import Path
from sandbox import Sandbox


def run(script_path: Path):
    if not script_path.exists():
        raise FileNotFoundError()
    if not script_path.is_file():
        raise ValueError(f'{script_path} is not a file')
    with prepare_src_dir(script_path) as src_dir:
        sandbox = Sandbox(
            time_limit=10,
            mem_limit=128000,
            output_size_limit=4096,
            file_size_limit=64 * 10**6,
            src_dir=src_dir,
            ignores=['__pycache__', 'main.py'],
            container_src_dir=src_dir,
            image='registry.gitlab.com/pyshare/judger',
        )
        return sandbox.run()


def prepare_src_dir(script_path: Path):
    dir_prefix = 'pyshare-one-shot-submission'
    temp_dir = tempfile.TemporaryDirectory(prefix=dir_prefix)
    # The source must named 'main.py'
    shutil.copy(script_path, f'{temp_dir.name}/main.py')
    return temp_dir


if __name__ == '__main__':
    try:
        script_path = Path(sys.argv[1])
    except IndexError:
        print(f'Usage: python3 {__file__} <script path>')
        exit(1)
    result = run(script_path)
    pprint(result)
