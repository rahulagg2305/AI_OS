"""Errors raised by the Sandbox's execution boundary."""


class SandboxExecutionError(Exception):
    """A sandboxed command could not be executed at all.

    Raised for invalid input (an empty command, a non-existent
    ``working_directory``, a non-positive ``timeout_seconds``/
    ``max_output_bytes``) and for a failure to even start the process
    (e.g. the executable does not exist) — never for the executed
    command's own non-zero exit code, which is a legitimate
    :class:`~ai_os_kernel.sandbox.models.SandboxResult`, not an error.
    The underlying exception, when there is one, is chained via
    ``from``.
    """
