"""Finite R25 supervisor; no automatic restart after safety failure."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from idps_ai.common import atomic_json
from idps_ai.training.checkpoint import RunLock
from r18_data import read


def adapter_command(out, phase, seconds):
    return [sys.executable,"-B","-m","idps_ai.training.resource_adapter","--attempt",str(out/f"resource-{phase}"),"--phase",{"experiment":"TRAIN","verify":"EVALUATE"}[phase],"--seconds",str(seconds),"--cpu-percent","100","--memory-mib","4096","--",sys.executable,"-B",str(Path(__file__).with_name(f"r25_{phase}.py")),str(out)]


def run(out):
    started=time.monotonic()
    with RunLock(out/"supervisor"):
        for phase,seconds in (("experiment",600),("verify",300)):
            directory=out/f"resource-{phase}"
            if (directory/"result.json").exists():
                result=read(directory/"result.json")
                if result.get("reason")=="COMPLETED" and result.get("cleanup_verified"):
                    continue
                atomic_json(out/"status.json",{"state":"BLOCKED","phase":phase,"reason":"PRIOR_NONCOMPLETION_REQUIRES_DIAGNOSIS"})
                return 1
            atomic_json(out/"status.json",{"state":"RUNNING","phase":phase,"run_id":out.name,"supervisor_pid":os.getpid(),"max_worker_cpu":1,"max_worker_memory_mib":4096,"eta_seconds":180})
            command=adapter_command(out,phase,seconds)
            code=subprocess.run(command,check=False).returncode
            result=read(directory/"result.json") if (directory/"result.json").exists() else {}
            if code or result.get("reason")!="COMPLETED" or not result.get("cleanup_verified"):
                atomic_json(out/"status.json",{"state":"BLOCKED","phase":phase,"reason":result.get("reason","ADAPTER_RESULT_MISSING"),"terminal_safety_retry":False})
                return 1
        atomic_json(out/"status.json",{"state":"COMPLETED_RESEARCH_ONLY","run_id":out.name,"fit_originals":400000,"experiment":"PASS","resume":"PASS","resource_cleanup":"PASS","selected_development":read(out/"experiment.json")["selected_development"],"independent_dual_class_evaluation":"BLOCKED","native_acceptance":"PENDING","release_ready":False,"seconds":time.monotonic()-started})
    return 0


if __name__=="__main__":
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path);raise SystemExit(run(p.parse_args().out))
