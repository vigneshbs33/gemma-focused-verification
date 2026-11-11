import subprocess,time,pathlib,os,signal,json,sys
P=pathlib.Path(__file__).parent;tag=sys.argv[1];command=sys.argv[2:];(P/'logs').mkdir(exist_ok=True);peak=0;reason=None;start=time.monotonic()
with (P/'logs'/(tag+'.log')).open('w') as log:
 p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 while p.poll() is None:
  try:rss=int(next(x.split()[1] for x in pathlib.Path(f'/proc/{p.pid}/status').read_text().splitlines() if x.startswith('VmRSS:')));peak=max(peak,rss)
  except (FileNotFoundError,StopIteration):rss=0
  if rss>1500*1024:reason='memorycap'
  if time.monotonic()-start>90:reason='timecap'
  if reason:os.killpg(p.pid,signal.SIGKILL);p.wait();break
  time.sleep(.03)
 result={'tag':tag,'command':command,'returncode':p.wait(),'stop_reason':reason,'peak_rss_kib':peak,'elapsed_seconds':time.monotonic()-start};(P/'logs'/(tag+'-status.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print((P/'logs'/(tag+'.log')).read_text()[-3000:])
 if result['returncode']!=0:sys.exit(1)
