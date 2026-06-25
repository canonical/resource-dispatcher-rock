#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Run Resource Dispatcher server."""

import argparse

from src.envdefault import EnvDefault
from src.server import run_server

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        help="Port on which run the sync server",
        action=EnvDefault,
        envvar="PORT",
        default=80,
    )
    parser.add_argument(
        "--label",
        "-l",
        type=str,
        help="Namespace label to which should be the resources injected",
        action=EnvDefault,
        envvar="TARGET_NAMESPACE_LABEL",
        default="user.kubeflow.org/enabled",
    )
    parser.add_argument(
        "--folder",
        "-f",
        type=str,
        help="Folder wehre resource templates should be stored",
        action=EnvDefault,
        envvar="TEMPLATES_FOLDER",
        default="./resources",
    )
    args = parser.parse_args()
    run_server(args.port, args.label, args.folder)
