import unittest
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Test timed out")

class TestProcess(unittest.TestCase):
    def test_process_completes(self):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(2)
        try:
            from process import process_items
            result = process_items(["a", "b", "c"])
            signal.alarm(0)
            self.assertEqual(result, ["A", "B", "C"])
        except TimeoutError:
            self.fail("process_items did not complete in time")

if __name__ == "__main__":
    unittest.main()
