import os
import sys
import unittest
import re

class TestForumLogAuthRegex(unittest.TestCase):
    def test_admin_required_present(self):
        """Verify that @admin_required is present for forum log endpoints in app.py"""
        with open('app.py', 'r') as f:
            content = f.read()

        # Pattern to match the routes followed by @admin_required and the function definition
        # Using re.DOTALL is not ideal here as we want to ensure they are on successive lines
        # Allowing for optional whitespace and comments
        pattern = r"@app\.route\('/api/forum/log'\)\s*\n\s*@app\.route\('/api/forum/analysis/log'\)\s*\n\s*@admin_required\s*\n\s*def get_forum_log\(\):"

        match = re.search(pattern, content)
        self.assertIsNotNone(match, "Could not find @admin_required correctly placed before get_forum_log()")

    def test_no_unprotected_log_endpoints(self):
        """Double check no other variant of these routes is unprotected"""
        with open('app.py', 'r') as f:
            lines = [line for line in f]

        for i, line in enumerate(lines):
            if "/api/forum/log" in line or "/api/forum/analysis/log" in line:
                if "@app.route" in line:
                    # Check if the next few lines contain @admin_required before the next def
                    found_admin_required = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        if "@admin_required" in lines[j]:
                            found_admin_required = True
                            break
                        if "def " in lines[j]:
                            break
                    self.assertTrue(found_admin_required, f"Route at line {i+1} seems to be missing @admin_required")

    def test_export_forum_auth(self):
        with open('app.py', 'r') as f:
            lines = [line for line in f]
        found = False
        for i, line in enumerate(lines):
            if "@app.route('/api/forum/export')" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "@admin_required" in lines[j]:
                        found = True
                        break
                    if "def export_forum" in lines[j]:
                        break
        self.assertTrue(found, "Route /api/forum/export seems to be missing @admin_required")

if __name__ == "__main__":
    unittest.main()
