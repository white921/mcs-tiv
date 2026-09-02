from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import socket
import ssl
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aioquic.asyncio import connect, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.logger import QuicLogger
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dnslib import A, DNSHeader, DNSRecord, QTYPE, RCODE, RR


DOMAIN = "service.test"
CACHED_IP = "127.0.0.10"
OLD_BACKEND_IP = "127.0.0.2"
NEW_IP = "127.0.0.3"
DNS_IP = "127.0.0.53"
ALPN = ["aeacus-lab"]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    fresh_ip: str
    drop_seconds: float | None
    expected_classification: str


@dataclass
class AttemptResult:
    label: str
    ip: str
    success: bool
    elapsed_ms: float
    total_elapsed_ms: float
    error: str | None
    initial_packets_sent: int
    qlog_file: str


SCENARIOS = {
    "control": Scenario(
        name="control",
        description="旧IPが有効で、最初のQUIC接続が成功する基準ケース",
        fresh_ip=CACHED_IP,
        drop_seconds=0.0,
        expected_classification="initial_success",
    ),
    "transient": Scenario(
        name="transient",
        description="一時的にUDPを破棄し、タイムアウト後の同一IPへの新規接続で復旧する",
        fresh_ip=CACHED_IP,
        drop_seconds=1.4,
        expected_classification="transient_same_ip_recovered",
    ),
    "stale": Scenario(
        name="stale",
        description="古いIPは応答せず、DNSが返す新IPのみ接続できる",
        fresh_ip=NEW_IP,
        drop_seconds=None,
        expected_classification="stale_ip_likely",
    ),
    "persistent": Scenario(
        name="persistent",
        description="DNSのIPは変わらず、同一IPへの新規接続も失敗する",
        fresh_ip=CACHED_IP,
        drop_seconds=None,
        expected_classification="non_dns_or_persistent_unknown",
    ),
    "changed_old_recovers": Scenario(
        name="changed_old_recovers",
        description="DNS応答は変化するが、旧IPも一時障害後に再利用できる",
        fresh_ip=NEW_IP,
        drop_seconds=1.4,
        expected_classification="dns_changed_old_still_usable",
    ),
}


class DnsProtocol(asyncio.DatagramProtocol):
    def __init__(self, answer_ip: str) -> None:
        self.answer_ip = answer_ip
        self.transport: asyncio.DatagramTransport | None = None
        self.queries = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.queries += 1
        try:
            request = DNSRecord.parse(data)
            question = request.q
            reply = request.reply()
            if (
                str(question.qname).rstrip(".") == DOMAIN
                and question.qtype == QTYPE.A
            ):
                reply.add_answer(
                    RR(
                        rname=question.qname,
                        rtype=QTYPE.A,
                        rclass=1,
                        ttl=1,
                        rdata=A(self.answer_ip),
                    )
                )
            else:
                reply.header = DNSHeader(
                    id=request.header.id,
                    qr=1,
                    aa=1,
                    ra=0,
                    rcode=RCODE.NXDOMAIN,
                )
            if self.transport is not None:
                self.transport.sendto(reply.pack(), addr)
        except Exception:
            return


class FaultRelay(asyncio.DatagramProtocol):
    def __init__(
        self,
        backend: tuple[str, int],
        drop_seconds: float | None,
    ) -> None:
        self.backend = backend
        self.drop_seconds = drop_seconds
        self.started_at = time.monotonic()
        self.transport: asyncio.DatagramTransport | None = None
        self.client_addr: tuple[str, int] | None = None
        self.dropped_client_datagrams = 0
        self.forwarded_client_datagrams = 0
        self.forwarded_server_datagrams = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport is None:
            return

        if addr == self.backend:
            if self.client_addr is not None:
                self.forwarded_server_datagrams += 1
                self.transport.sendto(data, self.client_addr)
            return

        self.client_addr = addr
        should_drop = self.drop_seconds is None or (
            time.monotonic() - self.started_at < self.drop_seconds
        )
        if should_drop:
            self.dropped_client_datagrams += 1
            return

        self.forwarded_client_datagrams += 1
        self.transport.sendto(data, self.backend)


def generate_certificate(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)]
    )
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(DOMAIN)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )

    key_path = directory / "server.key"
    cert_path = directory / "server.crt"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def count_initial_packets(qlog: dict[str, Any]) -> int:
    count = 0
    for trace in qlog.get("traces", []):
        for event in trace.get("events", []):
            if event.get("name") != "transport:packet_sent":
                continue
            packet_type = event.get("data", {}).get("header", {}).get("packet_type")
            if packet_type == "initial":
                count += 1
    return count


