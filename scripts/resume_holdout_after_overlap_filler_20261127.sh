#!/usr/bin/env bash
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

initial_unit="mcs-universal-lambda095-final-holdout-20261127.service"
retired_filler_units=(
    "mcs-universal-lambda095-overlap-filler-20261127.service"
    "mcs-universal-lambda095-overlap-filler-v2-20261127.service"
)
filler_unit="mcs-universal-lambda095-overlap-filler-v3-20261128.service"
control_root="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-universal-lambda095-holdout-control"
experiment_root="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-universal-lambda095-holdout"
python315="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/bin/python3.15"
sumo_home="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/lib/python3.15/site-packages/sumo"
date_tag="20261127"
source_commit="f7590fd4d73d78c4f7863512b12985f33d6540bf"

for unit in "$initial_unit" "${retired_filler_units[@]}" "$filler_unit"; do
    printf '{"event":"waiting_for_holdout_unit","unit":"%s"}\n' "$unit"
    while systemctl --user is-active --quiet "$unit"; do
        sleep 30
    done
done

filler_result="$(systemctl --user show "$filler_unit" -p Result --value)"
filler_status="$(systemctl --user show "$filler_unit" -p ExecMainStatus --value)"
if [[ "$filler_result" != "success" || "$filler_status" != "0" ]]; then
    printf '{"event":"overlap_filler_failed","result":"%s","status":"%s"}\n' \
        "$filler_result" "$filler_status" >&2
    exit 1
fi

if [[ "$(git -C "$experiment_root" rev-parse HEAD)" != "$source_commit" ]]; then
    printf '{"event":"experiment_source_commit_changed"}\n' >&2
    exit 1
fi

common=(
    --root "$experiment_root"
    --sumo-home "$sumo_home"
    --python "$python315"
    --date-tag "$date_tag"
    --slots 15
    --resume
)

printf '{"event":"holdout_resume_preflight_started","source_commit":"%s"}\n' \
    "$source_commit"
"$python315" "$control_root/scripts/run_universal_lambda095_holdout.py" \
    "${common[@]}" --preflight-only

printf '{"event":"holdout_resume_started","source_commit":"%s"}\n' \
    "$source_commit"
"$python315" "$control_root/scripts/run_universal_lambda095_holdout.py" \
    "${common[@]}"

printf '{"event":"holdout_finalization_started","source_commit":"%s"}\n' \
    "$source_commit"
nice -n 10 ionice -c2 -n7 /usr/bin/python3 \
    "$control_root/scripts/finalize_universal_lambda095_holdout.py" \
    --root "$experiment_root" \
    --date-tag "$date_tag" \
    --source-commit "$source_commit" \
    --workers 2
printf '{"event":"holdout_finalization_finished","source_commit":"%s"}\n' \
    "$source_commit"
