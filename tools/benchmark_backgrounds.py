"""Bounded CPU microbenchmark; not a whole-machine idle measurement."""
import json,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ttools.backgrounds import Background,PREFERRED
results=[]
for name in PREFERRED:
 b=Background(seed=12,effect=name,now=0);b.render(120,40,0)
 start=time.process_time()
 for i in range(1,21):b.render(120,40,i*.12)
 elapsed=time.process_time()-start
 b.toggle(3);start=time.process_time()
 for i in range(1000):b.render(120,40,4+i)
 paused=time.process_time()-start
 results.append({'primary':name,'secondary':b.secondary,'cpu_ms_per_frame':round(elapsed*1000/20,2),'estimated_one_core_percent_at_10_fps':round(elapsed/20*1000,1),'paused_1000_cached_calls_ms':round(paused*1000,2)})
report={'size':[120,40],'frames':20,'method':'process_time; two layers; no curses/terminal/compositor; one Linux host','results':results}
(ROOT/'docs/background-benchmark.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
