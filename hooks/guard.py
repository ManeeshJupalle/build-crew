#!/usr/bin/env python3
"""guard: PreToolUse hook that blocks destructive git / gh / rm commands from the Bash and PowerShell tools.

It parses the command into shell words instead of pattern-matching raw text, so
  - quoted text such as commit messages can't trigger it ("docs: explain --no-verify"),
  - git global options can't hide it (git -C . push --force),
  - chained, grouped, nested and substituted commands are checked
    (&&, ;, |, if/then, { }, bash -c, pwsh -c, cmd /c, $(...)).
PowerShell commands get their own tokenizer, since its quoting and escapes differ from Bash.

Exit 2 = block (stderr is shown to Claude). Exit 0 = allow.
This is a seatbelt, not a sandbox: see "Limits" in the README.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

PROTECTED = re.compile(r"^(main|master|develop|release/.+)$")
SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "|&", ";;"}
WRAPPERS = {"sudo", "command", "exec", "time", "nice", "ionice", "nohup", "env", "xargs", "timeout",
            "stdbuf", "caffeinate", "chronic"}
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-n", "-s", "-k", "-c", "-p", "-o", "-e", "-i", "--signal", "--kill-after", "--user"}
HOOK_SKIP_ENV = re.compile(r"^(HUSKY=0|HUSKY_SKIP_HOOKS=|HUSKY_SKIP_INSTALL=|SKIP=|PRE_COMMIT_ALLOW_NO_CONFIG=|GIT_HOOKS_PATH=)")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "mksh", "ash", "fish", "csh", "tcsh"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!"}  # what follows is a command
POWERSHELLS = {"pwsh", "powershell"}
PS_VALUE_PARAMS = ("executionpolicy", "windowstyle", "inputformat", "outputformat", "version", "psconsolefile",
                   "configurationname", "configurationfile", "workingdirectory", "settingsfile", "custompipename")
PS_VALUE_ALIASES = {"ep", "ex", "w", "wd", "o", "of", "i", "if", "v"}
DANGEROUS_RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}", "$HOME/", "$HOME/*",
                        ".", "./", "./*", "..", "../", "*", ".*"}
WINDOWS_ROOTS = re.compile(r"([a-z]:|\$env:(userprofile|home))(/\*?)?", re.I)  # C:\, $env:USERPROFILE\*
PS_REMOVE = {"remove-item", "ri", "rm", "rmdir", "rd", "del", "erase"}
PS_QUOTES = {"'": "'", "‘": "'", "’": "'", "‚": "'", "‛": "'", '"': '"', "“": '"', "”": '"', "„": '"'}
PS_HERESTRING = re.compile(r"@(['\"])[ \t]*\r?\n.*?\r?\n\1@", re.S)
PS_VAR = r"(?:\[[\w.]+\])*\$[\w:.]+"  # $out, $script:x, [string]$x
SEP, GROUP = object(), object()  # PowerShell tokens: ; | & newline, and ( ) { }


def current_branch() -> str:
    try:
        return subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def is_protected_ref(ref: str, branch: str) -> bool:
    ref = ref.lstrip("+")
    dst = ref.split(":", 1)[1] if ":" in ref else ref
    dst = dst.removeprefix("refs/heads/")
    if dst in ("HEAD", "@"):
        dst = branch
    return bool(PROTECTED.match(dst or "x"))


def local_branch_exists(name: str) -> bool:
    try:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                              capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n.*?^[ \t]*\2[ \t]*$", re.S | re.M)


def strip_heredocs(cmd: str) -> str:
    """Heredoc bodies are data (commit messages, PR bodies), not commands: drop them."""
    return HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)


def prog_name(tok: str) -> str:
    """'/usr/bin/git' -> 'git'. Windows and macOS file systems ignore case, and Windows adds .exe: 'GIT.exe' -> 'git'."""
    name = re.split(r"[\\/]", tok)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def short_flags(tok: str) -> str:
    """'-fu' -> 'fu'; '--force' -> ''."""
    return tok[1:] if tok.startswith("-") and not tok.startswith("--") and len(tok) > 1 else ""


def tokenize(cmd: str) -> list[str]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
    lex.whitespace_split = True
    lex.whitespace = " \t\r"  # keep newlines as separators
    lex.commenters = ""         # we drop comments per segment, so a comment can't swallow the next line
    return list(lex)


def segments(tokens: list[str], braces: bool) -> list[list[str]]:
    seps = set(";&|\n{}") if braces else set(";&|\n")
    segs, cur, comment = [], [], False
    for t in tokens:
        if t in SEPARATORS or (t and set(t) <= seps):  # an empty argument ('') is not a separator
            if cur:
                segs.append(cur)
            cur, comment = [], False
        elif comment:
            continue
        elif t.startswith("#") and " " not in t:  # a shell comment runs to the end of the line
            comment = True
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def strip_prefix(seg: list[str]) -> list[str]:
    """Drop env assignments and wrappers: `FOO=1 timeout 60 nice -n 5 git ...` -> `git ...`."""
    i, in_wrapper = 0, False
    while i < len(seg):
        t = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or (t in KEYWORDS and not in_wrapper):
            i += 1
        elif prog_name(t) in WRAPPERS:
            i, in_wrapper = i + 1, True
        elif in_wrapper and t in WRAPPER_VALUE_FLAGS:
            i += 2
        elif in_wrapper and (t.startswith("-") or re.match(r"^[\d.]+[smhd]?$", t)):
            i += 1
        else:
            break
    return seg[i:]


def check_git(args: list[str], state: dict) -> str | None:
    # global options before the subcommand
    i = 0
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        if opt in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            if opt == "-c" and i + 1 < len(args) and args[i + 1].lower().startswith("core.hookspath"):
                return "Overriding core.hooksPath skips git hooks; forbidden."
            i += 2
            continue
        i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]

    if sub == "push":
        positionals = [a for a in rest if not a.startswith("-")]
        for a in rest:
            if a.startswith("--force") or a == "--mirror" or "f" in short_flags(a):
                return "Force push is forbidden."
            if a == "--no-verify":
                return "Skipping git hooks (--no-verify) is forbidden."
            if a in ("--all", "--delete") or "d" in short_flags(a):
                return f"git push {a} is forbidden; push one feature branch."
        refspecs = positionals[1:]
        branch = state.get("branch") or current_branch()
        for r in refspecs:
            if r.startswith("+"):
                return "Force push (+refspec) is forbidden."
            if is_protected_ref(r, branch):
                return "Pushing to a protected branch is forbidden. Open a PR."
        if not refspecs and PROTECTED.match(branch or "x"):
            return f"You are on protected branch '{branch}'. Create a feature branch first."
        return None

    if sub == "commit":
        j = 0
        while j < len(rest):
            a = rest[j]
            if a == "--no-verify":
                return "Skipping git hooks (--no-verify) is forbidden."
            if a in ("-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date",
                     "--template", "--fixup", "--squash", "--reuse-message", "--reedit-message"):
                j += 2
                continue
            for ch in short_flags(a):
                if ch in "mFCct":  # rest of the cluster is a value
                    break
                if ch == "n":
                    return "Skipping git hooks (-n / --no-verify) is forbidden."
            j += 1
        branch = state.get("branch") or current_branch()
        if PROTECTED.match(branch or "x"):
            return f"You are on protected branch '{branch}'. Create a feature branch first."
        return None

    if sub in ("switch", "checkout"):
        if sub == "checkout" and ("." in rest or ":/" in rest):
            return "Discarding all working-tree changes is forbidden."
        for k, a in enumerate(rest):
            if a == "--":
                break  # checkout -- <files>: not a branch change
            if a in ("-c", "-C", "-b", "-B", "--create") and k + 1 < len(rest):
                state["branch"] = rest[k + 1]
                break
            if not a.startswith("-") and (PROTECTED.match(a) or local_branch_exists(a)):
                state["branch"] = a
                break
        return None

    if sub in ("merge", "cherry-pick", "revert", "am"):
        branch = state.get("branch") or current_branch()
        if PROTECTED.match(branch or "x") and not any(a in ("--abort", "--quit") for a in rest):
            return f"git {sub} on protected branch '{branch}' is forbidden. Do it on a feature branch and open a PR."
        return None

    if sub == "reset" and "--hard" in rest:
        return "git reset --hard discards work; forbidden."
    if sub == "clean" and any(a == "--force" or "f" in short_flags(a) for a in rest):
        return "git clean -f deletes files; forbidden."
    if sub == "restore" and ("." in rest or ":/" in rest):
        staged_only = any(a in ("--staged", "-S") for a in rest) and not any(a in ("--worktree", "-W") for a in rest)
        if not staged_only:
            return "Discarding all working-tree changes is forbidden (unstaging with --staged is fine)."
    if sub == "branch" and any(a in ("-d", "-D", "--delete") for a in rest):
        if any(PROTECTED.match(a) for a in rest if not a.startswith("-")):
            return "Deleting a protected branch is forbidden."
    if sub == "add" and any(a in ("-A", "--all", ".", ":/", "-u", "--update") for a in rest):
        return "Stage files by explicit path, not 'git add -A' / 'git add .'."
    return None


def check_gh(args: list[str]) -> str | None:
    if args[:2] == ["pr", "merge"]:
        return "Merging is done by code, not by an agent: run gates/merge_gate.py <PR> --merge."
    if args[:1] == ["repo"] and len(args) > 1 and args[1] in ("delete", "archive", "rename", "edit"):
        return f"gh repo {args[1]} is forbidden."
    if args[:1] == ["api"]:
        joined = " ".join(args)
        if (re.search(r"pulls/\d+/merge\b", joined) or re.search(r"/merges\b", joined)
                or re.search(r"(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)", joined)):
            return "Merging through the API is forbidden: use gates/merge_gate.py."
        method = next((args[k + 1].upper() for k, a in enumerate(args[:-1]) if a in ("-X", "--method")), "GET")
        if method != "GET" and re.search(r"(branches|protection|rulesets|git/refs)", joined):
            return "Changing branches, refs or protection rules through the API is forbidden."
    return None


def check_rm(args: list[str]) -> str | None:
    recursive = any(a in ("--recursive", "-r", "-R") or set("rR") & set(short_flags(a)) for a in args)
    if not recursive:
        return None
    targets = [a for a in args if not a.startswith("-") or a == "-"]
    for t in targets:
        if dangerous_target(t):
            return f"Recursive delete of '{t}' is forbidden."
    return None


def dangerous_target(t: str) -> bool:
    t = t.replace("\\", "/")
    return (t.rstrip("/") in {x.rstrip("/") for x in DANGEROUS_RM_TARGETS} or t in DANGEROUS_RM_TARGETS
            or bool(WINDOWS_ROOTS.fullmatch(t)))


def check_remove_item(args: list[str]) -> str | None:
    """PowerShell's Remove-Item and its aliases. Parameters ignore case and can be shortened (-r, -Rec)."""
    if not any(len(a) > 1 and a[0] == "-" and a[1] != ":" and "recurse".startswith(a[1:].split(":")[0].lower())
               for a in args):
        return None
    for t in args:
        if not t.startswith("-") and dangerous_target(t):
            return f"Recursive delete of '{t}' is forbidden."
    return None


