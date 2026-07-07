#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Run HTTPServer for Resource Dispatcher."""

import glob
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

import yaml
from jinja2 import Template
from jinja2.exceptions import TemplateError
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
            desired_roles_count = 0
            desired_role_bindings_count = 0
            desired_config_maps_count = 0

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
                elif resource["kind"] == "Role":
                    desired_roles_count += 1
                elif resource["kind"] == "RoleBinding":
                    desired_role_bindings_count += 1
                elif resource["kind"] == "ConfigMap":
                    desired_config_maps_count += 1

            # Just compares number of presented with expected manifests its not comparing contents
            desired_status = {
                "resources-ready": str(
                    len(attachments.get("Secret.v1", [])) == desired_secrets_count
                    and len(attachments.get("ServiceAccount.v1", [])) == desired_svc_accounts_count
                    and len(attachments.get("Role.rbac.authorization.k8s.io/v1", []))
                    == desired_roles_count
                    and len(attachments.get("RoleBinding.rbac.authorization.k8s.io/v1", []))
                    == desired_role_bindings_count
                    and len(attachments.get("PodDefault.kubeflow.org/v1alpha1", []))
                    == desired_pod_defaults_count
                    and len(attachments.get("ConfigMap.v1", [])) == desired_config_maps_count
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
    manifest_files = glob.glob(f"{manifest_folder}/**/*.yaml", recursive=True)
    logger.info(f"found files {manifest_files}")
    candidates = []
    for manifest_file in manifest_files:
        with open(manifest_file) as f:
            try:
                template = Template(f.read())
                rendered_content = template.render(NAMESPACE=namespace)
                manifest = yaml.safe_load(rendered_content)
            except TemplateError as e:
                logger.error(f"Error rendering template {manifest_file}: {e}")
                raise
            except ParserError as e:
                raise e
        metadata = manifest.get("metadata", {})
        manifest_namespace = metadata.get("namespace")

        # Keep resources that are either namespace-agnostic
        # or already target the current namespace.
        # Skip manifests pinned to a different namespace
        # so profile-specific resources are not fanned out.
        if manifest_namespace and manifest_namespace != namespace:
            logger.info(
                "Skipping manifest %s/%s for namespace %s because it targets namespace %s",
                manifest.get("kind", "unknown"),
                metadata.get("name", "unknown"),
                namespace,
                manifest_namespace,
            )
            continue

        is_pinned = bool(manifest_namespace)
        manifest.setdefault("metadata", {})["namespace"] = namespace
        candidates.append((is_pinned, manifest))

    return _resolve_manifest_conflicts(candidates, namespace)


def _resolve_manifest_conflicts(candidates: list[tuple[bool, dict]], namespace: str) -> list[dict]:
    """Resolve name conflicts by preferring namespace-pinned manifests over global ones.

    When a namespace-pinned manifest and a global (unpinned) manifest share the
    same name, the pinned manifest takes precedence for that namespace.  This
    allows per-profile overrides to shadow global defaults without breaking the
    global default for every other namespace.

    If multiple pinned manifests for the same namespace share a name (which the
    charm-side validation should already prevent), the first encountered is kept
    and a warning is logged.

    Args:
        candidates: (is_pinned, manifest) pairs that have already passed the
                    namespace-filter step in generate_manifests.
        namespace:  The target namespace being processed (used for log messages).

    Returns:
        Deduplicated manifest list.
    """
    # Get manifests by name first
    by_name: dict[str, list[tuple[bool, dict]]] = {}
    for is_pinned, manifest in candidates:
        name = manifest.get("metadata", {}).get("name")
        by_name.setdefault(name, []).append((is_pinned, manifest))

    result = []
    for name, group in by_name.items():
        pinned = [m for is_pinned, m in group if is_pinned]
        unpinned = [m for is_pinned, m in group if not is_pinned]

        if pinned:
            if unpinned:
                logger.info(
                    "Manifest '%s' has both a namespace-pinned and a global version for namespace "
                    "'%s'; using the namespace-pinned version.",
                    name,
                    namespace,
                )
            if len(pinned) > 1:
                logger.warning(
                    "Multiple namespace-pinned manifests found for name '%s' in namespace '%s'; "
                    "using the first one.",
                    name,
                    namespace,
                )
            result.append(pinned[0])
        elif unpinned:
            if len(unpinned) > 1:
                logger.warning(
                    "Multiple global manifests found for name '%s' in namespace '%s'; "
                    "using the first one.",
                    name,
                    namespace,
                )
            result.append(unpinned[0])

    return result
