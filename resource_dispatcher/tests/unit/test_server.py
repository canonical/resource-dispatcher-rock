#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Unit tests for server module."""

from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest
from yaml.parser import ParserError

from resource_dispatcher.src.server import generate_manifests, run_server, server_factory

PORT = 1234  # HTTPServer randomly assigns the port to a free port
LABEL = "test.label"
FOLDER = "./resource_dispatcher/tests/test_data_folder"
FOLDER_CORRUPTED = "./resource_dispatcher/tests/test_data_folder_corrupted"


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

        assert type(server) == HTTPServer
        assert server.server_port == PORT

    def test_generate_manifests(self):
        """Test if function generates manifests for example folder."""
        manifests = generate_manifests(FOLDER, namespace="namespace")
        assert len(manifests) == 5
        assert manifests[0]["metadata"]["namespace"] == "namespace"

    def test_generate_manifests_failure(self):
        """Test if function generates manifests for example folder."""
        with pytest.raises(ParserError):
            generate_manifests(FOLDER_CORRUPTED, namespace="namespace")