def check_powershell(args: list[str], state: dict, depth: int) -> str | None:
    """PowerShell runs everything after -Command as one command, and Windows PowerShell does the same with a bare
    first argument. Parameters start with - or /, ignore case and can be shortened (-c, -co, /enc).
    -EncodedCommand is base64, so it can't be checked. After -File come the script's own arguments."""
    k = 0
    while k < len(args) and args[k][:1] in ("-", "/"):
        name = args[k].lstrip("-/").lower()
        if name in ("e", "ec") or (len(name) > 1 and "encodedcommand".startswith(name)):
            return "PowerShell -EncodedCommand can't be verified."
        if name in ("c", "cwa") or (len(name) > 1 and "commandwithargs".startswith(name)):
            k += 1
            break
        if name == "f" or (len(name) > 1 and "file".startswith(name)):
            return None
        takes_value = name in PS_VALUE_ALIASES or (len(name) > 1 and any(p.startswith(name) for p in PS_VALUE_PARAMS))
        k += 2 if takes_value else 1
    return check(" ".join(args[k:]), depth + 1, state, "powershell") if k < len(args) else None


def check_segment(seg: list[str], state: dict, depth: int) -> str | None:
    if seg and seg[0] == "export":
        seg = seg[1:]
    for t in seg:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            break
        if HOOK_SKIP_ENV.match(t):
            return f"Skipping git hooks via {t.split('=')[0]} is forbidden."
    seg = strip_prefix(seg)
    if not seg:
        return None
    prog = prog_name(seg[0])
    args = seg[1:]
    if prog in SHELLS:
        for k, a in enumerate(args):
            if (a in ("-c", "--command") or "c" in short_flags(a)) and k + 1 < len(args):
                return check(args[k + 1], depth + 1, state)
    if prog in POWERSHELLS:
        return check_powershell(args, state, depth)
    if prog == "cmd":
        for k, a in enumerate(args):
            if re.fullmatch(r"/+[ckr]", a, re.I):  # Git Bash turns /c into a path, so it's written //c there
                return check(" ".join(args[k + 1:]), depth + 1, state)
    if prog == "eval":
        return check(" ".join(args), depth + 1, state)
    if prog == "git":
        return check_git(args, state)
    if prog == "gh":
        return check_gh(args)
    if prog == "rm":
        return check_rm(args)
    return None


