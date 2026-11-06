"""A semantic interruption probe added after non-atomic M41 survived phase 1."""
import builtins
from pathlib import Path
import tempfile
from unittest import mock


def check(evaluator):
    failures = []
    original_open = builtins.open
    original_fdopen = evaluator.os.fdopen

    class InterruptedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, text):
            self.stream.write(text[:max(1, len(text) // 2)])
            self.stream.flush()
            raise OSError("injected failure halfway through write")

        def __getattr__(self, name):
            return getattr(self.stream, name)

    def opened(file, mode="r", *args, **kwargs):
        stream = original_open(file, mode, *args, **kwargs)
        return InterruptedStream(stream) if any(flag in mode for flag in ("w", "a", "x")) else stream

    def fdopened(fd, *args, **kwargs):
        return InterruptedStream(original_fdopen(fd, *args, **kwargs))

    with tempfile.TemporaryDirectory(prefix="r3-interruption-", dir="/workspace/work") as directory:
        path = Path(directory) / "result.json"
        previous = b'{"complete_previous_result":true}'
        path.write_bytes(previous)
        interrupted = False
        try:
            with mock.patch.object(builtins, "open", opened), mock.patch.object(evaluator.os, "fdopen", fdopened):
                evaluator.write_atomic(str(path), '{"complete_next_result":true}')
        except OSError:
            interrupted = True
        observed = path.read_bytes()
        if not interrupted or observed != previous:
            failures.append(dict(test="added.atomic_interruption_preserves_previous_file",
                                 interruption_observed=interrupted,
                                 previous=previous.decode(), actual=observed.decode(errors="replace")))
    return failures
