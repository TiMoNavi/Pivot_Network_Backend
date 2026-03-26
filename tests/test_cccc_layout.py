import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path("/home/cw/ybj/Pivot_backend_build_team")


def test_cccc_assets_live_under_project_cccc_layout() -> None:
    assert (ROOT / "CCCC" / "run-cccc.sh").exists()
    assert (ROOT / "CCCC" / "cccc-start.sh").exists()
    assert (ROOT / "CCCC" / "cccc-status.sh").exists()
    assert (ROOT / "CCCC" / "cccc-stop.sh").exists()
    assert (ROOT / "CCCC" / "cccc-control-common.sh").exists()
    assert (ROOT / ".cccc" / "bin" / "cccc").exists()


def test_codex_config_points_to_root_cccc_wrapper() -> None:
    config_text = (ROOT / ".codex" / "config.toml").read_text()
    assert 'command = "/home/cw/ybj/Pivot_backend_build_team/.cccc/bin/cccc"' in config_text


def test_run_cccc_exports_project_cccc_home() -> None:
    result = subprocess.run(
        [str(ROOT / "CCCC" / "run-cccc.sh"), "bash", "-lc", 'printf "%s" "$CCCC_HOME"'],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == str(ROOT / ".cccc" / "runtime" / "cccc-home")


def test_codex_wrapper_uses_repo_root_as_home(tmp_path: Path) -> None:
    stub = tmp_path / "codex-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nprintf '%s' \"$HOME\"\n", encoding="utf-8")
    stub.chmod(0o755)

    env = os.environ.copy()
    env["CODEX_REAL_BIN"] = str(stub)
    result = subprocess.run(
        [str(ROOT / ".cccc" / "bin" / "codex-wrapper.sh")],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout == str(ROOT)


def test_group_template_matches_official_project_actor_layout() -> None:
    template = yaml.safe_load((ROOT / "CCCC" / "templates" / "pivot-backend-build-team.group-template.yaml").read_text())

    assert template["kind"] == "cccc.group_template"
    assert template["v"] == 1
    assert template["settings"]["default_send_to"] == "foreman"
    assert [actor["id"] for actor in template["actors"]] == [
        "lead",
        "swarm_cli",
        "backend_adapter",
        "verification",
        "docs_summary",
    ]
    assert "docs/current-status.md" in template["prompts"]["help"]
    assert "docs/swarm-adapter-progress.md" in template["prompts"]["help"]
