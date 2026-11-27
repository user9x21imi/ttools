"""Test the --demo mode runs and exits cleanly."""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None


def test_demo_mode():
    """Test that --demo starts and can be exited with 'q'."""
    if PtyProcess is None:
        print("SKIP: winpty not available")
        return
    
    env = dict(os.environ, TTOOLS_AUTOUPDATE="0")
    
    # Use PtyProcess to spawn the process (required for curses)
    proc = PtyProcess.spawn(
        [sys.executable, "-m", "tspotify", "--demo"],
        env=env,
        dimensions=(30, 110)
    )
    
    try:
        # Wait a bit for startup and capture output
        out = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < 5:
            try:
                data = proc.read(1024)
            except EOFError:
                break
            if data:
                out.extend(data.encode("utf-8", "replace"))
            if not proc.isalive():
                break
        
        print(f"ALIVE after 5s: {proc.isalive()}, OUTPUT LEN: {len(out)}")
        if out:
            try:
                print(f"OUTPUT (last 500 chars):\n{out[-500:].decode('utf-8', 'replace')}")
            except UnicodeEncodeError:
                print("OUTPUT contains non-console-encodable chars (expected for demo UI)")
        
        if not proc.isalive():
            print(f"Process exited early with status: {proc.exitstatus}")
            assert False, "Process should stay running in demo mode"
        
        print("Process is running, sending 'q' to quit...")
        
        # Send 'q' to quit
        proc.write("q")
        time.sleep(1.5)
        
        print(f"ALIVE after q: {proc.isalive()}, EXITSTATUS: {proc.exitstatus}")
        
        if proc.isalive():
            proc.terminate(force=True)
            time.sleep(0.5)
            assert False, "Process did not exit after sending 'q'"
        
        assert proc.exitstatus == 0, f"Expected exit code 0, got {proc.exitstatus}"
        print("SUCCESS: Demo mode exited cleanly with code 0")
            
    except Exception as e:
        try:
            proc.terminate(force=True)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    test_demo_mode()