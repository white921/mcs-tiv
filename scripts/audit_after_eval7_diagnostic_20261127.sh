#!/usr/bin/env bash
set -euo pipefail

current_unit="mcs-eval7-lambda-merge-delay-20261127-v2.service"
holdout_root="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-universal-lambda095-holdout"
diagnostic_source="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-eval7-lambda-diag-700-s37-38-20261127"
diagnostic_output="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-diagnostic-artifacts/eval7-lambda-merge-delay-20261127"

printf '{"event":"waiting_for_diagnostic_audit","unit":"%s"}\n' "$current_unit"
while systemctl --user is-active --quiet "$current_unit"; do
    sleep 30
done

unit_result="$(systemctl --user show "$current_unit" -p Result --value)"
exec_status="$(systemctl --user show "$current_unit" -p ExecMainStatus --value)"
if [[ "$unit_result" != "success" || "$exec_status" != "0" ]]; then
    printf '{"event":"diagnostic_unit_failed","result":"%s","exit_status":"%s"}\n' \
        "$unit_result" "$exec_status" >&2
    exit 1
fi

/usr/bin/python3 "$holdout_root/scripts/audit_eval7_lambda_merge_delay.py" \
    --output-root "$diagnostic_output" \
    --source-root "$diagnostic_source" \
    --source-commit d3f485100ff7c5683a16611cc8e2d878b8e328f6
printf '{"event":"diagnostic_audit_passed"}\n'
