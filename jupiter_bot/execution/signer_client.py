"""Engine side of the signer: run signer.py as a separate, restricted process."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

from ..core import Rejected
from .solana_tx import b58decode

SIGNER_PATH = Path(__file__).resolve().with_name("signer.py")
MINIMAL_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}


class SignerRefused(Rejected):
    pass


class SubprocessSigner:
    def __init__(self, paths, python=None, timeout=30, runner=subprocess.run):
        self.paths, self.python, self.timeout, self.runner = paths, python or sys.executable, timeout, runner

    def command(self):
        # -I: isolated mode (no PYTHON* env, no user site-packages, no cwd/script dir on sys.path)
        return [self.python, "-I", str(SIGNER_PATH), "--mandate", str(self.paths.mandate),
                "--arm", str(self.paths.arm), "--state", str(self.paths.signer_state)]

    def sign(self, message, bundle):
        request = json.dumps({"message_b64": base64.b64encode(message).decode(), "bundle": bundle})
        try:
            done = self.runner(self.command(), input=request.encode(), capture_output=True,
                               timeout=self.timeout, env=dict(MINIMAL_ENV), cwd="/", check=False)
        except subprocess.TimeoutExpired:
            raise SignerRefused("signer timed out") from None
        try:
            answer = json.loads(done.stdout.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            answer = {}
        if done.returncode != 0 or "signature" not in answer:
            raise SignerRefused("signer: %s" % str(answer.get("error", "exit %d" % done.returncode))[:300])
        return b58decode(answer["signature"], 64)
