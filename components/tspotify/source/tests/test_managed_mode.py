"""Test managed mode integration (TSPOTIFY_INSTALL_PREFIX)."""

import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_managed_prefix_from_env():
    """Test that prefix() reads TSPOTIFY_INSTALL_PREFIX from environment."""
    from tspotify.managed import prefix, owner
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['TSPOTIFY_INSTALL_PREFIX'] = tmpdir
        try:
            p = prefix()
            expected = Path(tmpdir).expanduser().resolve()
            assert p == expected, f"Expected {expected}, got {p}"
            assert owner() == "ttools"
            print("Managed prefix from env: PASSED")
        finally:
            del os.environ['TSPOTIFY_INSTALL_PREFIX']


def test_managed_prefix_from_frozen():
    """Test that prefix() reads from .ttools-managed.json when frozen."""
    from tspotify.managed import prefix, owner
    from pathlib import Path
    import sys
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake executable and managed.json
        exe_dir = os.path.join(tmpdir, "bin")
        os.makedirs(exe_dir)
        exe_path = os.path.join(exe_dir, "tspotify.exe")
        with open(exe_path, "w") as f:
            f.write("dummy")
        
        managed_json = os.path.join(exe_dir, ".ttools-managed.json")
        with open(managed_json, "w") as f:
            json.dump({"prefix": tmpdir}, f)
        
        # Mock sys.frozen and sys.executable
        old_frozen = getattr(sys, 'frozen', False)
        old_executable = sys.executable
        try:
            sys.frozen = True
            sys.executable = exe_path
            
            p = prefix()
            expected = Path(tmpdir).expanduser().resolve()
            assert p == expected, f"Expected {expected}, got {p}"
            assert owner() == "ttools"
            print("Managed prefix from frozen: PASSED")
        finally:
            if old_frozen:
                sys.frozen = old_frozen
            else:
                delattr(sys, 'frozen')
            sys.executable = old_executable


def test_managed_prefix_none_when_not_managed():
    """Test that prefix() returns None when not in managed mode."""
    from tspotify.managed import prefix, owner
    
    # Ensure no env var and not frozen
    if 'TSPOTIFY_INSTALL_PREFIX' in os.environ:
        del os.environ['TSPOTIFY_INSTALL_PREFIX']
    
    import sys
    old_frozen = getattr(sys, 'frozen', False)
    try:
        if hasattr(sys, 'frozen'):
            delattr(sys, 'frozen')
        
        p = prefix()
        assert p is None, f"Expected None, got {p}"
        assert owner() is None
        print("Managed prefix none when not managed: PASSED")
    finally:
        if old_frozen:
            sys.frozen = old_frozen


def test_runtime_lock_with_managed_prefix():
    """Test runtime_lock works with managed prefix."""
    from tspotify.managed import runtime_lock
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['TSPOTIFY_INSTALL_PREFIX'] = tmpdir
        try:
            lock_file = os.path.join(tmpdir, 'run.lock')
            
            # First acquisition
            with runtime_lock():
                assert os.path.exists(lock_file)
            
            # Lock released, file remains
            assert os.path.exists(lock_file)
            
            # Second acquisition
            with runtime_lock():
                assert os.path.exists(lock_file)
            
            print("Runtime lock with managed prefix: PASSED")
        finally:
            del os.environ['TSPOTIFY_INSTALL_PREFIX']


if __name__ == "__main__":
    print("Running test_managed_prefix_from_env...")
    test_managed_prefix_from_env()
    print()
    
    print("Running test_managed_prefix_from_frozen...")
    test_managed_prefix_from_frozen()
    print()
    
    print("Running test_managed_prefix_none_when_not_managed...")
    test_managed_prefix_none_when_not_managed()
    print()
    
    print("Running test_runtime_lock_with_managed_prefix...")
    test_runtime_lock_with_managed_prefix()
    print()
    
    print("All managed mode tests passed!")