def ps_tokenize(cmd: str) -> list:
    """PowerShell words, with SEP and GROUP for separators and brackets. Unlike the Bash path, quoting is tracked,
    so a quoted ';' is a word. Backtick escapes (also inside "..."), '' is a quote inside '...', a backslash is an
    ordinary character, and a backtick at the end of a line continues it."""
    out, word, quoted, i = [], [], False, 0

    def end_word():
        nonlocal word, quoted
        if word or quoted:
            out.append("".join(word))
        word, quoted = [], False

    while i < len(cmd):
        c = cmd[i]
        if c == "`":
            nxt = cmd[i + 1:i + 2]
            if not nxt:
                raise ValueError("trailing backtick")
            if nxt in "\r\n":
                end_word()
                i += 3 if cmd.startswith("\r\n", i + 1) else 2
            else:
                word.append(nxt)
                i += 2
        elif c in PS_QUOTES:
            q, i, quoted = PS_QUOTES[c], i + 1, True
            while True:
                if i >= len(cmd):
                    raise ValueError("unbalanced quotes")
                d = cmd[i]
                if PS_QUOTES.get(d) == q:
                    if PS_QUOTES.get(cmd[i + 1:i + 2]) == q:  # '' or "" inside the quotes is one quote
                        word.append(d)
                        i += 2
                        continue
                    i += 1
                    break
                if q == '"' and d == "`" and i + 1 < len(cmd):
                    word.append(cmd[i + 1])
                    i += 2
                    continue
                word.append(d)
                i += 1
        elif c in " \t\r,":
            end_word()
            i += 1
        elif c == "#" and not word and not quoted:  # a comment runs to the end of the line
            j = cmd.find("\n", i)
            i = j if j >= 0 else len(cmd)
        elif cmd.startswith("<#", i) and not word and not quoted:
            j = cmd.find("#>", i + 2)
            if j < 0:
                raise ValueError("unclosed comment")
            i = j + 2
        elif c in ";|&\n(){}":
            end_word()
            out.append(SEP if c in ";|&\n" else GROUP)
            i += 1
        else:
            word.append(c)
            i += 1
    end_word()
    return out


