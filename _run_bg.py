import subprocess
import time
import sys
import os

p = subprocess.Popen(
    [sys.executable, "server.py"],
    stdout=open("server_out.log", "w"),
    stderr=open("server_err.log", "w"),
    cwd=os.path.dirname(os.path.abspath(__file__))
)
time.sleep(2)
print(f"PID: {p.pid}")
