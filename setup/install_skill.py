"""Make this skill visible to the agent apps installed on this computer.

usage: python setup/install_skill.py            link into every agent skills folder that exists
       python setup/install_skill.py --list     only show what would be linked

Links (directory junction on Windows, symlink elsewhere) <agent skills folder>/vlog-film to this
repository, so `git pull` here updates every agent at once. Known folders:
  Claude Code     ~/.claude/skills
  Codex CLI       ~/.codex/skills
  Hermes Agent    ~/.hermes/skills
  generic         ~/.agents/skills   (used by several other agents that read SKILL.md)
An existing vlog-film folder that is not already a link here is left alone and reported.
"""
import os
import subprocess
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "vlog-film"
TARGETS = [("Claude Code", "~/.claude/skills"), ("Codex", "~/.codex/skills"),
           ("Hermes Agent", "~/.hermes/skills"), ("generic", "~/.agents/skills")]


def same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def link(dst):
    if os.name == "nt":
        # a junction needs no admin rights or developer mode
        r = subprocess.run(["cmd", "/c", "mklink", "/J", dst, SKILL], capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    os.symlink(SKILL, dst)
    return True, ""


def main():
    dry = "--list" in sys.argv
    for app, folder in TARGETS:
        base = os.path.normpath(os.path.expanduser(folder))
        if not os.path.isdir(base):
            print("%-13s %s: not installed, skipped" % (app, folder))
            continue
        dst = os.path.join(base, NAME)
        if os.path.exists(dst):
            state = "already linked" if same(dst, SKILL) else "EXISTS and is not this repo: left alone"
            print("%-13s %s: %s" % (app, dst, state))
            continue
        if dry:
            print("%-13s %s: would link" % (app, dst))
            continue
        ok, msg = link(dst)
        print("%-13s %s: %s" % (app, dst, "linked" if ok else "failed " + msg))


if __name__ == "__main__":
    main()
