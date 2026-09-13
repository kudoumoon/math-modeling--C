"""Single-pass version runner. P1 is bounded; annual execution belongs to parent."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import sys
import subprocess
from time import perf_counter
import numpy as np
import pandas as pd
import scipy
import openpyxl
from q3_api import ROOT, load_inputs, load_upstream, sha256, simulate
from q3_outputs import write_json, write_variant, paired_comparison, plot_comparison

VERSION=Path(__file__).resolve().parents[1]


def source_hashes():
    return {str(p.relative_to(ROOT)):sha256(p) for p in sorted((VERSION/'program').rglob('*.py'))}


def run(args):
    if not args.run_id or Path(args.run_id).name!=args.run_id or args.run_id in ('.','..'):
        raise ValueError('run-id must be one directory name')
    output=VERSION/'results'/args.run_id
    if output.exists():
        raise FileExistsError(f'never overwrite previous evidence: {output}')
    upstream=load_upstream(run_path=args.upstream)
    inputs=load_inputs()
    hashes=source_hashes()
    if not args.p1:
        receipt=VERSION/'others/P1.json'
        if not receipt.exists():
            raise ValueError('run bounded --p1 and tests before annual execution')
        p1=json.loads(receipt.read_text())
        if p1.get('status')!='PASS' or p1.get('source_hashes')!=hashes:
            raise ValueError('P1 receipt absent/stale for these sources')
    output.mkdir(parents=True)
    figdir=VERSION/'figures'/args.run_id
    figdir.mkdir(parents=True,exist_ok=False)
    (VERSION/'others').mkdir(exist_ok=True)
    start,end=(78,80) if args.p1 else (0,364)
    variants={'baseline':('A',()),'A':('A',(6,12,18)),'B':('B',(6,12,18))}
    if not args.p1:
        variants.update(A_6=('A',(6,)),A_6_12=('A',(6,12)))
    manifest=dict(schema_version=1,status='running',formal_use=False,mode='P1' if args.p1 else 'annual',
        run_id=args.run_id,command=sys.argv,started_at=datetime.now(timezone.utc).isoformat(),
        source_hashes=hashes,upstream=upstream.provenance,
        inputs={str(p.relative_to(ROOT)):sha256(p) for p in [ROOT/'data/附件1.xlsx',ROOT/'data/附件2.xlsx',ROOT/'data/附件3.xlsx',ROOT/'data/附件5/result3.xlsx']},
        configuration=dict(start_day=start,end_day=end,report_start_day=max(31,start),time_mapping='A',battery_interpretation='A',
            observation_delay_slots=0,settlement_primary='A',settlement_sensitivity='B',risk_days=28,gate_days=14,
            margin_quantile=.65,min_risk_days=7,min_gate_days=7,terminal_value=.4684,adjustment_start_day=31,
            midnight_official_forecast_value_evaluated=False,selection='fixed ex ante, no audit-period tuning',variants=variants),
        git_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip(),
        git_status=subprocess.run(['git','status','--porcelain','--',str(VERSION)],cwd=ROOT,check=True,capture_output=True,text=True).stdout,
        python=sys.version,platform=platform.platform(),packages=dict(numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,openpyxl=openpyxl.__version__))
    write_json(output/'manifest.json',manifest)
    started=perf_counter()
    try:
        summaries,dailies={},{}
        for name,(settlement,hours) in variants.items():
            print(f'{name}: days {start}..{end}',flush=True)
            ledger,decisions,plans=simulate(inputs,upstream,start_day=start,end_day=end,settlement=settlement,release_hours=hours)
            # No solver is used for the baseline, and each variant executes once.
            q0=upstream.q0[ledger.day_index.to_numpy(int),ledger.time_index.to_numpy(int)]
            np.testing.assert_array_equal(ledger.q0_kwh,q0)
            summaries[name],dailies[name]=write_variant(output/name,ledger,decisions,plans,max(31,start),end)
        paired_comparison(dailies,output/'paired_comparison.csv')
        plot_comparison(dailies,figdir/'cost_and_emergency.png')
        write_json(output/'summary.json',summaries)
        manifest['status']='complete'
        manifest['outputs']={str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='manifest.json'}
        manifest['figures']={str(p.relative_to(ROOT)):sha256(p) for p in figdir.iterdir() if p.is_file()}
        if args.p1:
            tests=subprocess.run([sys.executable,'-m','pytest',str(VERSION/'program/tests'),'-q','-p','no:cacheprovider'],cwd=ROOT,text=True,capture_output=True)
            (output/'tests.txt').write_text(tests.stdout+tests.stderr)
            if tests.returncode:
                raise RuntimeError('P1 tests failed; see tests.txt')
            write_json(VERSION/'others/P1.json',dict(status='PASS',scope='bounded local P1, independent review pending',
                source_hashes=hashes,run=str(output.relative_to(ROOT)),tests_sha256=sha256(output/'tests.txt'),formal_use=False))
            manifest['outputs']['tests.txt']=sha256(output/'tests.txt')
    except BaseException as exc:
        manifest['status']='failed'
        manifest['error']=repr(exc)
        raise
    finally:
        manifest['elapsed_seconds']=perf_counter()-started
        manifest['finished_at']=datetime.now(timezone.utc).isoformat()
        write_json(output/'manifest.json',manifest)
    print(str(output),flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--p1',action='store_true')
    parser.add_argument('--upstream',type=Path,default=None)
    run(parser.parse_args())
