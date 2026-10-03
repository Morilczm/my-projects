#!/usr/bin/env python3
"""Portable score verification; no model loading, network, writes, or inference."""
from pathlib import Path
import json
import math
import sys
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'code/train_dev'))
from core import score

def check(a,b,path):
    if isinstance(b,dict):
        if set(a)!=set(b):raise ValueError(path+': keys differ')
        for k in b:check(a[k],b[k],path+'.'+k)
    elif isinstance(b,(int,float)) and not isinstance(b,bool):
        if not isinstance(a,(int,float)) or not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-14):raise ValueError(path+': number differs')
    elif a!=b:raise ValueError(path+': value differs')

def verify(path,expected):
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows)!=1200 or [r['row_id'] for r in rows]!=list(map(str,range(1200))):raise ValueError(str(path)+': row coverage differs')
    check(score(rows),expected,str(path))

count=0
for stage in ('pretrained','trained'):
    folder=root/'results/dev'/stage
    summary=json.loads((folder/'metrics.json').read_text())
    for mode,systems in summary['models'].items():
        for system,metrics in systems.items():
            verify(folder/f'{mode}_{system}.jsonl',metrics);count+=1
summary=json.loads((root/'results/test/final_result.json').read_text())
for mode,systems in summary['systems'].items():
    for system,metrics in systems.items():
        verify(root/'results/test'/f'{mode}_{system}.jsonl',metrics);count+=1
print(f'PASS: {count} prediction files, 1200 rows each; all saved dev/test metrics match.')
