"""Process CPU-time deltas, all process threads, measured only inside inference scopes.
One fully occupied CPU core = 100%; normalized machine capacity = cpu_percent / logical CPUs.
No child workers are launched by these inference runners. No background sampling overhead.
"""
import os,resource

def cpu_now():
 r=resource.getrusage(resource.RUSAGE_SELF)
 return r.ru_utime+r.ru_stime

def cpu_result(start,wall):
 cpu=cpu_now()-start
 return {'process_cpu_seconds':cpu,'wall_seconds':wall,'average_process_cpu_percent':100*cpu/wall,
         'average_busy_cores':cpu/wall,'logical_cpu_count':os.cpu_count(),
         'normalized_machine_cpu_percent':100*cpu/wall/os.cpu_count(),
         'scope':'this process all threads, inference scope only; no child inference processes'}
