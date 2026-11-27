"""Tests for runtime_lock in managed.py."""

import tempfile
import os
import sys
import time
import multiprocessing

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tspotify.managed import runtime_lock


def worker(results, idx, tmpdir, delay=0):
    os.environ['TSPOTIFY_INSTALL_PREFIX'] = tmpdir
    if delay:
        time.sleep(delay)
    try:
        with runtime_lock():
            results[idx] = 'acquired'
            time.sleep(0.5)  # Hold lock for a bit
            results[idx] = 'held'
        results[idx] = 'released'
    except RuntimeError as e:
        results[idx] = f'failed: {e}'
    except Exception as e:
        results[idx] = f'error: {e}'


def test_basic_lock():
    """Test basic lock acquisition and release."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['TSPOTIFY_INSTALL_PREFIX'] = tmpdir
        try:
            with runtime_lock():
                lock_file = os.path.join(tmpdir, 'run.lock')
                assert os.path.exists(lock_file), "Lock file should exist during lock"
            assert os.path.exists(lock_file), "Lock file should persist after release"
        finally:
            del os.environ['TSPOTIFY_INSTALL_PREFIX']


def test_no_prefix():
    """Test that runtime_lock yields without prefix."""
    # Ensure no prefix is set
    if 'TSPOTIFY_INSTALL_PREFIX' in os.environ:
        del os.environ['TSPOTIFY_INSTALL_PREFIX']
    with runtime_lock():
        pass  # Should not raise


def test_concurrent_lock():
    """Test that only one process can acquire the lock at a time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = multiprocessing.Manager()
        results = manager.dict()
        
        # Start first process - acquires lock
        p1 = multiprocessing.Process(target=worker, args=(results, 1, tmpdir, 0))
        p1.start()
        time.sleep(0.2)  # Give p1 time to acquire
        
        # Start second process - should fail
        p2 = multiprocessing.Process(target=worker, args=(results, 2, tmpdir, 0))
        p2.start()
        
        p1.join(timeout=5)
        p2.join(timeout=5)
        
        print(f'Process 1: {results.get(1)}')
        print(f'Process 2: {results.get(2)}')
        
        assert results.get(1) == 'released', f"Process 1 should acquire and release, got {results.get(1)}"
        assert 'failed' in results.get(2, ''), f"Process 2 should fail to acquire, got {results.get(2)}"
        
        # Verify lock is released after both finish - third process should succeed
        p3 = multiprocessing.Process(target=worker, args=(results, 3, tmpdir, 0))
        p3.start()
        p3.join(timeout=5)
        print(f'Process 3 (after): {results.get(3)}')
        assert results.get(3) == 'released', f"Process 3 should acquire after release, got {results.get(3)}"


def crash_worker(results, idx, tmpdir):
    """Worker that crashes while holding the lock."""
    os.environ['TSPOTIFY_INSTALL_PREFIX'] = tmpdir
    try:
        with runtime_lock():
            results[idx] = 'acquired'
            # Simulate crash by exiting without releasing
            os._exit(1)
    except Exception as e:
        results[idx] = f'error: {e}'


def test_crash_recovery():
    """Test that lock is released when process crashes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = multiprocessing.Manager()
        results = manager.dict()
        
        # Start process that crashes while holding lock
        p1 = multiprocessing.Process(target=crash_worker, args=(results, 1, tmpdir))
        p1.start()
        p1.join(timeout=5)
        
        print(f'Crashed process: {results.get(1)}')
        assert results.get(1) == 'acquired', "Process should have acquired before crash"
        
        # Give OS time to release the lock (Windows releases on handle close)
        time.sleep(0.2)
        
        # New process should be able to acquire
        p2 = multiprocessing.Process(target=worker, args=(results, 2, tmpdir, 0))
        p2.start()
        p2.join(timeout=5)
        
        print(f'Process after crash: {results.get(2)}')
        assert results.get(2) == 'released', f"Should acquire after crash recovery, got {results.get(2)}"


if __name__ == "__main__":
    print("Running test_basic_lock...")
    test_basic_lock()
    print("  PASSED")
    
    print("Running test_no_prefix...")
    test_no_prefix()
    print("  PASSED")
    
    print("Running test_concurrent_lock...")
    test_concurrent_lock()
    print("  PASSED")
    
    print("Running test_crash_recovery...")
    test_crash_recovery()
    print("  PASSED")
    
    print("\nAll tests passed!")