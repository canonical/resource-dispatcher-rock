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
PROFILE_A = "profile-a"
PROFILE_B = "profile-b"
PROFILE_A_SECRET = "profile-pinned-secret"
PROFILE_AGNOSTIC_SECRET = "mlpipeline-minio-artifact"
CONFLICT_SECRET_NAME = "mlpipeline-minio-artifact"
CONFLICT_PINNED_ACCESS_KEY = "pinned-access-key"
CONFLICT_GLOBAL_ACCESS_KEY = "value"

EXPECTED_ATTACHMENTS = [
    {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "mlpipeline-minio-artifact2", "namespace": "someName"},
        "stringData": {"accesskey": "value", "secretkey": "value"},
    },
    {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "mlpipeline-minio-artifact", "namespace": "someName"},
        "stringData": {"accesskey": "value", "secretkey": "value"},
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
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": "test-role",
            "labels": {"user.kubeflow.org/enabled": "true"},
            "namespace": "someName",
        },
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["secrets"],
                "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
            }
        ],
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {
            "name": "test-rolebinding",
            "labels": {"user.kubeflow.org/enabled": "true"},
            "namespace": "someName",
        },
        "subjects": [{"kind": "ServiceAccount", "name": "seracc", "namespace": "someName"}],
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": "test-role"},
    },
    {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "test-configmap",
            "labels": {"user.kubeflow.org/enabled": "true"},
            "namespace": "someName",
        },
        "data": {
            "defaultPipelineRoot": "minio://mlpipeline",
            "providers": "minio:\n  default:\n    endpoint: minio:9000.test-kubeflow\n    "
            "region: minio\n    credentials:\n      fromEnv: false\n      secretRef:\n        "
            "secretName: mlpipeline-minio-artifact\n        accessKeyKey: accesskey\n        "
            "secretKeyKey: secretkey",
        },
    },
]

CORRECT_NAMESPACE_REQ = {
    "object": {"metadata": {"name": "someName", "labels": {LABEL: "true"}}},
    "attachments": {
        "Secret.v1": [],
        "ServiceAccount.v1": [],
        "PodDefault.kubeflow.org/v1alpha1": [],
        "Role.rbac.authorization.k8s.io/v1": [],
        "RoleBinding.rbac.authorization.k8s.io/v1": [],
        "ConfigMap.v1": [],
    },
}

CORRECT_NAMESPACE_REQ_NO_RESYNC = {
    "object": {"metadata": {"name": "someName", "labels": {LABEL: "true"}}},
    "attachments": {
        "Secret.v1": [{}, {}],
        "ServiceAccount.v1": [{}],
        "PodDefault.kubeflow.org/v1alpha1": [{}, {}],
        "Role.rbac.authorization.k8s.io/v1": [{}],
        "RoleBinding.rbac.authorization.k8s.io/v1": [{}],
        "ConfigMap.v1": [{}],
    },
}

WRONG_NAMESPACE_REQ = {
    "object": {"metadata": {"name": "someName", "labels": {"wrong.namespace": "true"}}},
    "attachments": {
        "Secret.v1": [],
        "ServiceAccount.v1": [],
        "PodDefault.kubeflow.org/v1alpha1": [],
        "Role.rbac.authorization.k8s.io/v1": [],
        "RoleBinding.rbac.authorization.k8s.io/v1": [],
        "ConfigMap.v1": [],
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


def _build_request(namespace: str, attachments: dict | None = None) -> dict:
    """Build a controller sync request for a given namespace."""
    return {
        "object": {"metadata": {"name": namespace, "labels": {LABEL: "true"}}},
        "attachments": attachments
        or {
            "Secret.v1": [],
            "ServiceAccount.v1": [],
            "PodDefault.kubeflow.org/v1alpha1": [],
            "Role.rbac.authorization.k8s.io/v1": [],
            "RoleBinding.rbac.authorization.k8s.io/v1": [],
        },
    }


def _post_sync(server: HTTPServer, request_data: dict) -> dict:
    """Send a sync request to the server and return parsed JSON."""
    url = f"http://{server.server_address[0]}:{str(server.server_address[1])}"
    response = requests.post(url, data=json.dumps(request_data))
    assert response.status_code == 200
    return json.loads(response.text)


def _find_secret_in_controller_sync_result(result: dict, secret_name: str) -> dict | None:
    """Find a secret attachment by name in the controller sync result."""
    return next(
        (
            item
            for item in result["attachments"]
            if item["kind"] == "Secret" and item["metadata"]["name"] == secret_name
        ),
        None,
    )


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
    result = _post_sync(server, request_data)
    assert result["status"] == response_data["status"]
    assert [i for i in response_data["attachments"] if i not in result["attachments"]] == []
    assert ("resyncAfterSeconds" in result) == resync


@pytest.mark.parametrize(
    "namespace, expected_secret",
    [
        (PROFILE_A, PROFILE_A_SECRET),
        (PROFILE_B, None),
    ],
)
def test_namespace_specific_manifest_applied(server, namespace, expected_secret):
    """Verify manifests with metadata.namespace are not fanned out to other namespaces."""
    result = _post_sync(server, _build_request(namespace))
    matched_secret = _find_secret_in_controller_sync_result(result, PROFILE_A_SECRET)

    assert (
        matched_secret["metadata"]["name"] if matched_secret else None
    ) == expected_secret, f"{PROFILE_A_SECRET} presence mismatch for namespace {namespace}"


@pytest.mark.parametrize("namespace", [PROFILE_A, PROFILE_B])
def test_namespace_agnostic_manifest_applied(server, namespace):
    """Verify namespace-agnostic manifests are rendered for each matching namespace."""
    result = _post_sync(server, _build_request(namespace))
    matched_secret = _find_secret_in_controller_sync_result(result, PROFILE_AGNOSTIC_SECRET)

    assert matched_secret is not None, f"Should find {PROFILE_AGNOSTIC_SECRET} in {namespace}"
    assert matched_secret["metadata"]["namespace"] == namespace, f"Namespace should be {namespace}"


@pytest.mark.parametrize(
    "namespace, expected_access_key",
    [
        (PROFILE_A, CONFLICT_PINNED_ACCESS_KEY),
        (PROFILE_B, CONFLICT_GLOBAL_ACCESS_KEY),
    ],
)
def test_conflict_resolution_pinned_overrides_global(server, namespace, expected_access_key):
    """Verify a namespace-pinned manifest shadows the global manifest of the same name."""
    result = _post_sync(server, _build_request(namespace))
    matched_secret = _find_secret_in_controller_sync_result(result, CONFLICT_SECRET_NAME)

    assert (
        matched_secret is not None
    ), f"Should find '{CONFLICT_SECRET_NAME}' in namespace '{namespace}'"
    assert matched_secret["stringData"]["accesskey"] == expected_access_key, (
        f"Expected access key '{expected_access_key}' for namespace '{namespace}', "
        f"got '{matched_secret['stringData']['accesskey']}'"
    )
