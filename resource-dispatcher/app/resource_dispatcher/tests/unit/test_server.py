#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Unit tests for server module."""

from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest
from jinja2.exceptions import TemplateError
from yaml.parser import ParserError

from resource_dispatcher.src.server import (
    _resolve_manifest_conflicts,
    generate_manifests,
    run_server,
    server_factory,
)

PORT = 1234  # HTTPServer randomly assigns the port to a free port
LABEL = "test.label"
FOLDER = "./resource_dispatcher/tests/test_data_folder"
FOLDER_CORRUPTED = "./resource_dispatcher/tests/test_data_folder_corrupted"
FOLDER_INVALID_JINJA2 = "./resource_dispatcher/tests/test_data_folder_invalid_jinja"


class TestServer:
    """Unit test class for server module unit tests."""

    @patch("resource_dispatcher.src.server.server_factory")
    def test_run_server(self, server_factory: MagicMock):
        """Test run_server function."""
        run_server(PORT, LABEL, FOLDER)
        server_factory.assert_called()

    def test_server_factory(self):
        """Test if server_factory creates HTTPServer object."""
        server = server_factory(PORT, LABEL, FOLDER)

        assert type(server) is HTTPServer
        assert server.server_port == PORT

    def test_generate_manifests(self):
        """Test if function generates manifests for example folder."""
        manifests = generate_manifests(FOLDER, namespace="namespace")
        assert len(manifests) == 8
        assert manifests[0]["metadata"]["namespace"] == "namespace"

    def test_generate_manifests_failure(self):
        """Test if function generates manifests for example folder."""
        with pytest.raises(ParserError):
            generate_manifests(FOLDER_CORRUPTED, namespace="namespace")

    def test_generate_manifests_invalid_jinja2(self):
        """Test if appropriate error is raised when Jinja2 template is invalid."""
        with pytest.raises(TemplateError):
            generate_manifests(FOLDER_INVALID_JINJA2, namespace="namespace")

    def test_generate_manifests_pinned_overrides_global(self):
        """Pinned manifest overrides global in same target namespace."""
        manifests = generate_manifests(FOLDER, namespace="profile-a")
        artifact_secrets = [
            m
            for m in manifests
            if m["kind"] == "Secret" and m["metadata"]["name"] == "mlpipeline-minio-artifact"
        ]
        assert len(artifact_secrets) == 1, "Expected exactly one mlpipeline-minio-artifact secret"
        assert artifact_secrets[0]["stringData"]["accesskey"] == "pinned-access-key"

    def test_generate_manifests_global_applied_when_no_override(self):
        """Global manifest is used as-is when there is no pinned override for the namespace."""
        manifests = generate_manifests(FOLDER, namespace="profile-b")
        artifact_secrets = [
            m
            for m in manifests
            if m["kind"] == "Secret" and m["metadata"]["name"] == "mlpipeline-minio-artifact"
        ]
        assert len(artifact_secrets) == 1, "Expected exactly one mlpipeline-minio-artifact secret"
        assert artifact_secrets[0]["stringData"]["accesskey"] == "value"


class TestResolveManifestConflicts:
    """Unit tests for the _resolve_manifest_conflicts helper."""

    def _make_manifest(self, name: str, access_key: str = "value") -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": "ns"},
            "stringData": {"accesskey": access_key},
        }

    def test_no_conflict_returns_all(self):
        """Manifests with distinct names are all returned unchanged."""
        candidates = [
            (False, self._make_manifest("foo")),
            (False, self._make_manifest("bar")),
        ]
        result = _resolve_manifest_conflicts(candidates, "ns")
        names = {m["metadata"]["name"] for m in result}
        assert names == {"foo", "bar"}

    def test_pinned_overrides_global(self):
        """Pinned manifest replaces the global one when they share the same name."""
        global_m = self._make_manifest("foo", access_key="global")
        pinned_m = self._make_manifest("foo", access_key="pinned")
        candidates = [(False, global_m), (True, pinned_m)]
        result = _resolve_manifest_conflicts(candidates, "ns")
        assert len(result) == 1
        assert result[0]["stringData"]["accesskey"] == "pinned"

    def test_global_only_returned_when_no_pinned(self):
        """A global manifest is returned as-is when there is no pinned counterpart."""
        global_m = self._make_manifest("foo", access_key="global")
        candidates = [(False, global_m)]
        result = _resolve_manifest_conflicts(candidates, "ns")
        assert len(result) == 1
        assert result[0]["stringData"]["accesskey"] == "global"

    def test_multiple_pinned_same_name_keeps_first(self):
        """When multiple pinned manifests share a name, only the first is kept."""
        pinned_a = self._make_manifest("foo", access_key="first")
        pinned_b = self._make_manifest("foo", access_key="second")
        candidates = [(True, pinned_a), (True, pinned_b)]
        result = _resolve_manifest_conflicts(candidates, "ns")
        assert len(result) == 1
        assert result[0]["stringData"]["accesskey"] == "first"
