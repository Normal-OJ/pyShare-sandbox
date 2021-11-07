# Sandbox

## Setup

1. Create two directory to store submission data and backup. Default names are `submissions` and `submissions.bk`.
2. Copy `.config/dispatcher.json.example` to `.config/dispatcher.json` (or you can cahnge this path by `DISPATCHER_CONFIG` env var).
3. Adjust the config file to fit you deploy. See reference below.

## Configuration

The configration file is in json format, and have 5 options.

- `queue_size`: The capcity of submission queue. If the queue is full and new submission comes, the sandbox server will give a 500 response to require client send it later.
- `max_container_count`: The max container count can run at the same time. Aware that too many container may run out of the host resource.
- `base_dir`: Directory path inside sandbox server container to store submission data. If it is relative path, then it will be reolsve to relative path of `app.py`.
- `host_dir`: Directory path on the host (which run the docker daemon). Note that this path must be absolute path and should be mount to `base_dir` to sandbox server container.
- `image`: The image name used to judge submission. Currently we host the judger server at [GitLab](https://gitlab.com/pyshare/judger) and you can find the latest image on GitLab container registry of the judger repository. Change this if you need to pull the image from other registry. Note the we don't support private image now.
