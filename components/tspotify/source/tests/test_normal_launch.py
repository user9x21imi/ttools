"""Test normal mode launch (without --demo) - should show intro then transition to main UI."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None


def test_normal_launch():
    """Test that normal mode starts, shows intro, and can be exited."""
    if PtyProcess is None:
        print("SKIP: winpty not available")
        return True
    
    env = dict(os.environ, TTOOLS_AUTOUPDATE="0")
    
    # Use PtyProcess to spawn the process
    proc = PtyProcess.spawn(
        [sys.executable, "-m", "tspotify"],
        env=env,
        dimensions=(40, 120)
    )
    
    try:
        # Wait for startup and capture output
        out = bytearray()
        start = time.monotonic()
        while time.monotonic() - start < 10:
            try:
                data = proc.read(4096)
            except EOFError:
                break
            if data:
                out.extend(data.encode("utf-8", "replace"))
            if not proc.isalive():
                break
        
        print(f"ALIVE after 10s: {proc.isalive()}, OUTPUT LEN: {len(out)}")
        
        output_str = out.decode('utf-8', 'replace')
        
        # Verify intro elements are present
        assert 'tspotify' in output_str, "Missing 'tspotify' in output"
        assert 'SYSTEM' in output_str, "Missing 'SYSTEM' in output"
        # Check for braille characters (intro graphic)
        braille_chars = ['⠁','⠂','⠃','⠄','⠅','⠆','⠇','⠈','⠉','⠊','⠋','⠌','⠍','⠎','⠏']
        assert any(c in output_str for c in braille_chars), "Missing braille graphic characters in output"
        
        # Check no _render_grid error
        assert '_render_grid' not in output_str, "Still getting _render_grid error"
        
        if not proc.isalive():
            print(f"Process exited early with status: {proc.exitstatus}")
            return proc.exitstatus == 0
        
        # Send Ctrl+Q to quit (Ctrl+Q is the global exit hotkey)
        print("Process is running, sending Ctrl+Q to quit...")
        proc.write("\x11")  # Ctrl+Q
        time.sleep(3.0)
        
        print(f"ALIVE after Ctrl+Q: {proc.isalive()}, EXITSTATUS: {proc.exitstatus}")
        
        if proc.isalive():
            proc.terminate(force=True)
            time.sleep(0.5)
            return False
        
        print(f"Exit status: {proc.exitstatus}")
        return proc.exitstatus == 0
            
    except Exception as e:
        try:
            proc.terminate(force=True)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    success = test_normal_launch()
    if success:
        print("SUCCESS: Normal launch works!")
    else:
        print("FAILED: Normal launch failed")
        sys.exit(1)