def strip_ps_assignment(seg: list[str]) -> list[str]:
    """`$out = git push --force` still runs git push: drop the variable and the = (also $a = $b = ..., +=)."""
    while seg:
        joined = len(seg) > 1 and re.fullmatch(PS_VAR, seg[0])
        head, rest = (seg[0] + seg[1], seg[2:]) if joined else (seg[0], seg[1:])
        m = re.fullmatch(PS_VAR + r"[-+*/%]?=(.*)", head, re.S)
        if not m:
            return seg
        seg = ([m.group(1)] if m.group(1) else []) + rest
    return seg


def check_ps_segment(seg: list[str], state: dict, depth: int) -> str | None:
    m = re.fullmatch(r"\$env:(\w+)=(.*)", "".join(seg), re.I | re.S)
    if m and HOOK_SKIP_ENV.match(f"{m.group(1).upper()}={m.group(2)}"):
        return f"Skipping git hooks via $env:{m.group(1)} is forbidden."
    seg = strip_ps_assignment(seg)
    if not seg:
        return None
    prog = prog_name(seg[0])
    if prog in PS_REMOVE:
        # on Linux and macOS, rm in pwsh is /bin/rm, so check it both ways
        return check_remove_item(seg[1:]) or (check_rm(seg[1:]) if prog == "rm" else None)
    if prog in ("iex", "invoke-expression"):
        args = [a for a in seg[1:] if not (len(a) > 1 and a[0] == "-" and "command".startswith(a[1:].lower()))]
        if not args:
            return "Invoke-Expression with piped input can't be verified."
        return check(" ".join(args), depth + 1, state, "powershell")
    return check_segment(seg, state, depth)


