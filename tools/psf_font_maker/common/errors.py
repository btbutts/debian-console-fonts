"""The error type the tools raise for problems the user can fix."""


class ToolError(Exception):
    """A problem with the input or the request; the command line reports it and stops."""


class PsfFormatError(ToolError):
    """A file is not a PSF font."""
