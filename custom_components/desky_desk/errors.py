"""Errors raised by commands to the desk."""


class DeskError(Exception):
    """A command could not be sent to the desk."""


class DeskNotConnectedError(DeskError):
    """The desk is not connected."""


class DeskCommandError(DeskError):
    """Writing a command to the desk failed."""


class DeskSettingNotAppliedError(DeskError):
    """The desk reported its old value for a setting, even after it was sent again."""
