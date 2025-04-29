#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
import tenacity
import subprocess
import requests
import json

from charmed_kubeflow_chisme.rock import CheckRock

# Retry if the server is not ready
@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_fixed(2)
)
def post_sync_request(url):
    headers = {"Content-Type": "application/json"}
    payload = {
        "object": {
            "metadata": {
                "name": "someName",
                "labels": {
                    "user.kubeflow.org/enabled": "true"
                }
            }
        },
        "attachments": {
            "Secret.v1": [{}, {}],
            "ServiceAccount.v1": [{}]
        }
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    return response.json()

def main():
    """Test running container and /sync endpoint."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    print(f"Running {LOCAL_ROCK_IMAGE}")
    container_id = subprocess.run(
        ["docker", "run", "-d", "-p", "80:80", LOCAL_ROCK_IMAGE],
        stdout=subprocess.PIPE
    ).stdout.decode('utf-8')
    container_id = container_id[0:12]

    try:
        # Try to POST to the /sync endpoint
        output = post_sync_request("http://0.0.0.0/sync")

        # (Optional) validate output if needed
        assert isinstance(output, dict)
    finally:
        # Cleanup container no matter what
        subprocess.run(["docker", "stop", container_id])
        subprocess.run(["docker", "rm", container_id])

if __name__ == "__main__":
    main()
