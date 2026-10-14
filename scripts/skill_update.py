#!/usr/bin/env python3
"""Check and update a portable skill installation without requiring local .git."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = "https://github.com/NiHaiMaker/plink-u3d-ui-code.git"
VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
IGNORED_LOCAL_NAMES = {".git", "__pycache__"}


class StopUpdate(Exception):
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason


def run_git(directory, timeout, *args, allow_failure=False, network=False):
    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *args], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except FileNotFoundError:
        raise StopUpdate("unavailable", "git_not_found") from None
    except subprocess.TimeoutExpired:
        raise StopUpdate("unavailable", "fetch_timeout" if network else "git_timeout") from None
    except OSError:
        raise StopUpdate("unavailable", "git_unavailable") from None
    if result.returncode and not allow_failure:
        raise StopUpdate("unavailable" if network else "blocked",
                         "fetch_failed" if network else "git_command_failed")
    return result


def git_text(directory, timeout, *args):
    try:
        return run_git(directory, timeout, *args).stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise StopUpdate("blocked", "invalid_git_output") from None


def read_version_file(path, reason):
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise StopUpdate("blocked", reason) from None
    if not VERSION_PATTERN.fullmatch(value):
        raise StopUpdate("blocked", reason)
    return value


def version_numbers(version):
    return tuple(int(part) for part in version.split("."))


def clone_remote(temp_root, timeout):
    repository = temp_root / "repository"
    repository.mkdir()
    run_git(repository, timeout, "init", "--quiet")
    run_git(repository, timeout, "remote", "add", "origin", REPOSITORY)
    run_git(repository, timeout, "fetch", "--quiet", "--force", "--tags",
            "--no-recurse-submodules", "origin",
            "+refs/heads/main:refs/remotes/origin/main", network=True)
    head = git_text(repository, timeout, "rev-parse", "refs/remotes/origin/main^{commit}")
    return repository, head


def version_at(repository, timeout, revision):
    raw = run_git(repository, timeout, "show", f"{revision}:VERSION", allow_failure=True)
    if raw.returncode:
        raise StopUpdate("blocked", "remote_version_missing")
    try:
        value = raw.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise StopUpdate("blocked", "invalid_version_encoding") from None
    if not VERSION_PATTERN.fullmatch(value):
        raise StopUpdate("blocked", "invalid_version")
    return value


def release_notes_at(repository, timeout, revision, version):
    raw = run_git(repository, timeout, "show", f"{revision}:CHANGELOG.md",
                  allow_failure=True)
    if raw.returncode:
        return None
    try:
        content = raw.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    match = re.search(
        rf"^## {re.escape(version)}(?:\s+-[^\n]+)?\s*$\n(.*?)(?=^## |\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else None


def checkout(repository, timeout, revision):
    run_git(repository, timeout, "checkout", "--quiet", "--force", "--detach", revision)


def files_under(root):
    result = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in IGNORED_LOCAL_NAMES:
            continue
        if path.is_file():
            result.add(relative.as_posix())
    return result


def ensure_matches_baseline(skill_dir, repository, timeout, version):
    tag = f"refs/tags/v{version}^{{commit}}"
    if run_git(repository, timeout, "rev-parse", "--verify", tag,
               allow_failure=True).returncode:
        raise StopUpdate("blocked", "current_version_tag_unavailable")
    checkout(repository, timeout, tag)
    baseline_files = files_under(repository)
    local_files = files_under(skill_dir)
    if baseline_files != local_files:
        raise StopUpdate("blocked", "local_files_changed")
    for relative in sorted(baseline_files):
        if (repository / relative).read_bytes() != (skill_dir / relative).read_bytes():
            raise StopUpdate("blocked", "local_files_changed")


def install_revision(skill_dir, repository, timeout, target):
    checkout(repository, timeout, target)
    staging = Path(tempfile.mkdtemp(prefix=f".{skill_dir.name}-new-", dir=skill_dir.parent))
    backup = skill_dir.parent / f".{skill_dir.name}-previous"
    try:
        for source in repository.iterdir():
            if source.name == ".git":
                continue
            destination = staging / source.name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        if backup.exists():
            raise StopUpdate("blocked", "previous_backup_exists")
        skill_dir.rename(backup)
        try:
            staging.rename(skill_dir)
        except OSError:
            backup.rename(skill_dir)
            raise
        shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def inspect_remote(skill_dir, timeout, result, action, target=None):
    if not REPOSITORY:
        raise StopUpdate("unavailable", "update_repository_not_configured")
    current_version = read_version_file(skill_dir / "VERSION", "local_version_invalid")
    result["current_version"] = current_version
    with tempfile.TemporaryDirectory(prefix="plink-u3d-ui-code-update-") as temp:
        repository, remote_head = clone_remote(Path(temp), timeout)
        remote_version = version_at(repository, timeout, remote_head)
        result.update(
            remote_version=remote_version,
            target_commit=remote_head,
            release_notes=release_notes_at(
                repository, timeout, remote_head, remote_version
            ),
        )
        current = version_numbers(current_version)
        latest = version_numbers(remote_version)
        if action == "check":
            if latest < current:
                raise StopUpdate("local_ahead", "remote_version_older")
            if latest == current:
                raise StopUpdate("current", "already_current")
            result.update(status="update_available", reason="newer_version_available")
            return
        if not target or not COMMIT_PATTERN.fullmatch(target):
            raise StopUpdate("blocked", "full_target_commit_required")
        target_type = run_git(repository, timeout, "cat-file", "-t", target,
                              allow_failure=True)
        if target_type.returncode or target_type.stdout.strip() != b"commit":
            raise StopUpdate("blocked", "target_commit_unavailable")
        if run_git(repository, timeout, "merge-base", "--is-ancestor", target,
                   remote_head, allow_failure=True).returncode:
            raise StopUpdate("blocked", "target_not_on_remote_main")
        target_version = version_at(repository, timeout, target)
        result.update(remote_version=target_version, target_commit=target)
        if version_numbers(target_version) <= current:
            raise StopUpdate("blocked", "target_version_not_newer")
        if (skill_dir / ".git").exists():
            raise StopUpdate("blocked", "git_managed_installation")
        target_tag = f"refs/tags/v{target_version}^{{commit}}"
        tag_result = run_git(repository, timeout, "rev-parse", "--verify", target_tag,
                             allow_failure=True)
        if tag_result.returncode or tag_result.stdout.decode("ascii").strip() != target:
            raise StopUpdate("blocked", "target_release_tag_mismatch")
        ensure_matches_baseline(skill_dir, repository, timeout, current_version)
        install_revision(skill_dir, repository, timeout, target)
        installed = read_version_file(skill_dir / "VERSION", "installed_version_invalid")
        if installed != target_version or (skill_dir / ".git").exists():
            raise StopUpdate("blocked", "update_incomplete_inspect_local_state")
        result.update(status="updated", reason="confirmed_target_installed",
                      current_version=installed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "update"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--skill-dir", type=Path,
                               default=Path(__file__).resolve().parents[1])
        subparser.add_argument("--timeout", type=int, default=25)
        if command == "update":
            subparser.add_argument("--target-commit", required=True)
    args = parser.parse_args()
    result = {"status": "blocked", "reason": None, "repository": REPOSITORY,
              "current_version": None, "remote_version": None,
              "target_commit": None, "release_notes": None,
              "installation_mode": "portable"}
    try:
        if not 1 <= args.timeout <= 180:
            raise StopUpdate("blocked", "timeout_must_be_between_1_and_180")
        skill_dir = args.skill_dir.expanduser().resolve()
        if not skill_dir.is_dir():
            raise StopUpdate("blocked", "skill_directory_missing")
        inspect_remote(skill_dir, args.timeout, result, args.command,
                       getattr(args, "target_commit", None))
    except StopUpdate as exc:
        result.update(status=exc.status, reason=exc.reason)
    except (OSError, ValueError):
        result.update(status="blocked", reason="local_state_unavailable")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] in {
        "current", "update_available", "local_ahead", "updated"
    } else 1


if __name__ == "__main__":
    sys.exit(main())
