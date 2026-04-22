import subprocess
from pathlib import Path


class Validator:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def run_tests(self, test_path: str = None) -> tuple[bool, str]:
        """Run pytest and return (passed, output)."""
        cmd = ["python", "-m", "pytest", "--tb=short", "-q"]
        if test_path:
            cmd.append(test_path)

        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0
        return passed, output

    def run_lint(self) -> tuple[bool, str]:
        """Run basic syntax check on all Python files."""
        errors = []
        for py_file in self.repo_path.rglob("*.py"):
            if ".git" in py_file.parts or "__pycache__" in py_file.parts:
                continue
            result = subprocess.run(
                ["python", "-m", "py_compile", str(py_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                errors.append(f"{py_file}: {result.stderr.strip()}")

        if errors:
            return False, "\n".join(errors)
        return True, "All files passed syntax check."
