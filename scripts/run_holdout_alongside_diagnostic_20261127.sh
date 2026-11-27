#!/usr/bin/env bash
set -euo pipefail

holdout_root="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-universal-lambda095-holdout"
diagnostic_fragment="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-diagnostic-artifacts/eval7-lambda-merge-delay-20261127"
python315="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/bin/python3.15"
sumo_home="/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/lib/python3.15/site-packages/sumo"
date_tag="20261127"

cd "$holdout_root"
source_commit="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    printf '{"event":"holdout_source_dirty","commit":"%s"}\n' "$source_commit" >&2
    exit 1
fi

mapfile -t existing_sumo < <(pgrep -a -x sumo || true)
if (( ${#existing_sumo[@]} > 4 )); then
    printf '{"event":"too_many_existing_sumo","count":%d}\n' \
        "${#existing_sumo[@]}" >&2
    exit 1
fi
for command in "${existing_sumo[@]}"; do
    if [[ "$command" != *"$diagnostic_fragment"* ]]; then
        printf '{"event":"unexpected_existing_sumo","command":%q}\n' \
            "$command" >&2
        exit 1
    fi
done

common=(
    --root "$holdout_root"
    --sumo-home "$sumo_home"
    --python "$python315"
    --date-tag "$date_tag"
    --slots 15
    --allow-existing-sumo 4
    --allowed-external-fragment "$diagnostic_fragment"
)

printf '{"event":"holdout_preflight_started","source_commit":"%s","existing_sumo":%d}\n' \
    "$source_commit" "${#existing_sumo[@]}"
"$python315" scripts/run_universal_lambda095_holdout.py \
    "${common[@]}" --preflight-only

printf '{"event":"holdout_started","source_commit":"%s","existing_sumo":%d}\n' \
    "$source_commit" "${#existing_sumo[@]}"
"$python315" scripts/run_universal_lambda095_holdout.py "${common[@]}"

printf '{"event":"holdout_finalization_started","source_commit":"%s"}\n' \
    "$source_commit"
nice -n 10 ionice -c2 -n7 /usr/bin/python3 \
    scripts/finalize_universal_lambda095_holdout.py \
    --root "$holdout_root" \
    --date-tag "$date_tag" \
    --source-commit "$source_commit" \
    --workers 2
printf '{"event":"holdout_finalization_finished","source_commit":"%s"}\n' \
    "$source_commit"
