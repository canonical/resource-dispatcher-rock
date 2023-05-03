#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Set up logging."""

import logging
import os


def setup_custom_logger(name):
    """Set up logger with specific formatter."""
    formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level=os.getenv("LOGGER_LEVEL", "INFO").upper())
    logger.addHandler(handler)
    return logger
