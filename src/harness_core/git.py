"""Git operations — branch and worktree management with error handling."""

from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path


class GitError(Exception):
    """A git operation failed."""

    def __init__(self, command: str, stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"git {command} failed: {stderr}")


# What a command-level git failure left behind, as three siblings of GitError.
# None subclasses another, so a handler that refuses one never swallows the
# other two; a plain GitError is none of them and still reads as a bug.


class GitRefusedError(GitError):
    """Nothing was changed: a precondition failed, or a failed write left nothing.

    The message is one line saying what stood in the way; no git command need
    have run (a branch or path that already exists).
    """

    def __init__(self, message: str):
        self.command = ""
        self.stderr = message
        Exception.__init__(self, message)


class GitIncompleteError(GitError):
    """A write failed after changing something; ``done`` says what is left."""

    def __init__(self, message: str, done: dict):
        self.command = ""
        self.stderr = message
        self.done = done
        Exception.__init__(self, message)


class GitUnknownError(GitError):
    """A write failed and whether it took effect could not be read back."""

    def __init__(self, message: str, state: dict):
        self.command = ""
        self.stderr = message
        self.state = state
        Exception.__init__(self, message)


def _run_git(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a git command and return the result.

    ``env`` is laid over the inherited environment, never in place of it: PATH,
    HOME and the ssh settings a push needs stay.

    Raises:
        GitError: If git exits non-zero.
    """
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, errors="replace",
        env=None if env is None else {**os.environ, **env},
    )
    if result.returncode != 0:
        raise GitError(" ".join(args), result.stderr.strip())
    return result


def _one_line(stderr: str) -> str:
    """git's error text as one line: the ``error:``/``fatal:`` lines, no hints."""
    lines = [l.strip() for l in stderr.splitlines()
             if l.strip() and not l.lstrip().startswith("hint:")]
    errors = [l for l in lines if l.startswith(("error:", "fatal:"))]
    return "; ".join(errors or lines) or "(no message)"


def derive_branch_name(issue_number: int, title: str) -> str:
    """Derive branch name from issue number and title.

    Format: feat/issue-<number>-<slug>
    - lowercase, spaces to hyphens, strip special characters
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    slug = slug[:50].rstrip("-")
    return f"feat/issue-{issue_number}-{slug}"


def branch_exists(branch_name: str) -> bool:
    """Check if a ref resolves: a local branch, but also a tag, a sha or ``origin/*``."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _local_branch_exists(branch_name: str) -> bool:
    """``refs/heads/<name>`` exists — exactly, so a tag of that name is not a branch.

    The pre-check and the read-back of :func:`create_branch` and
    :func:`create_worktree` ask this; :func:`branch_exists` would refuse a
    ``checkout -b`` git accepts. A check that cannot run reads as "absent", so
    a repository git cannot read reports REFUSED where INCOMPLETE was due; a
    second run stops on the pre-check before writing anything.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch_name}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _checked_out() -> str | None:
    """The branch HEAD is on in the CWD, or None when detached or unreadable."""
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True,
    )
    return (result.stdout.strip() or None) if result.returncode == 0 else None


def _worktree_path_taken(path: str, root: Path) -> bool:
    """Something is at ``path`` (a dangling link too), or git has it registered.

    A registered worktree whose directory is gone makes ``worktree add`` create
    the branch and then fail, so the registration counts as much as the disk.
    """
    if os.path.lexists(path):
        return True
    listing = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"],
        capture_output=True, text=True,
    )
    want = os.path.realpath(path)
    return any(
        line.startswith("worktree ") and os.path.realpath(line[len("worktree "):]) == want
        for line in listing.stdout.splitlines()
    )


def _resolve_base_ref(base_ref: str) -> str:
    """Resolve a base branch name to a git ref that exists locally.

    Resolution order:
      1. If ``base_ref`` already resolves locally (local branch, tag, or commit),
         use it verbatim.
      2. If its remote-tracking ref ``origin/<base_ref>`` already resolves, use that.
      3. Otherwise fetch the branch from origin and use ``origin/<base_ref>``.

    Raises:
        GitRefusedError: the ref cannot be resolved even after fetching. Raised
            before any branch/worktree is created, so callers never leave
            partial state; the fetch itself changes no work.
    """
    if branch_exists(base_ref):
        return base_ref

    remote_tracking = base_ref if base_ref.startswith("origin/") else f"origin/{base_ref}"
    if branch_exists(remote_tracking):
        return remote_tracking

    fetch_target = base_ref[len("origin/"):] if base_ref.startswith("origin/") else base_ref
    try:
        _run_git("fetch", "origin", fetch_target)
    except GitError as exc:
        raise GitRefusedError(
            f"base ref '{base_ref}' not found locally and could not be fetched: "
            f"{_one_line(exc.stderr)}"
        ) from exc
    if branch_exists(remote_tracking):
        return remote_tracking
    raise GitRefusedError(
        f"base ref '{base_ref}' could not be resolved locally or as {remote_tracking}"
    )


def create_branch(branch_name: str, base_ref: str | None = None) -> str:
    """Create and checkout a new branch. Returns branch name.

    When ``base_ref`` is given the branch is cut from that ref (resolved via
    :func:`_resolve_base_ref`, fetching from origin if it is remote-only). When
    None, the branch is cut from the current HEAD (legacy behavior). ``--no-track``
    keeps a remote base from being adopted as the new branch's upstream, which
    would otherwise pollute ``git branch -vv`` and trip false "gone" cleanups.

    Raises:
        GitRefusedError: the branch already exists, the base cannot be
            resolved, or ``checkout`` failed and left no branch.
        GitIncompleteError: ``checkout`` failed after creating the branch (a
            failing post-checkout hook does this, with HEAD already moved).
    """
    if _local_branch_exists(branch_name):
        raise GitRefusedError(f"branch '{branch_name}' already exists")
    if base_ref is None:
        args: tuple[str, ...] = ("checkout", "-b", branch_name)
    else:
        args = ("checkout", "--no-track", "-b", branch_name, _resolve_base_ref(base_ref))
    try:
        _run_git(*args)
    except GitError as exc:
        # The pre-check saw no branch, so one there now is this call's.
        if not _local_branch_exists(branch_name):
            raise GitRefusedError(
                f"git {' '.join(args)} failed and created nothing: {_one_line(exc.stderr)}"
            ) from exc
        raise GitIncompleteError(
            f"git {' '.join(args)} failed after creating branch '{branch_name}'",
            {"branch": branch_name, "branch_created": True,
             "checked_out": _checked_out(), "error": exc.stderr},
        ) from exc
    return branch_name


def create_worktree(
    worktree_path: str, branch_name: str, base_ref: str | None = None
) -> str:
    """Create a git worktree with a new branch, rooted at the main checkout.

    Returns the worktree's absolute path.

    The worktree is placed and cut from the main checkout, whatever the CWD: a
    relative ``worktree_path`` is taken under :func:`main_worktree_root`, and
    ``worktree add`` runs there, so an undeclared base branches from the main
    checkout's HEAD. Called from a linked worktree, the CWD would otherwise
    nest the new worktree inside it and branch from its feature. A layout with
    no main work tree raises :class:`MainWorktreeUnresolvedError` before
    anything is fetched or created.

    ``base_ref`` behaves as in :func:`create_branch`, and is resolved from the
    CWD: refs and remotes are shared by every worktree of a repository (a
    per-worktree ref such as ``HEAD`` is not a base a plan declares).
    ``--no-track`` is used on both paths, for the reason :func:`create_branch`
    gives, and because ``branch.autoSetupMerge=always`` would otherwise make
    the default base the new branch's upstream too. On a git too old to accept
    it on ``worktree add`` (rejected before any worktree is created), we fall
    back to creating the worktree and then unsetting the upstream.

    Before anything is fetched or created, a branch that already exists and a
    path that is taken are refused. The path check is stricter than git, which
    takes an existing empty directory: with nothing at the path beforehand,
    whatever is there after a failure is this call's.

    Raises:
        GitRefusedError: the branch exists, the path is taken, the base cannot
            be resolved, or ``worktree add`` failed and left nothing.
        GitIncompleteError: ``worktree add`` failed after creating the branch,
            the worktree, or both (an existing path or an unwritable parent
            leaves the branch; a failing post-checkout hook leaves both).
    """
    root = main_worktree_root()
    # Like harness_core.local.abs_under_main (`~` expanded, an absolute path
    # kept), but normalized lexically; local imports this module.
    path = Path(worktree_path).expanduser()
    worktree_path = os.path.normpath(path if path.is_absolute() else root / path)
    if _local_branch_exists(branch_name):
        raise GitRefusedError(f"branch '{branch_name}' already exists")
    if _worktree_path_taken(worktree_path, root):
        raise GitRefusedError(f"worktree path '{worktree_path}' already exists")
    start = [] if base_ref is None else [_resolve_base_ref(base_ref)]

    try:
        try:
            _run_git(
                "-C", str(root),
                "worktree", "add", "--no-track", "-b", branch_name, worktree_path, *start,
            )
        except GitError as exc:
            # Only fall back when this git is too old to accept --no-track on
            # `worktree add` (the option is rejected before any worktree is made).
            # Any other failure (duplicate branch, dirty path) goes to the
            # read-back below — retrying without --no-track would just fail
            # again or mask the cause.
            stderr = (exc.stderr or "").lower()
            if not any(s in stderr for s in ("--no-track", "unknown option", "usage:")):
                raise
            try:
                _run_git("-C", str(root), "worktree", "add", "-b", branch_name, worktree_path, *start)
            except GitError as retry:
                # The first failure says why the fallback was taken; the
                # retry's says why it did not help.
                raise GitError(exc.command, f"{exc.stderr}\n{retry.stderr}") from retry
            try:
                _run_git("-C", worktree_path, "branch", "--unset-upstream", branch_name)
            except GitError:
                pass  # no upstream was set — nothing to unset
    except GitError as exc:
        branch_created = _local_branch_exists(branch_name)
        worktree_created = _worktree_path_taken(worktree_path, root)
        if not (branch_created or worktree_created):
            raise GitRefusedError(
                f"git worktree add failed and created nothing: {_one_line(exc.stderr)}"
            ) from exc
        raise GitIncompleteError(
            f"git worktree add failed after creating "
            + " and ".join(n for n, made in (("the branch", branch_created),
                                            ("the worktree", worktree_created)) if made),
            {"branch": branch_name, "worktree": worktree_path,
             "branch_created": branch_created, "worktree_created": worktree_created,
             "error": exc.stderr},
        ) from exc
    return worktree_path


def delete_branch(branch_name: str) -> None:
    """Delete a local branch (force, for rollback)."""
    _run_git("branch", "-D", branch_name)


def clean_up_stale_branches(
    bases: list[str] | None = None,
    plan_dir: "Path | str | None" = None,
) -> dict:
    """Fetch --prune, then delete stale branches and their worktrees.

    A branch is stale if its upstream ref is gone (`: gone]` in `git branch
    -vv`) or it is fully merged into any branch listed in `bases`.

    Worktrees on stale branches are removed with --force before branch
    deletion. Merged branches use `-d` (safe); gone-only branches use `-D`.

    A stale branch whose worktree holds uncommitted changes (any `git status
    --porcelain` output — modified or untracked) is left completely alone: the
    worktree is not removed and the branch is not deleted. `worktree remove
    --force` would destroy that work silently, so it is reported under
    ``skipped_dirty`` instead of acted on.

    Args:
        bases: Base branches to check merged status against.
               Defaults to ["develop", "main"]. Missing bases are skipped.
        plan_dir: If given, every ``base_branch`` declared in ``plan-*.md``
               frontmatter under this directory is protected from deletion even
               when it looks stale — an integration branch that sub-task plans
               still target must outlive its own merge into develop. Local scan
               only; no network.

    Returns:
        {"removed_worktrees": [...], "deleted_branches": [...],
         "skipped_dirty": [...], "protected_branches": [...], "warnings": [...]}
        ``warnings`` names each removal or deletion that failed and each status
        check that could not run; a non-empty list means the clean-up is
        incomplete, and running it again once the cause is fixed is safe.

    Raises:
        GitRefusedError: ``fetch --prune`` failed, before anything was deleted.
    """
    if bases is None:
        bases = ["develop", "main"]

    try:
        _run_git("fetch", "--prune")
    except GitError as exc:
        raise GitRefusedError(
            f"git fetch --prune failed; no local branch or worktree was touched: "
            f"{_one_line(exc.stderr)}"
        ) from exc

    # Collect branches whose remote ref is gone
    result = subprocess.run(["git", "branch", "-vv"], capture_output=True, text=True)
    gone_branches: set[str] = set()
    for line in result.stdout.splitlines():
        if ": gone]" not in line:
            continue
        stripped = line.strip().lstrip("*+ ")
        branch = stripped.split()[0]
        if branch:
            gone_branches.add(branch)

    # Never treat a base/default branch as stale, even if its upstream shows
    # gone (e.g. a renamed remote default) — deleting develop/main is never safe.
    gone_branches -= set(bases)

    # Collect branches fully merged into any base
    merged_branches: set[str] = set()
    for base in bases:
        try:
            merged_result = _run_git("branch", "--merged", base)
        except GitError:
            continue  # base branch doesn't exist locally — skip
        for line in merged_result.stdout.splitlines():
            stripped = line.strip().lstrip("*+ ")
            if stripped and stripped not in ("develop", "main"):
                merged_branches.add(stripped)
    # A base is merged into itself; like the gone set above, it is never stale.
    merged_branches -= set(bases)

    stale = gone_branches | merged_branches

    # Protect integration branches that live plans still declare as their base.
    protected: set[str] = set()
    if plan_dir is not None:
        from .local import collect_declared_base_branches

        protected = collect_declared_base_branches(Path(plan_dir))
        stale -= protected

    if not stale:
        return {
            "removed_worktrees": [],
            "deleted_branches": [],
            "skipped_dirty": [],
            "protected_branches": sorted(protected),
            "warnings": [],
        }

    # Build branch → worktree path map from porcelain output
    worktree_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    worktree_map: dict[str, str] = {}
    main_path = _first_worktree(worktree_result.stdout)
    current_path: str | None = None
    for line in worktree_result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and current_path:
            worktree_map[line[len("branch refs/heads/"):]] = current_path

    # Remove worktrees before deleting their branches; a worktree with
    # uncommitted work is skipped whole (worktree kept, branch kept).
    removed_worktrees: list[str] = []
    skipped_dirty: list[str] = []
    warnings: list[str] = []
    for branch in stale:
        if branch not in worktree_map:
            continue
        path = worktree_map[branch]
        if path == main_path:
            # The main worktree is never removed; its branch's deletion below
            # fails with git's own reason, and that warning is the report.
            continue
        status = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if status.returncode != 0 or status.stdout.strip():
            # Uncommitted changes (modified or untracked) — or an inability to
            # even determine the state (a stale index.lock, a permission error, a
            # temporarily unavailable mount) — mean `worktree remove --force` could
            # destroy work without a trace. Fail closed: leave the whole branch
            # alone and surface it. A non-empty stdout is dirty; a failed check is
            # treated as dirty too, never as clean.
            skipped_dirty.append(branch)
            if status.returncode != 0:
                warnings.append(
                    f"status check failed for {path}; skipped to be safe: {status.stderr.strip()}"
                )
            continue
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", path],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            removed_worktrees.append(path)
        else:
            warnings.append(f"Could not remove worktree {path}: {result.stderr.strip()}")

    # Delete local branches, except those whose dirty worktree we just skipped.
    deleted_branches: list[str] = []
    for branch in sorted(stale):
        if branch in skipped_dirty:
            continue
        flag = "-d" if branch in merged_branches else "-D"
        result = subprocess.run(
            ["git", "branch", flag, branch], capture_output=True, text=True
        )
        if result.returncode == 0:
            deleted_branches.append(branch)
        else:
            warnings.append(f"Could not delete {branch}: {result.stderr.strip()}")

    return {
        "removed_worktrees": removed_worktrees,
        "deleted_branches": deleted_branches,
        "skipped_dirty": sorted(skipped_dirty),
        "protected_branches": sorted(protected),
        "warnings": warnings,
    }


def remove_worktree(worktree_path: str) -> None:
    """Remove a worktree (force)."""
    _run_git("worktree", "remove", "--force", worktree_path)


# A ref line git prints on stderr when the remote turned the update down
# (non-fast-forward, fetch first, a declining hook). Anything else a failed
# push says — a lost connection above all — is left to the read-back.
_PUSH_REJECTED = re.compile(r"^ ! \[(?:rejected|remote rejected)\] ")
# Push and its read-back parse git's English; the locale must not translate it.
_C_LOCALE = {"LC_ALL": "C"}


def _remote_head(branch_name: str) -> str | None:
    """The sha origin's push URL has for ``refs/heads/<branch>``, or None.

    Read where the push went — ``pushurl`` when one is set, which ``ls-remote
    origin`` would not read. An absent ref is an empty answer, not a failure.

    Raises:
        GitError: the URL or the remote could not be read.
    """
    urls = _run_git("remote", "get-url", "--push", "--all", "origin", env=_C_LOCALE).stdout.splitlines()
    urls = [u for u in urls if u.strip()]  # one URL a line; a path may hold spaces
    if len(urls) != 1:
        # Several push URLs: one can take the update while another fails, and
        # reading one of them back would call a partial push refused.
        raise GitError("remote get-url --push --all origin", f"origin has {len(urls)} push URLs")
    ref = f"refs/heads/{branch_name}"
    # `--` keeps a URL that starts with `-` from being read as an option.
    listing = _run_git("ls-remote", "--", urls[0], ref, env=_C_LOCALE).stdout
    heads = [line.split("\t", 1)[0] for line in listing.splitlines()
             if line.split("\t", 1)[1:] == [ref]]
    return heads[0] if heads else None


def push_branch(branch_name: str) -> str | None:
    """Push branch to origin.

    Returns None when the push succeeded, and the push's error text when it
    reported a failure but origin holds the local commit anyway — a push whose
    connection dropped after the update, or a failing pre-push hook on a branch
    origin already had at this commit.

    Raises:
        GitRefusedError: there is no local branch to push, origin rejected the
            update, or origin is read back without the local commit (absent,
            or at another commit — a single-ref update is all or nothing).
        GitUnknownError: the push failed and origin could not be read back,
            or has more than one push URL to read.
    """
    local = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch_name}^{{commit}}"],
        capture_output=True, text=True,
    )
    if local.returncode != 0:
        raise GitRefusedError(f"no local branch '{branch_name}' to push")
    commit = local.stdout.strip()
    try:
        _run_git("push", "origin", branch_name, env=_C_LOCALE)
        return None
    except GitError as exc:
        error = exc.stderr
    rejected = [line.strip() for line in error.splitlines() if _PUSH_REJECTED.match(line)]
    if rejected:
        raise GitRefusedError(f"origin rejected the push: {rejected[0]}")
    try:
        remote = _remote_head(branch_name)
    except GitError as exc:
        raise GitUnknownError(
            f"push of '{branch_name}' failed and origin could not be read back: "
            f"{_one_line(exc.stderr)}",
            {"branch": branch_name, "remote_head": None, "error": error},
        ) from exc
    if remote == commit:
        return error
    where = "has no such branch" if remote is None else f"is at {remote[:12]}, not {commit[:12]}"
    raise GitRefusedError(
        f"push of '{branch_name}' failed and origin {where}: {_one_line(error)}"
    )


def current_branch() -> str:
    """Return the name of the current branch."""
    result = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    return result.stdout.strip()


class MainWorktreeUnresolvedError(RuntimeError):
    """The main work tree cannot be determined from inside this repository.

    Raised by :func:`main_worktree_root` for a bare repository (with or without
    linked worktrees) and for a ``--separate-git-dir`` repository, where the
    first ``git worktree list`` entry is a git dir and git keeps no pointer
    back to the work tree; and when ``git worktree list`` itself fails inside a
    repository (one git refuses to read, for example). Guessing a directory
    there is how gitignored state ends up under the wrong root, so the caller
    gets a stop instead.
    """


def _first_worktree(listing: str) -> str:
    """The path of the first ``git worktree list --porcelain`` record.

    Read line by line, as the skills' ``sed -n '1s/^worktree //p'`` reads it,
    so the two forms parse the same text the same way.
    """
    first = listing.split("\n", 1)[0]
    return first[len("worktree "):] if first.startswith("worktree ") else ""


@functools.lru_cache(maxsize=1)
def main_worktree_root() -> Path:
    """Return the absolute path of the main worktree root.

    The canonical rule, shared with the skills' shell block in
    ``skills/_shared/references/worktree.md``: take the first entry of
    ``git worktree list --porcelain`` and ask git for *that* entry's work tree
    (``git -C <entry> rev-parse --show-toplevel``).

    - Ordinary clone and its linked worktrees: the first entry is the main
      worktree, and its toplevel is itself.
    - Submodule (and its linked worktrees): the first entry is
      ``.git/modules/<name>``; its ``core.worktree`` makes the toplevel the
      submodule checkout.
    - ``--separate-git-dir`` and bare repositories: the first entry is a git
      dir with no work tree, so this raises :class:`MainWorktreeUnresolvedError`.
      Deriving the root from the parent of ``--git-common-dir`` instead returns
      a directory that exists and is wrong in all three of these layouts.

    Fallback: when git is missing, or git says CWD is not a repository at all,
    returns Path.cwd().resolve(). Any other failed listing raises — a
    repository git refuses to read (``safe.directory``) included — so the
    harness stops exactly where the shell block stops.

    Cached with lru_cache (exceptions are not cached) — tests that change CWD
    across worktrees must call main_worktree_root.cache_clear() between
    assertions.
    """
    try:
        listing = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return Path.cwd().resolve()
    if listing.returncode != 0:
        # Only "not a git repository" means outside a repo. Git refusing a
        # repository it does not trust fails the same way with a different
        # message, and CWD there is the linked worktree, not the main one.
        probe = subprocess.run(
            ["git", "rev-parse", "--git-dir"], capture_output=True, text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        if probe.returncode != 0 and "not a git repository" in probe.stderr:
            return Path.cwd().resolve()
        raise MainWorktreeUnresolvedError(
            "git worktree list failed inside a repository: "
            + (listing.stderr.strip() or f"exit {listing.returncode}")
        )
    first = _first_worktree(listing.stdout)
    if not first:
        raise MainWorktreeUnresolvedError("git worktree list reported no worktree")
    top = subprocess.run(
        ["git", "-C", first, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    answer = top.stdout.rstrip("\n")  # as $(...) trims: newlines only
    if top.returncode != 0 or not answer:
        raise MainWorktreeUnresolvedError(
            f"the first worktree entry {first} has no work tree "
            "(a --separate-git-dir or bare repository)"
        )
    return Path(answer).resolve()


def worktree_root() -> Path:
    """Return the absolute path of the working tree that contains CWD.

    The counterpart of :func:`main_worktree_root` for *tracked* content. In a
    linked worktree this is the linked worktree's own root, not the main
    checkout's — so a file committed on the current branch is read at the
    version this branch carries. Gitignored state (``.task/plan/``,
    ``.claude/state.json``) exists only in the main checkout and stays on
    :func:`main_worktree_root`.

    Fallbacks:
        - bare repository, or CWD inside a ``.git`` directory: git has no
          working tree to report, so returns Path.cwd().resolve().
        - non-git environment: returns Path.cwd().resolve().
    (:func:`main_worktree_root` raises for a bare repository instead, and from
    inside ``.git`` of an ordinary clone answers the main checkout; the two
    answer different questions.)

    Deliberately not cached: the value follows CWD, and a cached copy would
    outlive a ``chdir`` between worktrees.
    """
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return Path(top).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd().resolve()
