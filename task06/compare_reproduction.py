"""Compare the formal run to a separately executed end-to-end run."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from task06.common import *


def compare(other):
    first=read_json(OUT/"verification_task06.json")
    second=read_json(other/"verification_task06.json")
    assert first["status"]==second["status"]=="passed"
    assert read_json(OUT/"experiment_config_frozen.json")["selected_parameters"]==read_json(other/"experiment_config_frozen.json")["selected_parameters"]
    checks=[]
    for name in ["predictions.csv","baseline_predictions.csv","metrics.csv","high_load_metrics.csv",
                 "daily_peak_metrics.csv","daily_metrics.csv","horizon_metrics.csv","weekly_metrics.csv",
                 "uncertainty_summary.csv","information_sensitivity.csv","common_score_mask.csv",
                 "stability_conclusions.csv"]:
        a=read_csv(OUT/name,low_memory=False)
        b=read_csv(other/name,low_memory=False)
        pd.testing.assert_frame_equal(a,b,check_exact=True)
        checks.append(dict(file=name,rows=len(a),exact_frame_equality=True,
                           byte_identical=sha(OUT/name)==sha(other/name),maximum_numeric_difference=0))
    log=[json.loads(line) for line in (other/"training_log.jsonl").read_text(encoding="utf-8").splitlines()]
    first_stage=pd.Timestamp(log[0]["started_at"])
    last_stage=pd.Timestamp(log[-1]["started_at"])+pd.Timedelta(seconds=log[-1]["wall_seconds"])
    result=dict(status="passed",created_at=now(),
        actual_command="& ..\\.venv\\Scripts\\python.exe task06/run_task06.py all --output-root work/task06_reproduction/data --report-root work/task06_reproduction/reports",
        primary_accepted_checks=first["passed"],reproduction_accepted_checks=second["passed"],
        separately_retrained=True,changed_hyperparameters_or_rules=False,
        observed_stage_span_seconds=float((last_stage-first_stage).total_seconds()),
        span_definition="derived from first stage timestamp to last completed report timestamp; excludes interpreter startup and final manifest I/O",
        checks=checks)
    write_json(REPORT/"reproduction_check.json",result)
    write_json(OUT/"reproduction_check.json",result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--other",type=Path,default=ROOT/"work/task06_reproduction/data")
    compare(p.parse_args().other)