async def attempt_quic(
    *,
    label: str,
    ip: str,
    port: int,
    timeout_seconds: float,
    qlog_dir: Path,
) -> AttemptResult:
    quic_logger = QuicLogger()
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=ALPN,
        server_name=DOMAIN,
        verify_mode=ssl.CERT_NONE,
        quic_logger=quic_logger,
    )
    started_at = time.monotonic()
    decided_at: float | None = None
    success = False
    error: str | None = None
    handshake_task: asyncio.Task[None] | None = None

    try:
        async with connect(
            ip,
            port,
            configuration=configuration,
            wait_connected=False,
        ) as protocol:
            # wait_connected=False lets us retain the protocol while imposing the
            # experiment deadline. transmit() sends the Initial immediately.
            protocol.transmit()
            handshake_task = asyncio.create_task(protocol.wait_connected())
            done, _ = await asyncio.wait(
                {handshake_task}, timeout=timeout_seconds
            )
            if handshake_task in done:
                await handshake_task
                success = True
                decided_at = time.monotonic()
            else:
                error = f"timeout after {timeout_seconds:.2f}s"
                decided_at = time.monotonic()
    except Exception as exc:  # The exception text is part of the experiment log.
        error = f"{type(exc).__name__}: {exc}"
        decided_at = time.monotonic()
    finally:
        # On a deadline, leaving connect() closes the QUIC connection and resolves
        # wait_connected() with ConnectionError. Consume it so asyncio does not
        # emit an unrelated "Future exception was never retrieved" warning.
        if handshake_task is not None and not handshake_task.done():
            try:
                await handshake_task
            except ConnectionError:
                pass

    finished_at = time.monotonic()
    if decided_at is None:
        decided_at = finished_at
    elapsed_ms = (decided_at - started_at) * 1000
    total_elapsed_ms = (finished_at - started_at) * 1000
    qlog = quic_logger.to_dict()
    qlog_path = qlog_dir / f"{label}.qlog.json"
    qlog_path.write_text(json.dumps(qlog, ensure_ascii=False, indent=2))
    return AttemptResult(
        label=label,
        ip=ip,
        success=success,
        elapsed_ms=round(elapsed_ms, 3),
        total_elapsed_ms=round(total_elapsed_ms, 3),
        error=error,
        initial_packets_sent=count_initial_packets(qlog),
        qlog_file=str(qlog_path),
    )


async def resolve_fresh_ip(port: int, timeout_seconds: float = 1.0) -> str:
    request = DNSRecord.question(DOMAIN, "A")
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        await loop.sock_sendto(sock, request.pack(), (DNS_IP, port))
        data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 2048), timeout_seconds)
    finally:
        sock.close()

    response = DNSRecord.parse(data)
    for answer in response.rr:
        if answer.rtype == QTYPE.A:
            return str(answer.rdata)
    raise RuntimeError("DNS response did not contain an A record")


def classify(
    *,
    initial: AttemptResult,
    cached_ip: str,
    fresh_ip: str | None,
    old_retry: AttemptResult | None,
    fresh_attempt: AttemptResult | None,
) -> str:
    if initial.success:
        return "initial_success"
    if old_retry is None or fresh_ip is None:
        return "insufficient_evidence"

    if fresh_ip == cached_ip:
        if old_retry.success:
            return "transient_same_ip_recovered"
        return "non_dns_or_persistent_unknown"

    fresh_success = fresh_attempt is not None and fresh_attempt.success
    if old_retry.success and fresh_success:
        return "dns_changed_old_still_usable"
    if not old_retry.success and fresh_success:
        return "stale_ip_likely"
    if old_retry.success and not fresh_success:
        return "old_recovered_new_failed"
    return "both_addresses_failed_unknown"


