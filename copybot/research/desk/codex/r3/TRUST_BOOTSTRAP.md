# Readiness trust bootstrap

This is an explicit, reviewed local source snapshot, not automatic trust on
first use. `READINESS_INTEGRITY.json` records the selected evaluator/test
dependency closure, all 79 input fixtures, all 79 expected outputs, the 45
mutant copies, and the control artifacts. `run_mutants.py` pins the manifest's
SHA-256 as a code constant. The baseline contract has a separate pinned digest.
The harness never regenerates or updates either trust document at startup.

The source dependency closure was derived by parsing local Python import
statements starting at the frozen evaluator and the three requested Claude
test files, recursively including local `research`/`tests` modules and package
initializers. No market observations, network resources, or credentials were
read. The manifest records the Git commit used for this bootstrap and the
original frozen evaluator digest. Inputs and sources must match that reviewed
snapshot before execution and again before a successful phase report is
published. Missing/extra fixture or expected-output files are also rejected.

Updating trusted sources or accepting a new baseline requires an explicit
review of those changes, a new manifest/contract, and an intentional change
to the pinned digest in `run_mutants.py`. An input change is not accepted
merely because the evaluator and mutant both produce a matching new result.
All integrity and baseline gates use explicit exceptions and remain active
with `python -O` or `PYTHONOPTIMIZE`.

The exact accepted baseline difference is only
`R3_13_numeric_ledger.errors[0].path`: independent reference `""`, frozen
Claude `"OverflowError"`. No new difference, missing known difference,
changed value, or changed fixture inventory is accepted silently. The
numeric comparison tolerance remains unchanged at 1e-9 times
`max(1, abs(a), abs(b))`; the accepted exception concerns an exact string.

Fresh reports have unique run IDs and current UTC/Git/Python/harness/trust
metadata. `run_phase` writes a new phase report; `finalize` requires those
fresh objects and publishes a separate summary. Historical INITIAL,
AUGMENTED, and MUTATION_RESULTS reports are read-only evidence. Failed
baseline/integrity gates produce a fresh failure report and a nonzero CLI
exit. Existing report files cannot be replaced by a new publication.

This trust root is the reviewed harness code and its repository delivery.
It is not protection against an actor who can replace that trusted code and
the manifest constants together. The snapshot does not pin the operating
system, Python standard library/interpreter, `ssh-keygen`, or dynamically
loaded external resources; their identities must be controlled by the
execution environment. Static import discovery is not a general sandbox or
a proof of every possible Python dynamic import. The harness remains a
synthetic mutation/control lab, not a live-order execution system.
