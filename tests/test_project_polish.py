from __future__ import annotations

import pathlib
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProjectPolishTest(unittest.TestCase):
    def load_pyproject(self) -> dict:
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_project_is_installable_package(self) -> None:
        data = self.load_pyproject()
        self.assertEqual(data["tool"]["uv"]["package"], True)
        self.assertEqual(data["build-system"]["build-backend"], "hatchling.build")
        self.assertTrue(any(requirement.startswith("hatchling==") for requirement in data["build-system"]["requires"]))
        wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertIn("rl_kyc_task_env", wheel["packages"])
        self.assertIn("/task", wheel["include"])
        self.assertIn("/private", wheel["include"])

    def test_optional_framework_dependencies_are_strictly_pinned(self) -> None:
        optional = self.load_pyproject()["project"]["optional-dependencies"]
        self.assertEqual(optional["verifiers"], ["verifiers==0.1.11"])
        self.assertEqual(optional["openreward"], ["openreward==0.1.112"])
        self.assertEqual(optional["frameworks"], ["verifiers==0.1.11", "openreward==0.1.112"])

    def test_console_scripts_are_declared(self) -> None:
        scripts = self.load_pyproject()["project"]["scripts"]
        self.assertEqual(scripts["rl-kyc-public-validator"], "task.tools.public_validator:main")
        self.assertEqual(scripts["rl-kyc-hidden-judge"], "judge.run_judge:main")
        self.assertEqual(scripts["rl-kyc-harness"], "harness.cli.external_agent_eval:main")

    def test_ci_workflow_has_required_jobs(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("contract-tests", workflow)
        self.assertIn("bundle-builds", workflow)
        self.assertIn("docker-smoke", workflow)
        self.assertIn("uv run python -m unittest discover -s tests", workflow)
        self.assertIn("build-public-bundle", workflow)
        self.assertIn("run-public-episode", workflow)

    def test_docker_runtime_installs_dependencies_without_project_build(self) -> None:
        dockerfile = (ROOT / "docker" / "eval-runtime.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("RUN uv sync --frozen --no-install-project", dockerfile)


if __name__ == "__main__":
    unittest.main()
