import unittest

from aeacus_lab.experiment import AttemptResult, classify


def attempt(label: str, ip: str, success: bool) -> AttemptResult:
    return AttemptResult(
        label=label,
        ip=ip,
        success=success,
        elapsed_ms=1.0,
        total_elapsed_ms=1.0,
        error=None if success else "timeout",
        initial_packets_sent=1,
        qlog_file="test.qlog.json",
    )


class ClassificationTest(unittest.TestCase):
    def test_initial_success(self) -> None:
        result = classify(
            initial=attempt("initial", "127.0.0.10", True),
            cached_ip="127.0.0.10",
            fresh_ip=None,
            old_retry=None,
            fresh_attempt=None,
        )
        self.assertEqual(result, "initial_success")

    def test_same_ip_recovers(self) -> None:
        result = classify(
            initial=attempt("initial", "127.0.0.10", False),
            cached_ip="127.0.0.10",
            fresh_ip="127.0.0.10",
            old_retry=attempt("retry", "127.0.0.10", True),
            fresh_attempt=None,
        )
        self.assertEqual(result, "transient_same_ip_recovered")

    def test_stale_ip_likely(self) -> None:
        result = classify(
            initial=attempt("initial", "127.0.0.10", False),
            cached_ip="127.0.0.10",
            fresh_ip="127.0.0.3",
            old_retry=attempt("retry", "127.0.0.10", False),
            fresh_attempt=attempt("fresh", "127.0.0.3", True),
        )
        self.assertEqual(result, "stale_ip_likely")

    def test_dns_change_does_not_prove_old_ip_is_stale(self) -> None:
        result = classify(
            initial=attempt("initial", "127.0.0.10", False),
            cached_ip="127.0.0.10",
            fresh_ip="127.0.0.3",
            old_retry=attempt("retry", "127.0.0.10", True),
            fresh_attempt=attempt("fresh", "127.0.0.3", True),
        )
        self.assertEqual(result, "dns_changed_old_still_usable")


if __name__ == "__main__":
    unittest.main()
