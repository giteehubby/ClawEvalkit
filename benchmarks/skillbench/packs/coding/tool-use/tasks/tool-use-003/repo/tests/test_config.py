import unittest
import json
import pathlib

class TestConfig(unittest.TestCase):
    def test_config_parses(self):
        config_path = pathlib.Path("config.json")
        content = config_path.read_text()
        data = json.loads(content)  # Should not raise
        self.assertIsInstance(data, dict)

    def test_config_has_fields(self):
        config_path = pathlib.Path("config.json")
        data = json.loads(config_path.read_text())
        self.assertIn("name", data)
        self.assertIn("version", data)
        self.assertIn("enabled", data)

if __name__ == "__main__":
    unittest.main()
