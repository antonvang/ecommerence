"""Persistent offline research queue, independent evaluation and paper simulation.

No exchange connectors, credentials, live orders, or automatic approvals. A
forward-paper study requires an externally signed, pre-window protocol.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
COPYBOT = HERE.parents[3]
R3 = HERE.parent / "r3"
STREAM_REGISTRY = COPYBOT / "research/desk/stream_registry.json"
sys.path.insert(0, str(HERE))
from job_store import JobStore, LeaseLostError


class StudyError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise StudyError(message)


def read_json(path):
    def reject(value):
        raise StudyError("Non-JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value).encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name,
                                         mode="wb", delete=False) as stream:
            temporary = stream.name
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def engines():
    harness = load_module("operations_harness", R3 / "run_mutants.py")
    harness.verify_frozen()
    reference = load_module("operations_reference", R3 / "ref_eval.py")
    sys.path.insert(0, str(COPYBOT))
    from research.desk.crosscheck import claude_eval_v111
    return harness, reference, claude_eval_v111


def implementation_hash():
    components = ("research_runner.py", "study_builder.py", "paper_engine.py", "job_store.py", "authorization.py")
    return digest({name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in components})


def protocol_bundle(study):
    """Everything the owner freezes before seeing forward observations."""
    return dict(schema_version=study["schema_version"], study_id=study["study_id"],
                mode=study["mode"], created_at=study["created_at"],
                source_identity={**source_identity(study["source"]), "implementation_sha256": implementation_hash()},
                alpha=study["alpha"], q_fdr=study["q_fdr"],
                candidates=[{key: candidate[key] for key in
                             ("candidate_id", "family", "protocol", "paper_plan")}
                            for candidate in study["candidates"]])


def source_identity(source):
    if source.get("kind") == "synthetic":
        return source
    return {**{key: source.get(key) for key in ("kind", "source_id", "adapter_version")},
            "registry_sha256": hashlib.sha256(STREAM_REGISTRY.read_bytes()).hexdigest()}


def data_bundle(study):
    return [{key: candidate[key] for key in
             ("candidate_id", "fixture", "paper_events", "terminal_marks")}
            for candidate in study["candidates"]]


def validate_study(study):
    require(isinstance(study, dict), "study must be an object")
    required = {"schema_version", "study_id", "mode", "created_at", "alpha", "q_fdr", "source", "candidates"}
    require(required <= study.keys(), "missing study fields")
    require(not study.keys() - required - {"approval"}, "unknown study fields")
    require(type(study["schema_version"]) is int and study["schema_version"] == 1, "unknown schema")
    require(isinstance(study["study_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]+", study["study_id"]), "unsafe study id")
    require(study["mode"] in ("synthetic", "forward_paper"), "unsupported study mode")
    require(type(study["created_at"]) is int and 0 <= study["created_at"] <= 4102444800, "bad freeze time")
    for key in ("alpha", "q_fdr"):
        require(type(study[key]) in (int, float) and 0 < study[key] < 1, "bad " + key)
    require(isinstance(study["source"], dict), "source metadata required")
    require(study["source"].get("kind") == ("synthetic" if study["mode"] == "synthetic" else "local_forward_export"), "source mode mismatch")
    if study["mode"] == "forward_paper":
        require(set(study["source"]) == {"kind", "source_id", "adapter_version", "receipt", "signature"}, "forward export requires source identity and signed capture receipt")
        require(all(isinstance(study["source"][key], str) and study["source"][key]
                    for key in ("source_id", "adapter_version")), "missing forward source identity")
    require(isinstance(study["candidates"], list) and 1 <= len(study["candidates"]) <= 64, "candidate budget must be 1..64")
    identifiers = set()
    for candidate in study["candidates"]:
        fields = {"candidate_id", "family", "protocol", "fixture", "paper_plan", "paper_events", "terminal_marks"}
        require(isinstance(candidate, dict) and candidate.keys() == fields, "bad candidate schema")
        identifier = candidate["candidate_id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9_-]+", identifier), "bad candidate id")
        require(identifier not in identifiers, "duplicate candidate id")
        identifiers.add(identifier)
        require(isinstance(candidate["family"], str) and candidate["family"], "empty family")
        protocol, fixture = candidate["protocol"], candidate["fixture"]
        require(isinstance(protocol, dict) and isinstance(fixture, dict), "bad protocol or fixture")
        require(len(fixture.get("hypotheses", [])) == 1, "one predeclared primary per candidate")
        hypothesis = fixture["hypotheses"][0]
        require(hypothesis.get("hid") == identifier and hypothesis.get("family") == candidate["family"], "primary identity mismatch")
        for key in ("signal_key", "rule", "cost_bps", "funding"):
            require(key in protocol and canonical(protocol[key]) == canonical(hypothesis.get(key)), "protocol mismatch: " + key)
        for key in ("window", "cadence_s", "universe"):
            require(key in protocol and canonical(protocol[key]) == canonical(fixture.get(key)), "protocol mismatch: " + key)
        require(canonical(fixture.get("alpha")) == canonical(study["alpha"])
                and canonical(fixture.get("q_fdr")) == canonical(study["q_fdr"]), "study thresholds mismatch")
        require(fixture.get("ledger_requests") == [], "candidate cannot provide a separate statistical ledger")
        require(isinstance(candidate["paper_events"], list) and isinstance(candidate["paper_plan"], dict), "paper input required")
        require(candidate["paper_plan"].get("protocol_id") == identifier, "paper protocol id mismatch")
        require(study["created_at"] <= fixture["window"]["start"], "protocol freeze occurs after window start")
        validate_data_binding(candidate)
    canonical(study)
    return study


def validate_data_binding(candidate):
    """The two execution models must use the same observed path and signals."""
    fixture, protocol = candidate["fixture"], candidate["protocol"]
    observations, events = fixture.get("observations"), candidate["paper_events"]
    require(isinstance(observations, list), "observations must be a list")
    require(len(events) == len(observations), "paper/evaluation row count differs")
    start, end = protocol["window"].get("start"), protocol["window"].get("end")
    cadence = protocol["cadence_s"]
    embargo = protocol["window"].get("embargo_s", 0)
    require(all(type(value) is int for value in (start, end, cadence, embargo))
            and cadence > 0 and start < end and 0 <= embargo < end - start, "bad operational grid")
    grid = range(start, end, cadence)
    require(len(grid) <= 20000 and len(events) <= 200000, "operational data budget exceeded")
    require(protocol.get("recipe") in ("momentum", "reversal", "funding_carry")
            and type(protocol.get("lookback")) is int and 1 <= protocol["lookback"] <= 1000,
            "unregistered recipe or invalid lookback")
    universe = protocol["universe"]
    require(isinstance(universe, dict) and 1 <= len(universe) <= 64, "bad operational universe")
    require(set(candidate["paper_plan"].get("allowed_assets", [])) == set(universe), "paper universe differs from protocol")
    rows, grouped = {}, {}
    for row in observations:
        require(isinstance(row, dict) and type(row.get("ts")) is int and isinstance(row.get("asset"), str), "bad observation identity")
        key = (row["ts"], row["asset"])
        require(start + embargo <= key[0] < end and (key[0] - start) % cadence == 0, "offgrid or embargo observation cannot be paper traded")
        listing = universe.get(key[1])
        require(isinstance(listing, dict) and listing.get("listed_from", end) <= key[0]
                and (listing.get("delisted_at") is None or key[0] < listing["delisted_at"]),
                "nonmember observation cannot be paper traded")
        require(key not in rows, "operational input contains duplicate observations")
        rows[key] = row
    seen = set()
    event_order = []
    for event in events:
        require(isinstance(event, dict), "bad paper event")
        key = (event.get("ts"), event.get("asset"))
        require(key in rows and key not in seen, "paper event has no unique matching observation")
        seen.add(key)
        event_order.append(key)
        row = rows[key]
        signal = row.get("signals", {}).get(protocol["signal_key"])
        require(isinstance(signal, dict), "missing operational signal")
        value = signal.get("value")
        require(type(value) in (int, float) and math.isfinite(value), "missing/nonfinite operational signal")
        weight = float((value > 0) - (value < 0)) if protocol["rule"] == "sign" else min(1.0, max(-1.0, value))
        require(event.get("signal") == weight and event.get("avail_ts") == signal.get("avail_ts"), "paper/evaluation signal mismatch")
        rate = row.get("funding") if protocol["funding"] else 0
        require(event.get("funding_rate", 0) == rate, "paper/evaluation funding mismatch")
        require(type(event.get("bid")) in (int, float) and type(event.get("ask")) in (int, float), "missing paper quote")
        mid = event["bid"] / 2 + event["ask"] / 2
        require(math.isfinite(mid) and mid > 0, "invalid paper mid")
        grouped.setdefault(key[1], []).append((key[0], mid, row))
    require(event_order == sorted(event_order), "paper events must be sorted by time and asset")
    expected = {(ts, asset) for ts in grid if ts >= start + embargo for asset, listing in universe.items()
                if listing["listed_from"] <= ts and (listing["delisted_at"] is None or ts < listing["delisted_at"])}
    require(set(rows) == expected, "incomplete forward grid; gaps are not imputed")
    require(isinstance(candidate["terminal_marks"], dict) and set(candidate["terminal_marks"]) == set(grouped), "terminal marks required for all assets")
    for asset, bars in grouped.items():
        bars.sort(key=lambda bar: bar[0])
        terminal = candidate["terminal_marks"][asset]
        require(type(terminal) in (int, float) and math.isfinite(terminal) and terminal > 0, "bad terminal mark")
        for i, (_, mid, row) in enumerate(bars):
            closing = bars[i + 1][1] if i + 1 < len(bars) else terminal
            ret = row.get("ret")
            require(type(ret) in (int, float) and math.isfinite(ret)
                    and math.isclose(ret, closing / mid - 1, rel_tol=1e-12, abs_tol=1e-12), "paper/evaluation return path mismatch")
        from study_builder import signals_from_history
        calculated = signals_from_history(protocol["recipe"], protocol["lookback"],
            [mid for _, mid, _ in bars] + [terminal], [row["funding"] for _, _, row in bars])
        for (_, _, row), calculated_signal in zip(bars, calculated):
            observed_signal = row["signals"][protocol["signal_key"]]["value"]
            require(math.isclose(observed_signal, calculated_signal, rel_tol=1e-12, abs_tol=1e-12),
                    "signal is not the causal output of the frozen recipe")


def submit(study, db_path, max_attempts=2):
    validate_study(study)
    _, reference, _ = engines()
    for candidate in study["candidates"]:
        errors = reference.validate(candidate["fixture"])
        require(not errors, "invalid candidate fixture: " + canonical(errors))
    plan_hash = digest(study)
    protocol_hash = digest(protocol_bundle(study))
    context = {key: study[key] for key in ("study_id", "mode", "created_at", "alpha", "q_fdr", "source")}
    context.update(plan_sha256=plan_hash, protocol_sha256=protocol_hash,
                   implementation_sha256=implementation_hash(),
                   source_registry_sha256=(hashlib.sha256(STREAM_REGISTRY.read_bytes()).hexdigest()
                                           if study["mode"] == "forward_paper" else None),
                   data_sha256=digest(data_bundle(study)),
                   window_start=min(c["protocol"]["window"]["start"] for c in study["candidates"]),
                   window_end=max(c["protocol"]["window"]["end"] for c in study["candidates"]),
                   candidate_ids=[candidate["candidate_id"] for candidate in study["candidates"]],
                   approval=study.get("approval"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with JobStore(db_path) as store:
        require(all(job["payload"].get("context", {}).get("plan_sha256") == plan_hash
                    for job in store.list_jobs()), "database belongs to a different frozen study")
        for candidate in study["candidates"]:
            store.enqueue(study["study_id"] + ":" + candidate["candidate_id"],
                          dict(context=context, candidate=candidate), max_attempts=max_attempts)
        return dict(study_id=study["study_id"], plan_sha256=plan_hash,
                    protocol_sha256=protocol_hash, counts=store.counts())


def approval_check(payload, owner_signers, now):
    context, candidate = payload["context"], payload["candidate"]
    if context["mode"] == "synthetic":
        return dict(status="SYNTHETIC_ONLY", reasons=[])
    trust = owner_signers if isinstance(owner_signers, dict) else dict(owner=owner_signers, collector=None)
    owner_signers = trust.get("owner")
    authorization_db = trust.get("authorization_db")
    if owner_signers is None or authorization_db is None:
        return dict(status="BLOCKED_OWNER_APPROVAL", reasons=["pre-window authorization registry and trusted owner signers required"])
    policy = source_policy(context)
    if policy["status"] != "SOURCE_ALLOWED":
        return policy
    if context["window_end"] > now:
        return dict(status="BLOCKED_FORWARD_WINDOW", reasons=["complete forward window is not available"])
    from authorization import verify_authorization
    authorization = verify_authorization(context["protocol_sha256"], context["study_id"],
        context["window_start"], owner_signers, authorization_db)
    if authorization.get("status") != "OWNER_APPROVED":
        return authorization
    provenance = verify_capture(context, trust.get("collector"), now)
    if provenance["status"] != "VERIFIED_CAPTURE":
        return provenance
    return {**authorization, "provenance": provenance}


def source_policy(context):
    raw = STREAM_REGISTRY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != context.get("source_registry_sha256"):
        return dict(status="BLOCKED_SOURCE_POLICY", reasons=["stream registry changed since the study was frozen"])
    registry = json.loads(raw)
    source_id = context["source"]["source_id"]
    matches = [stream for stream in registry["streams"] if stream["id"] == source_id]
    if len(matches) != 1 or matches[0]["status"] != "EXISTING_ACTIVE" or source_id.startswith("pm_lp"):
        return dict(status="BLOCKED_SOURCE_POLICY", reasons=["source is not an approved existing stream for this isolated runner"])
    start, end = context["window_start"], context["window_end"]
    if start < 1735689600 and 1704067200 < end:
        return dict(status="BLOCKED_SOURCE_POLICY", reasons=["2024 holdout is protected"])
    match = re.search(r"(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?", str(matches[0].get("started", "")))
    if not match:
        return dict(status="BLOCKED_SOURCE_POLICY", reasons=["source has no durable forward start time"])
    first = datetime.fromisoformat(match[1] + "T" + (match[2] or "00:00")).replace(tzinfo=timezone.utc)
    if start < int(first.timestamp()):
        return dict(status="BLOCKED_SOURCE_POLICY", reasons=["window precedes the stream's forward start"])
    return dict(status="SOURCE_ALLOWED", registry_sha256=context["source_registry_sha256"])


def verify_capture(context, collector_signers, now):
    source = context["source"]
    receipt, signature = source.get("receipt"), source.get("signature")
    if collector_signers is None or not Path(collector_signers).is_file():
        return dict(status="BLOCKED_SOURCE_PROVENANCE", reasons=["trusted collector signers file required"])
    expected = dict(schema_version=1, source_id=source["source_id"], adapter_version=source["adapter_version"],
                    protocol_sha256=context["protocol_sha256"], data_sha256=context["data_sha256"],
                    captured_from=context["window_start"], captured_to=context["window_end"])
    if receipt != expected or not isinstance(signature, str) or not signature or context["window_end"] > now:
        return dict(status="BLOCKED_SOURCE_PROVENANCE", reasons=["capture receipt does not bind the complete frozen forward input"])
    with tempfile.TemporaryDirectory(prefix="copybot-capture-") as directory:
        path = Path(directory) / "capture.sig"
        path.write_text(signature, encoding="utf-8")
        result = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(collector_signers),
            "-I", "collector", "-n", "copybot-forward-data", "-s", str(path)],
            input=canonical(receipt).encode(), capture_output=True, timeout=30)
    if result.returncode:
        return dict(status="BLOCKED_SOURCE_PROVENANCE", reasons=["capture signature invalid"])
    return dict(status="VERIFIED_CAPTURE", receipt_sha256=digest(receipt),
                collector_signers_sha256=hashlib.sha256(Path(collector_signers).read_bytes()).hexdigest())


def evaluate_payload(payload, owner_signers=None, now=None):
    now = int(time.time()) if now is None else now
    harness, reference, frozen = engines()
    require(payload["context"].get("implementation_sha256") == implementation_hash(),
            "research implementation changed since protocol freeze")
    candidate = payload["candidate"]
    authorization = approval_check(payload, owner_signers, now)
    if authorization["status"].startswith("BLOCKED"):
        return dict(status=authorization["status"], authorization=authorization,
                    candidate_id=candidate["candidate_id"], mode=payload["context"]["mode"])
    fixture = candidate["fixture"]
    wanted, actual = reference.evaluate(fixture), frozen.evaluate(fixture)
    differences = harness.differences(wanted, actual)
    if differences:
        return dict(status="BLOCKED_CROSSCHECK", differences=differences,
                    candidate_id=candidate["candidate_id"], mode=payload["context"]["mode"])
    if wanted["status"] != "OK":
        return dict(status="REFUSED_INPUT", evaluation=wanted, candidate_id=candidate["candidate_id"],
                    mode=payload["context"]["mode"])
    from paper_engine import simulate_paper
    paper = simulate_paper(candidate["paper_plan"], candidate["paper_events"])
    ready = paper.get("status") in ("OK", "RISK_STOPPED") and paper.get("errors") == []
    return dict(status="COMPLETE" if ready else "BLOCKED_PAPER_QUALITY", mode=payload["context"]["mode"],
                candidate_id=candidate["candidate_id"], fixture_sha256=digest(fixture),
                protocol_sha256=payload["context"]["protocol_sha256"], authorization=authorization,
                evaluation=wanted, paper=paper,
                paper_eligible=paper.get("status") == "OK",
                paper_valuation_ts=max((event["ts"] for event in candidate["paper_events"]), default=None),
                evaluation_window_end=candidate["protocol"]["window"]["end"],
                interpretation="synthetic exercise" if payload["context"]["mode"] == "synthetic" else "forward paper observation",
                automatic_promotion=False)


class _LeaseHeartbeat:
    """Renew a fenced lease using a connection owned by the heartbeat thread."""

    def __init__(self, db_path, worker_id, job, lease_s):
        import threading
        self.db_path = db_path
        self.job_id, self.token = job["job_id"], job["token"]
        self.lease_s = lease_s
        # With integer-second expiry and lease>=3, a one-second interval leaves
        # time to renew even when the initial claim occurs near a second edge.
        self.interval = min(1.0, lease_s / 3)
        self._stop = threading.Event()
        self._started = threading.Event()
        self.error = None
        self._thread = threading.Thread(target=self._run,
            name="lease-heartbeat-" + worker_id + "-" + self.job_id, daemon=True)

    def _run(self):
        try:
            with JobStore(self.db_path) as store:
                while not self._stop.is_set():
                    store.renew(self.job_id, self.token, int(time.time()), self.lease_s)
                    self._started.set()
                    if self._stop.wait(self.interval):
                        break
        except Exception as error:
            self.error = error
        finally:
            self._started.set()

    def start(self):
        self._thread.start()
        # The computation starts only after the second connection has renewed
        # once, or reported a failure. It never runs with a failed heartbeat.
        self._started.wait()
        self.check()

    def check(self):
        if self.error is not None:
            if isinstance(self.error, LeaseLostError):
                raise self.error
            raise RuntimeError("Lease heartbeat failed: " + str(self.error)) from self.error

    def stop(self):
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join()


def worker(db_path, worker_id, owner_signers=None, lease_s=300):
    require(type(lease_s) is int and lease_s >= 3, "worker lease must be an integer >=3 seconds")
    engines()  # code/integrity gate before spending a job attempt
    with JobStore(db_path) as store:
        while True:
            unfinished = [job for job in store.list_jobs() if job["status"] in ("queued", "running")]
            for pending in unfinished:
                if pending["payload"].get("context", {}).get("mode") == "forward_paper":
                    gate = approval_check(pending["payload"], owner_signers, int(time.time()))
                    if gate["status"].startswith("BLOCKED"):
                        return  # keep queued and preserve retry budget until the prerequisite exists
            job = store.claim(worker_id, int(time.time()), lease_s)
            if job is None:
                return
            heartbeat = _LeaseHeartbeat(db_path, worker_id, job, lease_s)
            try:
                heartbeat.start()
                result = evaluate_payload(job["payload"], owner_signers)
                heartbeat.check()
                store.complete(job["job_id"], job["token"], result, int(time.time()))
            except LeaseLostError:
                pass  # Another token owns this job; this result must be discarded.
            except Exception as error:
                try:
                    store.fail(job["job_id"], job["token"],
                               dict(type=type(error).__name__, message=str(error)), int(time.time()))
                except LeaseLostError:
                    pass  # Failure reporting must not crash a worker after recovery.
            finally:
                heartbeat.stop()


def summary(db_path, owner_signers=None):
    _, reference, _ = engines()
    with JobStore(db_path) as store:
        jobs, counts = store.list_jobs(), store.counts()
    require(jobs, "empty study")
    context = jobs[0]["payload"]["context"]
    require(all(job["payload"]["context"] == context for job in jobs), "mixed study contexts")
    expected_ids = context["candidate_ids"]
    complete = counts["succeeded"] == len(expected_ids) and counts["total"] == len(expected_ids)
    ready = complete and all(job["result"].get("status") == "COMPLETE" for job in jobs)
    results, fingerprints, blocked = {}, {}, []
    by_id = {job["payload"]["candidate"]["candidate_id"]: job for job in jobs}
    for identifier in expected_ids:
        job = by_id.get(identifier)
        if job is None or job["status"] != "succeeded" or job["result"].get("status") != "COMPLETE":
            reason = dict(candidate_id=identifier, status="MISSING" if job is None else
                          job["result"].get("status") if job["result"] else job["status"])
            if job is not None and job["status"] == "queued" and context["mode"] == "forward_paper":
                authorization = approval_check(job["payload"], owner_signers, int(time.time()))
                if authorization["status"].startswith("BLOCKED"):
                    reason.update(status=authorization["status"], reasons=authorization["reasons"])
            blocked.append(reason)
            continue
        candidate = job["payload"]["candidate"]
        h = candidate["fixture"]["hypotheses"][0]
        result = copy.deepcopy(job["result"]["evaluation"]["hypotheses"][identifier])
        fingerprint = (h["family"], h["signal_key"], h["rule"])
        if fingerprint in fingerprints:
            result.update(status="DUPLICATE", duplicate_of=fingerprints[fingerprint])
        else:
            fingerprints[fingerprint] = identifier
        results[identifier] = result
    # A partial batch never supplies inferential decisions: its full predeclared m is unknown.
    if ready:
        reference.adjust_multiple(results, context["alpha"], context["q_fdr"])
    else:
        for result in results.values():
            result["holm_reject"] = result["bh_reject"] = None
    return dict(schema_version=1, study_id=context["study_id"], mode=context["mode"],
                status="COMPLETE" if ready else "BLOCKED" if complete or counts["failed"]
                or any(item["status"].startswith("BLOCKED") for item in blocked) else "PENDING",
                plan_sha256=context["plan_sha256"], protocol_sha256=context["protocol_sha256"],
                implementation_sha256=context["implementation_sha256"],
                counts=counts, blocked=blocked, predeclared_candidates=len(expected_ids),
                pooled_hypotheses=results, automatic_promotion=False,
                paper={identifier: by_id[identifier]["result"]["paper"] for identifier in results},
                output_semantics="synthetic research exercise" if context["mode"] == "synthetic" else "paper only")


def run(db_path, workers=1, owner_signers=None):
    require(type(workers) is int and 1 <= workers <= 16, "workers must be 1..16")
    if isinstance(owner_signers, dict) and owner_signers.get("authorization_db") is not None:
        require(Path(db_path).resolve() != Path(owner_signers["authorization_db"]).resolve(),
                "authorization registry and research queue must be separate databases")
    engines()
    with JobStore(db_path) as store:
        require(all(job["payload"].get("context", {}).get("implementation_sha256") == implementation_hash()
                    for job in store.list_jobs()), "queue belongs to another research implementation")
    if workers == 1:
        worker(str(db_path), "worker-0", owner_signers)
    else:
        context = multiprocessing.get_context("spawn")
        processes = [context.Process(target=worker, args=(str(db_path), "worker-" + str(i), owner_signers))
                     for i in range(workers)]
        for process in processes:
            process.start()
        for process in processes:
            process.join()
        require(all(process.exitcode == 0 for process in processes), "worker process failed")
    return summary(db_path, owner_signers)


def doctor(report_dir, full=False):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    harness, _, _ = engines()
    report = dict(status="PASS", ts=int(time.time()), frozen=harness.verify_frozen(),
                  implementation_sha256=implementation_hash(), full_mutation_gate=full)
    if full:
        process = subprocess.run([sys.executable, "-B", str(R3 / "run_mutants.py"), "--phase", "both",
                                  "--report-dir", str(report_dir / "mutation")],
                                 capture_output=True, text=True)
        report.update(status="PASS" if process.returncode == 0 else "BLOCKED",
                      mutation_exit_code=process.returncode, mutation_output=process.stdout[-6000:],
                      mutation_error=process.stderr[-6000:])
    write_json(report_dir / "doctor.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--out", type=Path, required=True)
    demo.add_argument("--candidates", type=int, default=9)
    demo.add_argument("--seed", type=int, default=52)
    demo.add_argument("--workers", type=int, default=2)
    sub = commands.add_parser("submit")
    sub.add_argument("study", type=Path)
    sub.add_argument("--db", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--db", type=Path, required=True)
    execute.add_argument("--out", type=Path, required=True)
    execute.add_argument("--workers", type=int, default=2)
    execute.add_argument("--owner-signers", type=Path)
    execute.add_argument("--collector-signers", type=Path)
    execute.add_argument("--authorization-db", type=Path)
    status = commands.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    status.add_argument("--out", type=Path)
    check = commands.add_parser("doctor")
    check.add_argument("--out", type=Path, required=True)
    check.add_argument("--full", action="store_true")
    protocol = commands.add_parser("protocol")
    protocol.add_argument("study", type=Path)
    protocol.add_argument("--out", type=Path, required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("protocol", type=Path)
    freeze.add_argument("--statement", type=Path, required=True)
    freeze.add_argument("--signature", type=Path, required=True)
    freeze.add_argument("--owner-signers", type=Path, required=True)
    freeze.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            from study_builder import build_demo
            study = build_demo(seed=args.seed, candidates=args.candidates)
            args.out.mkdir(parents=True, exist_ok=True)
            write_json(args.out / "study.json", study)
            submit(study, args.out / "jobs.sqlite3")
            report = run(args.out / "jobs.sqlite3", args.workers)
            write_json(args.out / "report.json", report)
        elif args.command == "submit":
            report = submit(read_json(args.study), args.db)
        elif args.command == "run":
            trust = dict(owner=str(args.owner_signers) if args.owner_signers else None,
                         collector=str(args.collector_signers) if args.collector_signers else None,
                         authorization_db=str(args.authorization_db) if args.authorization_db else None)
            report = run(args.db, args.workers, trust)
            write_json(args.out, report)
        elif args.command == "status":
            report = summary(args.db)
            if args.out:
                write_json(args.out, report)
        elif args.command == "doctor":
            report = doctor(args.out, args.full)
        elif args.command == "protocol":
            study = validate_study(read_json(args.study))
            packet = protocol_bundle(study)
            write_json(args.out, packet)
            report = dict(status="PREPARED", protocol_sha256=digest(packet), path=str(args.out))
        else:
            from authorization import freeze_protocol
            report = freeze_protocol(read_json(args.protocol), read_json(args.statement),
                args.signature.read_text(encoding="utf-8"), args.owner_signers, args.db, int(time.time()))
        print(canonical({key: value for key, value in report.items() if key not in
                         ("paper", "pooled_hypotheses", "mutation_output")}))
        return 1 if report.get("status") in ("BLOCKED", "PENDING", "BLOCKED_OWNER_APPROVAL") else 0
    except Exception as error:
        print(canonical(dict(status="BLOCKED", type=type(error).__name__, error=str(error))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
