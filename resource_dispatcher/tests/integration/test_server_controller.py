#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Integration tests for Resource Dispatcher server controller."""

import json
import threading
from http.server import HTTPServer

import pytest
import requests

from resource_dispatcher.src.server import server_factory

PORT = 0  # HTTPServer randomly assigns the port to a free port
LABEL = "test.label"
FOLDER = "./resource_dispatcher/tests/test_data_folder"

EXPECTED_ATTACHMENTS = [
    {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "mlpipeline-minio-artifact2", "namespace": "someName"},
        "stringData": {"AWS_ACCESS_KEY_ID": "value", "AWS_SECRET_ACCESS_KEY": "value"},
    },
    {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "mlpipeline-minio-artifact", "namespace": "someName"},
        "stringData": {"AWS_ACCESS_KEY_ID": "value", "AWS_SECRET_ACCESS_KEY": "value"},
    },
    {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": "sa", "namespace": "someName"},
        "secrets": [{"name": "s3creds"}],
    },
    {
        "apiVersion": "kubeflow.org/v1alpha1",
        "kind": "PodDefault",
        "metadata": {"name": "mlflow-server-minio", "namespace": "someName"},
        "spec": {
            "desc": "Allow access to MLFlow",
            "env": [
                {"name": "MLFLOW_S3_ENDPOINT_URL", "value": "http://minio.kubeflow:9000"},
                {
                    "name": "MLFLOW_TRACKING_URI",
                    "value": "http://mlflow-server.kubeflow.svc.cluster.local:5000",
                },
            ],
            "selector": {"matchLabels": {"mlflow-server-minio": "true"}},
        },
    },
    {
        "apiVersion": "kubeflow.org/v1alpha1",
        "kind": "PodDefault",
        "metadata": {"name": "access-minio", "namespace": "someName"},
        "spec": {
            "desc": "Allow access to Minio",
            "selector": {"matchLabels": {"access-minio": "true"}},
            "env": [
                {
                    "name": "AWS_ACCESS_KEY_ID",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "mlpipeline-minio-artifact",
                            "key": "accesskey",
                            "optional": False,
                        }
                    },
                },
                {
                    "name": "AWS_SECRET_ACCESS_KEY",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "mlpipeline-minio-artifact",
                            "key": "secretkey",
                            "optional": False,
                        }
                    },
                },
                {
                    "name": "MINIO_ENDPOINT_URL",
                    "value": "http://minio.kubeflow.svc.cluster.local:9000",
                },
            ],
        },
    },
]

CORRECT_NAMESPACE_REQ = {
    "object": {"metadata": {"name": "someName", "labels": {LABEL: "true"}}},
    "attachments": {
        "Secret.v1": [],
        "ServiceAccount.v1": [],
        "PodDefault.kubeflow.org/v1alpha1": [],
    },
}

CORRECT_NAMESPACE_REQ_NO_RESYNC = {
    "object": {"metadata": {"name": "someName", "labels": {LABEL: "true"}}},
    "attachments": {
        "Secret.v1": [{}, {}],
        "ServiceAccount.v1": [{}],
        "PodDefault.kubeflow.org/v1alpha1": [{}, {}],
    },
}

WRONG_NAMESPACE_REQ = {
    "object": {"metadata": {"name": "someName", "labels": {"wrong.namespace": "true"}}},
    "attachments": {
        "Secret.v1": [],
        "ServiceAccount.v1": [],
        "PodDefault.kubeflow.org/v1alpha1": [],
    },
}

CORRECT_NAMESPACE_RESP = {
    "status": {"resources-ready": "False"},
    "attachments": EXPECTED_ATTACHMENTS,
    "resyncAfterSeconds": 10,
}

CORRECT_NAMESPACE_RESP_NO_RESYNC = {
    "status": {"resources-ready": "True"},
    "attachments": EXPECTED_ATTACHMENTS,
}

WRONG_NAMESPACE_RESP = {"status": {}, "attachments": []}


@pytest.fixture(
    scope="function",
)
def server():
    """
    Start the sync HTTP server for a given set of parameters. Create server on a separate thread.

    Yields:
    * the server (useful to interrogate for the server address)
    """
    server = server_factory(PORT, LABEL, FOLDER)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    yield server


@pytest.mark.parametrize(
    "request_data, response_data, resync",
    [
        (CORRECT_NAMESPACE_REQ, CORRECT_NAMESPACE_RESP, True),
        (WRONG_NAMESPACE_REQ, WRONG_NAMESPACE_RESP, False),
        (CORRECT_NAMESPACE_REQ_NO_RESYNC, CORRECT_NAMESPACE_RESP_NO_RESYNC, False),
    ],
)
def test_server_responses(server: HTTPServer, request_data, response_data, resync):
    """Test if server returns desired Kubernetes objects for given namespaces."""
    server_obj = server
    url = f"http://{server_obj.server_address[0]}:{str(server_obj.server_address[1])}"
    response = requests.post(url, data=json.dumps(request_data))
    result = json.loads(response.text)
    assert response.status_code == 200
    assert result["status"] == response_data["status"]
    assert [i for i in response_data["attachments"] if i not in result["attachments"]] == []
    assert ("resyncAfterSeconds" in result) == resync
