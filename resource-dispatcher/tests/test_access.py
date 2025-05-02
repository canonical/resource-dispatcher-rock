#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
import pytest
import subprocess
import requests
import json
import tenacity

from charmed_kubeflow_chisme.rock import CheckRock

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

@pytest.fixture(scope="module")
def running_container():
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    local_image = f"{rock_image}:{rock_version}"

    print(f"Running container: {local_image}")
    result = subprocess.run(
        ["docker", "run", "-d", "-p", "80:80", local_image],
        stdout=subprocess.PIPE,
        check=True
    )
    container_id = result.stdout.decode('utf-8')[:12]

    yield container_id

    subprocess.run(["docker", "stop", container_id])
    subprocess.run(["docker", "rm", container_id])

def test_sync_endpoint(running_container):
    output = post_sync_request("http://0.0.0.0/sync")
    assert isinstance(output, dict)
