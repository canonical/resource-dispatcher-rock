#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Handle command line arguments."""

import argparse
import os


class EnvDefault(argparse.Action):
    """
    Argparse Action which sets the value based on environment variable and parameters.

    If the value is missing use environment variable if presented otherwise use default value.
    """

    def __init__(self, envvar, required=True, default=None, **kwargs):
        """Specify the parameters for given argument."""
        if envvar in os.environ:
            default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """Call the method to set the name attribute."""
        setattr(namespace, self.dest, values)
