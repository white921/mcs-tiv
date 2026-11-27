#!/usr/bin/env bash
set -euo pipefail

current_unit="mcs-eval7-lambda-merge-delay-20261127-v2.service"
holdout_root="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-universal-lambda095-holdout"
diagnostic_source="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-eval7-lambda-diag-700-s37-38-20261127"
diagnostic_output="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-diagnostic-artifacts/eval7-lambda-merge-delay-20261127"
python315="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/bin/python3.15"
sumo_home="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/lib/python3.15/site-packages/sumo"
date_tag="20261127"

printf '{"event":"waiting_for_diagnostic","unit":"%s"}\n' "$current_unit"
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

printf '{"event":"diagnostic_audit_started"}\n'
/usr/bin/python3 "$holdout_root/scripts/audit_eval7_lambda_merge_delay.py" \
    --output-root "$diagnostic_output" \
    --source-root "$diagnostic_source" \
    --source-commit d3f485100ff7c5683a16611cc8e2d878b8e328f6
printf '{"event":"diagnostic_audit_passed"}\n'

cd "$holdout_root"
source_commit="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    printf '{"event":"holdout_source_dirty","commit":"%s"}\n' "$source_commit" >&2
    exit 1
fi
if [[ "$(pgrep -cx sumo || true)" != "0" ]]; then
    printf '{"event":"unexpected_sumo_before_holdout"}\n' >&2
    exit 1
fi

printf '{"event":"holdout_preflight_started","source_commit":"%s"}\n' "$source_commit"
"$python315" scripts/run_universal_lambda095_holdout.py \
    --root "$holdout_root" \
    --sumo-home "$sumo_home" \
    --python "$python315" \
    --date-tag "$date_tag" \
    --slots 15 \
    --preflight-only

printf '{"event":"holdout_started","source_commit":"%s"}\n' "$source_commit"
"$python315" scripts/run_universal_lambda095_holdout.py \
    --root "$holdout_root" \
    --sumo-home "$sumo_home" \
    --python "$python315" \
    --date-tag "$date_tag" \
    --slots 15

printf '{"event":"holdout_finalization_started","source_commit":"%s"}\n' "$source_commit"
nice -n 10 ionice -c2 -n7 /usr/bin/python3 \
    scripts/finalize_universal_lambda095_holdout.py \
    --root "$holdout_root" \
    --date-tag "$date_tag" \
    --source-commit "$source_commit" \
    --workers 2
printf '{"event":"holdout_finalization_finished","source_commit":"%s"}\n' "$source_commit"
