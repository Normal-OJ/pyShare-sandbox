import sys
from pathlib import Path
from submission import SubmissionRunner

if __name__ == '__main__':
    _id = sys.argv[1]
    _dir = Path(f'submissions/{_id}/testcase')
    runner = SubmissionRunner(
        submission_id=_id,
        time_limit=1000,
        mem_limit=65535,
        testdata_input_path=str((_dir / '0000.in').absolute()),
        testdata_output_path=str((_dir / '0000.out').absolute()),
        lang='c11',
    )

    res = runner.compile()
    print(res)
    res = runner.run()
    print(res)