def check_ps(cmd: str, depth: int, state: dict) -> str | None:
    # $(...) runs even inside "..." and @"..."@ (inside '...' it's checked too, to be safe)
    for inner in re.findall(r"\$\(([^()]*)\)", cmd):
        reason = check(inner, depth + 1, state, "powershell")
        if reason:
            return reason
    try:
        tokens = ps_tokenize(PS_HERESTRING.sub("''", cmd))  # here-strings are data, like heredocs
    except ValueError:
        return "Could not parse this command (unbalanced quotes?), so it can't be verified."
    # ( ) and { } group commands (if ($?) { git push }) but also wrap arguments (git commit -m (Get-Date) --no-verify),
    # so check both ways, each from the same starting branch
    start = dict(state)
    for grouping in (True, False):
        state.clear()
        state.update(start)
        seg = []
        for t in tokens + [SEP]:
            if t is SEP or (t is GROUP and grouping):
                reason = check_ps_segment(seg, state, depth) if seg else None
                if reason:
                    return reason
                seg = []
            elif t is not GROUP:
                seg.append(t)
    return None


def check(cmd: str, depth: int = 0, state: dict | None = None, shell: str = "bash") -> str | None:
    if depth > 3:
        return "Command nesting too deep to verify."
    state = {} if state is None else state
    if shell == "powershell":
        return check_ps(cmd, depth, state)
    cmd = strip_heredocs(cmd)
    # commands inside $(...) and backticks run too
    for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", cmd):
        reason = check(inner[0] or inner[1], depth + 1, state)
        if reason:
            return reason
    try:
        tokens = tokenize(cmd)
    except ValueError:
        return "Could not parse this command (unbalanced quotes?), so it can't be verified."
    # a standalone { } may group commands ({ git push -f; }) or be a plain argument (-m '{}'), so check both ways,
    # each from the same starting branch
    start = dict(state)
    for braces in (False, True):
        state.clear()
        state.update(start)
        for seg in segments(tokens, braces):
            reason = check_segment(seg, state, depth)
            if reason:
                return reason
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read())  # bytes: Claude Code sends UTF-8, Windows would decode as cp1252
    except Exception:
        print("BLOCKED by build-crew guard: unreadable hook input.", file=sys.stderr)
        return 2
    shell = {"Bash": "bash", "PowerShell": "powershell"}.get(data.get("tool_name"))
    if not shell:
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    reason = check(cmd, shell=shell)
    if reason:
        print(f"BLOCKED by build-crew guard: {reason}\nCommand: {cmd.strip()[:300]}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