async def run_scenario(
    scenario: Scenario,
    *,
    trial: int,
    index: int,
    cert_path: Path,
    key_path: Path,
    results_dir: Path,
    initial_timeout: float,
    retry_timeout: float,
) -> dict[str, Any]:
    quic_port = 4433 + index
    dns_port = 5353 + index
    scenario_dir = results_dir / scenario.name / f"trial_{trial:03d}"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    server_configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=ALPN,
    )
    server_configuration.load_cert_chain(str(cert_path), str(key_path))

    old_server = await serve(
        OLD_BACKEND_IP,
        quic_port,
        configuration=server_configuration,
    )
    new_server = await serve(
        NEW_IP,
        quic_port,
        configuration=server_configuration,
    )

    loop = asyncio.get_running_loop()
    relay_protocol = FaultRelay(
        backend=(OLD_BACKEND_IP, quic_port),
        drop_seconds=scenario.drop_seconds,
    )
    relay_transport, _ = await loop.create_datagram_endpoint(
        lambda: relay_protocol,
        local_addr=(CACHED_IP, quic_port),
    )
    dns_protocol = DnsProtocol(scenario.fresh_ip)
    dns_transport, _ = await loop.create_datagram_endpoint(
        lambda: dns_protocol,
        local_addr=(DNS_IP, dns_port),
    )

    fresh_ip: str | None = None
    old_retry: AttemptResult | None = None
    fresh_attempt: AttemptResult | None = None
    dns_error: str | None = None

    try:
        initial = await attempt_quic(
            label="initial_cached_ip",
            ip=CACHED_IP,
            port=quic_port,
            timeout_seconds=initial_timeout,
            qlog_dir=scenario_dir,
        )

        if not initial.success:
            old_retry_task = asyncio.create_task(
                attempt_quic(
                    label="new_connection_same_ip",
                    ip=CACHED_IP,
                    port=quic_port,
                    timeout_seconds=retry_timeout,
                    qlog_dir=scenario_dir,
                )
            )
            try:
                fresh_ip = await resolve_fresh_ip(dns_port)
            except Exception as exc:
                dns_error = f"{type(exc).__name__}: {exc}"

            fresh_task: asyncio.Task[AttemptResult] | None = None
            if fresh_ip is not None and fresh_ip != CACHED_IP:
                fresh_task = asyncio.create_task(
                    attempt_quic(
                        label="new_connection_fresh_ip",
                        ip=fresh_ip,
                        port=quic_port,
                        timeout_seconds=retry_timeout,
                        qlog_dir=scenario_dir,
                    )
                )

            old_retry = await old_retry_task
            if fresh_task is not None:
                fresh_attempt = await fresh_task

        classification = classify(
            initial=initial,
            cached_ip=CACHED_IP,
            fresh_ip=fresh_ip,
            old_retry=old_retry,
            fresh_attempt=fresh_attempt,
        )
        result: dict[str, Any] = {
            "scenario": scenario.name,
            "trial": trial,
            "description": scenario.description,
            "expected_classification": scenario.expected_classification,
            "classification": classification,
            "matches_expected": classification == scenario.expected_classification,
            "cached_ip": CACHED_IP,
            "fresh_dns_ip": fresh_ip,
            "dns_error": dns_error,
            "dns_queries": dns_protocol.queries,
            "initial": asdict(initial),
            "same_ip_new_connection": asdict(old_retry) if old_retry else None,
            "fresh_ip_new_connection": asdict(fresh_attempt)
            if fresh_attempt
            else None,
            "relay": {
                "dropped_client_datagrams": relay_protocol.dropped_client_datagrams,
                "forwarded_client_datagrams": relay_protocol.forwarded_client_datagrams,
                "forwarded_server_datagrams": relay_protocol.forwarded_server_datagrams,
            },
        }
        (scenario_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        return result
    finally:
        dns_transport.close()
        relay_transport.close()
        old_server.close()
        new_server.close()
        await asyncio.sleep(0.05)


async def async_main(args: argparse.Namespace) -> int:
    selected = list(SCENARIOS.values()) if args.scenario == "all" else [SCENARIOS[args.scenario]]
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aeacus-lab-") as temp_dir:
        cert_path, key_path = generate_certificate(Path(temp_dir))
        results = []
        run_index = 0
        for scenario in selected:
            print(f"[{scenario.name}] {scenario.description}", flush=True)
            for trial in range(1, args.repetitions + 1):
                result = await run_scenario(
                    scenario,
                    trial=trial,
                    index=run_index,
                    cert_path=cert_path,
                    key_path=key_path,
                    results_dir=results_dir,
                    initial_timeout=args.initial_timeout,
                    retry_timeout=args.retry_timeout,
                )
                run_index += 1
                results.append(result)
                print(
                    f"  trial={trial} classification={result['classification']} "
                    f"expected={result['expected_classification']} "
                    f"match={result['matches_expected']}",
                    flush=True,
                )

    classification_counts = Counter(item["classification"] for item in results)
    scenario_counts = {
        scenario.name: dict(
            Counter(
                item["classification"]
                for item in results
                if item["scenario"] == scenario.name
            )
        )
        for scenario in selected
    }

    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "initial_timeout_seconds": args.initial_timeout,
        "retry_timeout_seconds": args.retry_timeout,
        "repetitions_per_scenario": args.repetitions,
        "all_matched_expected": all(item["matches_expected"] for item in results),
        "classification_counts": dict(classification_counts),
        "classification_counts_by_scenario": scenario_counts,
        "results": results,
    }
    summary_path = results_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    csv_path = results_dir / "trials.csv"
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "scenario",
                "trial",
                "classification",
                "matches_expected",
                "cached_ip",
                "fresh_dns_ip",
                "initial_success",
                "same_ip_success",
                "fresh_ip_success",
            ],
        )
        writer.writeheader()
        for result in results:
            same_ip = result["same_ip_new_connection"]
            fresh_attempt = result["fresh_ip_new_connection"]
            writer.writerow(
                {
                    "scenario": result["scenario"],
                    "trial": result["trial"],
                    "classification": result["classification"],
                    "matches_expected": result["matches_expected"],
                    "cached_ip": result["cached_ip"],
                    "fresh_dns_ip": result["fresh_dns_ip"],
                    "initial_success": result["initial"]["success"],
                    "same_ip_success": same_ip["success"] if same_ip else "",
                    "fresh_ip_success": fresh_attempt["success"]
                    if fresh_attempt
                    else "",
                }
            )
    print(f"summary={summary_path}", flush=True)
    print(f"trials={csv_path}", flush=True)
    return 0 if summary["all_matched_expected"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run controlled QUIC timeout experiments with concurrent same-IP "
            "reconnection and fresh DNS resolution."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="all",
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--initial-timeout", type=float, default=1.2)
    parser.add_argument("--retry-timeout", type=float, default=1.5)
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    return args


def main() -> int:
    return asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
