"""Run from any working directory; all paths resolve relative to this repository."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["prepare","preflight","train","predict","evaluate","report","verify","manifest","all"])
    parser.add_argument("--output-root",type=Path,help="Fresh derived output directory inside repository for independent reruns")
    parser.add_argument("--report-root",type=Path,help="Separate report directory inside repository for independent reruns")
    args=parser.parse_args()
    import task06.common as common
    for value in (args.output_root,args.report_root):
        if value is not None:
            assert value.resolve().is_relative_to(common.ROOT),"Output must stay inside this repository"
    if args.output_root is not None:
        common.OUT=args.output_root.resolve()
    if args.report_root is not None:
        common.REPORT=args.report_root.resolve()
    from task06.data import prepare
    from task06.modeling import preflight,train,make_predictions
    from task06.evaluation import evaluate
    actions=dict(prepare=prepare,preflight=preflight,train=train,predict=make_predictions,evaluate=evaluate)
    if args.stage in ("report","verify","manifest","all"):
        from task06.reporting import report,manifest
        from task06.verify_task06 import verify
        actions.update(report=report,verify=verify,manifest=manifest)
    stages=["prepare","preflight","train","predict","evaluate","report","verify","report","manifest"] if args.stage=="all" else [args.stage]
    for stage in stages:
        print(f"=== task06 {stage} ===",flush=True)
        if stage == "verify":
            with common.timed("phase_"+stage):
                actions[stage]()
        else:
            actions[stage]()


if __name__=="__main__":
    main()
