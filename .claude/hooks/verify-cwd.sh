#!/usr/bin/env bash
# PreToolUse guard: refuse repo commands that rely on INHERITED working directory.
#
# WHY THIS EXISTS (rule 10). The Bash tool persists cwd between calls, so one earlier
# `cd` into a git worktree silently relocates every later "my repo" command — and git
# answers honestly about a tree you did not mean to be in. On 2026-08-02 that produced
# six tool calls of wrong conclusions and an alarming, entirely false report of an agent
# isolation failure. It then RECURRED one turn after the rule was written, by the author
# of the rule, which is the stated trigger for automating it.
#
# The rule is: anchor repo commands to an absolute path. This enforces it mechanically
# instead of asking anyone to remember.
#
# LIMITATION, READ THIS BEFORE TRUSTING IT: this hook inspects the COMMAND TEXT, not the
# process's actual working directory. A command that merely mentions the repo path passes.
# It is a DISCIPLINE ENFORCER, NOT A SANDBOX. It would have caught all three of the
# 2026-08-02/03 incidents, but it is not proof — and a guard you over-trust is itself an
# instance of the failure class it exists to prevent.
set -euo pipefail
REPO="/Users/renatus/code/lora-rocket-telemetry"
cmd="$(cat)"                      # the proposed command, on stdin

# Only police commands that read or mutate repo state.
grep -Eq '(^|[;&|[:space:]])(git|pyright|pytest)([[:space:]]|$)' <<<"$cmd" || exit 0
# Anchored if it cds to the absolute repo root, or otherwise names it. Once anchored a
# RELATIVE interpreter path like `.venv-test/bin/python` is fine — it resolves against the
# cwd we just pinned. (An earlier draft of this hook rejected that, which was a FALSE
# POSITIVE: the ordering matters, and a guard that cries wolf is one that gets disabled.)
grep -Fq "cd $REPO" <<<"$cmd" && exit 0
grep -Fq "$REPO" <<<"$cmd" && exit 0

# Unanchored AND using a relative interpreter path — the specific form that bit twice.
grep -Eq '(^|[;&|[:space:]])\.venv-test/' <<<"$cmd" && {
  echo "BLOCKED: relative '.venv-test/...' with no absolute anchor." >&2
  echo "Use: cd $REPO && .venv-test/bin/python ..." >&2
  exit 2
}

# INSTANCE 1 of the hollow-guard class: verification chained into mutation.
# `pytest … | tail -1 && git push` pushed on an UNVERIFIED suite, because a pipeline's
# exit status is the LAST command's — tail always succeeds. But `|| exit 1` is not the
# fix either: it still lets a push fire on an exit CODE that nobody read.
# The rule is stronger — a verification and a push/merge must not be the SAME command,
# so the result is read, and approved, before anything mutates.
if grep -Eq '(pytest|pyright)' <<<"$cmd" && grep -Eq 'git[[:space:]]+(push|merge)' <<<"$cmd"; then
  echo "BLOCKED: verification chained into push/merge in one command." >&2
  echo "Run the check, READ the output, then push as a separate deliberate act." >&2
  echo "Reason: a chained push fires on an exit status nobody looked at." >&2
  exit 2
fi

echo "BLOCKED: repo command without an absolute anchor (rule 10)." >&2
echo "Prefix with: cd $REPO && ..." >&2
echo "Reason: cwd persists between calls; git will answer about whatever tree you are in." >&2
exit 2
