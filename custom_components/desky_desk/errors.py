"""Errors raised by commands to the desk."""


class DeskError(Exception):
    """A command could not be sent to the desk."""


class DeskNotConnectedError(DeskError):
    """The desk is not connected."""


class DeskCommandError(DeskError):
    """Writing a command to the desk failed."""
