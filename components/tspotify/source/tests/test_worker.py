import os
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(os.name == "nt", reason="POSIX parent ownership")
def test_engine_terminates_if_frontend_is_killed(tmp_path):
    pidfile = tmp_path / "engine.pid"
    child = "import os,time,pathlib; pathlib.Path(%r).write_text(str(os.getpid())); time.sleep(30)" % str(
        pidfile
    )
    parent_code = (
        "import os,subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-m','tspotify._worker',str(os.getpid()),"
        "sys.executable,'-c',%r],start_new_session=True); time.sleep(30)" % child
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code])
    engine_pid = None
    try:
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pidfile.exists()
        engine_pid = int(pidfile.read_text())
        parent.kill()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(engine_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("engine survived its frontend")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if engine_pid:
            try:
                os.kill(engine_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "nt", reason="Windows job ownership")
def test_windows_job_terminates_owned_engine():
    from tspotify._winjob import Job

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    job = None
    try:
        job = Job(child.pid)
        job.close()
        child.wait(timeout=5)
    finally:
        if job:
            job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)
