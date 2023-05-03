#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Run HTTPServer for Resource Dispatcher."""

import glob
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

import yaml
from yaml.parser import ParserError

from .log import setup_custom_logger

logger = setup_custom_logger("server")


def run_server(port: int, label: str, folder: str) -> None:
    """Run a server for injecting resources into namespaces by given label."""
    logger.info("Resource dispatcher service alive")
    server = server_factory(port, label, folder)
    logger.info(
        f"Serving sync server forever on port: {port}, for label: {label}, on folder: {folder}"
    )
    server.serve_forever()


def server_factory(controller_port: int, label: str, folder: str, url: str = "") -> HTTPServer:
    """Return an HTTPServer populated with Handler with customised settings."""

    class Controller(BaseHTTPRequestHandler):
        def sync(self, parent, attachments):
            """Return manifests which needs to be created for given state."""
            namespace = parent.get("metadata", {}).get("name")
            pipeline_enabled = parent.get("metadata", {}).get("labels", {}).get(label)

            if pipeline_enabled != "true":
                logger.info(
                    f"Namespace not in scope, no action taken (metadata.labels.{label} = {pipeline_enabled}, must be 'true')"  # noqa: E501
                )
                return {"status": {}, "attachments": []}

            desired_secrets_count = 0
            desired_svc_accounts_count = 0
            desired_pod_defaults_count = 0
            desired_resources = []
            try:
                desired_resources += generate_manifests(folder, namespace)
            except ParserError as e:
                raise e

            for resource in desired_resources:
                if resource["kind"] == "Secret":
                    desired_secrets_count += 1
                elif resource["kind"] == "ServiceAccount":
                    desired_svc_accounts_count += 1
                elif resource["kind"] == "PodDefault":
                    desired_pod_defaults_count += 1

            # Just compares number of presented with expected manifests its not comparing contents
            desired_status = {
                "resources-ready": str(
                    len(attachments["Secret.v1"]) == desired_secrets_count
                    and len(attachments["ServiceAccount.v1"]) == desired_svc_accounts_count
                    and len(attachments["PodDefault.kubeflow.org/v1alpha1"])
                    == desired_pod_defaults_count
                )
            }
            resync_after = (
                {"resyncAfterSeconds": 10} if desired_status["resources-ready"] == "False" else {}
            )
            return {
                "status": desired_status,
                "attachments": desired_resources,
                **resync_after,
            }

        def do_POST(self):  # noqa: N802
            """Serve the sync() function as a JSON webhook."""
            observed = json.loads(self.rfile.read(int(self.headers.get("content-length"))))
            logger.info(f"Request is  {observed}")
            try:
                desired = self.sync(observed["object"], observed["attachments"])
            except ParserError as e:
                logger.error(f"generate_manifests: {e}")
                self.send_error(500, "Problem with manifest templates")
                return
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes(json.dumps(desired), "utf-8"))

    return HTTPServer((url, int(controller_port)), Controller)


def generate_manifests(manifest_folder: str, namespace: str) -> list[dict]:
    """For each file in templates_folder generate a yaml with populated context."""
    manifest_files = glob.glob(f"{manifest_folder}/**/*.yaml")
    logger.info(f"found files {manifest_files}")
    manifests = []
    for manifest_file in manifest_files:
        with open(manifest_file) as f:
            try:
                manifest = yaml.safe_load(f)
            except ParserError as e:
                raise e
        manifest["metadata"]["namespace"] = namespace
        manifests.append(manifest)
    return manifests
