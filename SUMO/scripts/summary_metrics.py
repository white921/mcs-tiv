import json
import statistics


def format_distance(value):
    if value is None:
        return None
    return round(value, 1)


def sample_variance(values):
    if len(values) < 2:
        return 0.0
    return statistics.pvariance(values)


def build_run_summary(phase_first_seen, event_times, metric_samples):
    phase_summary = {
        phase: round(timestamp, 2) for phase, timestamp in sorted(phase_first_seen.items())
    }
    event_summary = {
        name: round(timestamp, 2) for name, timestamp in sorted(event_times.items())
    }
    metric_summary = {
        "mv2_speed_variance_deactivate_to_merge": round(
            sample_variance(metric_samples["mv2_speed_deactivate_to_merge"]), 4
        ),
        "rv_speed_variance_observable_to_merge": round(
            sample_variance(metric_samples["rv_speed_observable_to_merge"]), 4
        ),
        "rv_mean_abs_advisory_mismatch": round(
            statistics.fmean(metric_samples["rv_abs_advisory_mismatch"])
            if metric_samples["rv_abs_advisory_mismatch"]
            else 0.0,
            4,
        ),
        "rv_max_abs_advisory_mismatch": round(
            max(metric_samples["rv_abs_advisory_mismatch"])
            if metric_samples["rv_abs_advisory_mismatch"]
            else 0.0,
            4,
        ),
        "samples": {
            "mv2_deactivate_to_merge": len(metric_samples["mv2_speed_deactivate_to_merge"]),
            "rv_observable_to_merge": len(metric_samples["rv_speed_observable_to_merge"]),
            "rv_advisory_monitor": len(metric_samples["rv_abs_advisory_mismatch"]),
        },
    }

    timeline_deltas = {}
    if "leader_switch_to_rv" in event_summary:
        timeline_deltas["leader_switch_error_vs_8s"] = round(
            event_summary["leader_switch_to_rv"] - 8.0, 2
        )
    if "flag2_activated" in event_summary:
        timeline_deltas["flag2_activation_error_vs_8s"] = round(
            event_summary["flag2_activated"] - 8.0, 2
        )
    if "speed_sync" in phase_summary:
        timeline_deltas["speed_sync_start_error_vs_15s"] = round(
            phase_summary["speed_sync"] - 15.0, 2
        )

    return {
        "phases": phase_summary,
        "events": event_summary,
        "metrics": metric_summary,
        "paper_timeline_deltas": timeline_deltas,
    }


def dump_summary(summary, summary_json_path=None):
    print(f"summary phases={summary['phases']}")
    print(f"summary events={summary['events']}")
    print(f"summary metrics={summary['metrics']}")
    print(f"summary paper_deltas={summary['paper_timeline_deltas']}")

    if summary_json_path:
        with open(summary_json_path, "w", encoding="utf-8") as summary_file:
            json.dump(summary, summary_file, indent=2, sort_keys=True)
