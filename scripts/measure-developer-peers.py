#!/usr/bin/env python3
"""Measured macOS physical footprint and interval CPU, excluding model/agent jobs."""
import argparse
import ctypes
import json
import os
import pathlib
import statistics
import struct
import time

parser=argparse.ArgumentParser()
parser.add_argument('--process',action='append',required=True,help='label:pid')
parser.add_argument('--seconds',type=float,default=30)
parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args()
library=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
library.proc_pid_rusage.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
system=ctypes.CDLL('/usr/lib/libSystem.B.dylib')
class Timebase(ctypes.Structure): _fields_=[('numer',ctypes.c_uint32),('denom',ctypes.c_uint32)]
base=Timebase(); system.mach_timebase_info(ctypes.byref(base))
scale=base.numer/base.denom/1e9
def sample(pid):
    buffer=ctypes.create_string_buffer(1024)
    if library.proc_pid_rusage(pid,4,ctypes.byref(buffer))!=0: raise OSError(ctypes.get_errno(),'proc_pid_rusage failed')
    values=struct.unpack_from('=16s8Q',buffer.raw)
    return {'cpu_seconds':(values[1]+values[2])*scale,'rss_mib':values[7]/2**20,'physical_mib':values[8]/2**20}
processes={item.split(':')[0]:int(item.split(':')[1]) for item in args.process}
before={name:sample(pid) for name,pid in processes.items()}
rows=[]; started=time.monotonic()
while time.monotonic()-started<args.seconds:
    time.sleep(min(2,args.seconds-(time.monotonic()-started)))
    rows.append({name:sample(pid) for name,pid in processes.items()})
elapsed=time.monotonic()-started
report={'seconds':round(elapsed,3),'samples':len(rows),'cpu_scale':'100% equals one fully occupied CPU core',
    'logical_cpu_count':os.cpu_count(),'memory':'macOS physical footprint; RSS also recorded',
    'scope':'native apps and sharing service only; excludes Codex and other agent/model processes',
    'mach_timebase':{'numer':base.numer,'denom':base.denom},'processes':{},'raw_samples':rows}
for name,pid in processes.items():
    report['processes'][name]={'pid':pid,'physical_mib_mean':round(statistics.mean(row[name]['physical_mib'] for row in rows),1),
        'physical_mib_peak':round(max(row[name]['physical_mib'] for row in rows),1),
        'rss_mib_mean':round(statistics.mean(row[name]['rss_mib'] for row in rows),1),
        'cpu_percent_interval':round((rows[-1][name]['cpu_seconds']-before[name]['cpu_seconds'])/elapsed*100,2)}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_samples'},indent=2))
