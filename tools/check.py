#!/usr/bin/env python3
"""ProbeTab's gate: does the repository still hold together?

    python tools/check.py                  every check; exit 1 if any fails
    python tools/check.py --require-all    a skipped check fails instead
    python tools/check.py --control        plant a fault for each check, in a
                                           copy of the files or a throwaway
                                           repository; each must be caught
    python tools/check.py --history RANGE  also scan the commits in RANGE (a git
                                           revision range; HEAD if none given)
                                           for personal data

Read the VERDICT line and any SKIP lines. The exit code is the weakest signal.
Before a commit, run with --require-all.

The files checked are the working-tree copies of the files git would commit:
the tracked files, plus the untracked files .gitignore does not exclude. The
staged check says when a staged copy differs from the copy that was read.
Programs are started by the full path shutil.which finds, never by a bare name.

The checks, by name, each with what it cannot see:

  layout     README.md's folder table and the top-level folders agree in both
             directions: a folder holding files with no row fails, naming the
             folder, and a row whose folder holds no files fails, naming the
             row. Each folder in the table has a README.md. Folders whose names
             begin with a dot are not in the table.
             Limit: whether a row's description fits its folder is not checked.
  licences   Each row of the table names a licence this repository carries
             (MIT, CC-BY-4.0 or CERN-OHL-P-2.0), and that licence's file exists;
             so does LICENSE, which covers files outside the folders. The table
             is the one statement of which folder has which licence.
             Limit: what a licence file says is not read.
  links      Every relative link in a file whose name ends .md, in any case,
             names a file or folder that exists inside the repository, spelled
             exactly. Three forms are read: inline [text](target), reference
             definitions [label]: target, and quoted HTML href= and src=
             attributes.
             Limit: these are not checked:
               - anchors, and links to other sites;
               - unquoted attributes, srcset and poster;
               - links inside code spans and fenced blocks, which are skipped
                 on purpose;
               - files ending .markdown, and other kinds of file.
  reference  No file is a PDF, judged by its name or by a PDF header in its
             first 1024 bytes, and no file has the bytes of the manual pinned in
             protocol/labpro-facts.toml.
             Limit: a PDF inside another format, such as a zip, and a pasted,
             re-encoded or edited extract of the manual are not caught.
  privacy    No file holds:
               - a home-directory path, in any of these forms:
                 - Windows: a drive letter or a leading backslash, then Users;
                 - MSYS, WSL or Cygwin: a drive's mount, then Users;
                 - macOS: a Users folder at the root;
                 - Unix: a home folder at the root;
                 The Windows and mount forms match in either case. A form
                 matches only where no letter, digit, underscore or dot comes
                 right before it.
               - an email address, except the co-author trailer's;
               - a private IPv4 address;
               - a default Windows hostname, or an mDNS (.local) hostname in
                 either case;
               - a private-key block;
               - a GitHub, Anthropic or AWS key of its published shape;
               - a string listed in .git/info/privacy-extra (one per line;
                 local, never committed).
             With no such file, the check is skipped by name.
             Limit: these are not caught:
               - a string that is split, encoded or spelled out;
               - a hostname in another form;
               - a public IP address;
               - secrets of other shapes.
  eol        No file holds a carriage return. .gitattributes keeps bytes exact,
             so a CRLF written by a Windows tool would otherwise reach a commit.
             Limit: other invisible characters, such as a byte-order mark or a
             Unicode line separator, are not checked.
  staged     No file's staged copy differs both from the last commit (before
             the first commit, from nothing) and from its working-tree copy. If
             one did, `git commit` would take bytes the other checks never read.
             It reads git without writing to it.
             Limit: this describes `git commit` with no paths; `git commit -a`
             and `git commit <path>` take working-tree copies, which are what
             the checks read.
  facts      protocol/labpro-facts.toml parses, and every fact in it (a table
             holding no further tables) has:
               - a value;
               - a source listed under [source];
               - a page;
               - evidence of 16 to 200 characters;
               - a status, "manual" or "bench".
             A bench fact names a file in protocol/traces/. Where the manual is
             present with its pinned SHA-256 and pdftotext is found, each
             fact's evidence must appear on its cited page, with runs of
             whitespace collapsed; otherwise that part is skipped by name.
             Limits:
               - whether a fact's value agrees with its evidence is not
                 checked;
               - what a bench fact's trace holds is not checked, as what makes
                 a file a recorded trace is not defined yet;
               - source tables are not checked beyond what the evidence check
                 uses;
               - matching depends on the pdftotext build, whose version is
                 printed; another build may lay a page out differently.

--history scans each commit in RANGE: its author and committer names and
addresses, its message, and the lines it adds (a merge's, against its first
parent). Header lines listed in .git/info/privacy-allow-headers (local; one per
line) are allowed in the headers only. RANGE is resolved from local refs, so
fetch before naming a remote-tracking ref. A range with no commits is skipped
by name, as it scanned nothing.
Limit: these are not scanned:
  - the names of files a commit adds;
  - tags and notes;
  - an octopus merge's changes beyond what it adds against its first parent.

Threat model: honest mistakes, such as a link or a citation gone stale, a fact
without its source, or a file that should not be published. Text built to pass
the gate is outside it; catching that is the job of a verifier and the owner.
"""

import argparse
import hashlib
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS = "protocol/labpro-facts.toml"
LICENCE_FILES = {
    "MIT": "LICENSE",
    "CC-BY-4.0": "LICENSE-DOCS-DATA",
    "CERN-OHL-P-2.0": "LICENSE-HARDWARE",
}
TABLE = re.compile(r"<!-- folders:start[^>]*-->(.*?)<!-- folders:end -->", re.S)
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
CODE = re.compile(r"`[^`\n]*`")
LINKS = [
    re.compile(r"\]\((<[^>]*>|[^)\s]+)"),
    re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*(<[^>]*>|\S+)", re.M),
    re.compile(r"""\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.I),
]
REQUIRED = ("value", "source", "page", "evidence", "status")
STATUSES = ("manual", "bench")
EVIDENCE_LENGTH = (16, 200)
ALLOWED_EMAILS = {"noreply@anthropic.com"}  # the co-author trailer on commits

# Each pattern is written so that this file does not match it.
PRIVACY = [
    ("a Windows home path", re.compile(r"\b[A-Za-z]:[\\/]+users[\\/]+[^\\/\s]+", re.I)),
    ("a Windows home path", re.compile(r"(?<![\w.])\\users\\[^\\\s]+", re.I)),
    ("an MSYS, WSL or Cygwin home path",
     re.compile(r"(?<![\w.])(?:/mnt|/cygdrive)?/[a-z]/users/[^/\s]+", re.I)),
    ("a macOS home path", re.compile(r"(?<![\w.])/User[s]/[^/\s]+")),
    ("a Unix home path", re.compile(r"(?<![\w.])/home/[a-z_][\w-]*")),
    ("an AppData path", re.compile(r"AppData[\\/]", re.I)),
    ("an email address",
     re.compile(r"[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("a private IPv4 address",
     re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("a default Windows hostname", re.compile(r"\bDESKTOP-[A-Z0-9]{7}\b")),
    ("an mDNS hostname", re.compile(r"\b[A-Za-z0-9][\w-]*\.local\b", re.I)),
    ("a private-key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{22,})")),
    ("an Anthropic key", re.compile(r"\bsk-ant-[\w-]{20,}")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


class Report:
    def __init__(self, name):
        self.name = name
        self.fails = []
        self.skips = []
        self.notes = []

    def fail(self, message):
        self.fails.append(message)

    def skip(self, message):
        self.skips.append(message)

    def note(self, message):
        self.notes.append(message)


class Context:
    """Where the local, uncommitted things are: the manual, and .git/info."""

    def __init__(self, reference_root, git_root):
        self.reference_root = reference_root
        self.git_root = git_root
        self.pages = {}


def tool(name):
    return shutil.which(name)


def collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def git_files(root):
    git = tool("git")
    if not git:
        sys.exit("refused: git is not on PATH")
    out = subprocess.run(
        [git, "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=True).stdout
    names = {n for n in out.decode("utf-8").split("\0") if n}
    return sorted(n for n in names if (root / n).is_file())


def walked_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def folder_rows(root, report):
    readme = root / "README.md"
    if not readme.is_file():
        report.fail("README.md is missing")
        return {}
    match = TABLE.search(readme.read_bytes().decode("utf-8", errors="replace"))
    if not match:
        report.fail("README.md has no folder table between its folders:start and folders:end markers")
        return {}
    rows = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or re.fullmatch(r"[|:\- ]+", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        name = re.fullmatch(r"`([^`/]+)/`", cells[0])
        if name:
            if name.group(1) in rows:
                report.fail(f"README.md's table lists {name.group(1)}/ twice")
            rows[name.group(1)] = cells[-1]
        elif cells[0] != "Folder":
            report.fail(f"README.md's table has a row it cannot read: {line}")
    return rows


def check_layout(root, files, ctx):
    report = Report("layout")
    rows = folder_rows(root, report)
    top = {f.split("/", 1)[0] for f in files if "/" in f and not f.startswith(".")}
    for folder in sorted(top - rows.keys()):
        report.fail(f"folder {folder}/ holds files but has no row in README.md's table")
    for folder in sorted(rows.keys() - top):
        report.fail(f"README.md's table has a row for {folder}/, which holds no files")
    for folder in sorted(rows.keys() & top):
        if f"{folder}/README.md" not in files:
            report.fail(f"folder {folder}/ has no README.md")
    report.note(f"{len(rows)} rows, {len(top)} folders")
    return report


def check_licences(root, files, ctx):
    report = Report("licences")
    rows = folder_rows(root, Report("unused"))  # layout reports a table it cannot read
    for folder, licence in sorted(rows.items()):
        if licence not in LICENCE_FILES:
            report.fail(f"README.md's row {folder}/ names licence {licence!r}, "
                        f"which this repository does not carry")
        elif LICENCE_FILES[licence] not in files:
            report.fail(f"README.md's row {folder}/ names {licence}, but {LICENCE_FILES[licence]} is missing")
    if "LICENSE" not in files:
        report.fail("LICENSE, which covers files outside the folders, is missing")
    report.note(", ".join(sorted(set(rows.values()))) or "no rows")
    return report


def check_links(root, files, ctx):
    report = Report("links")
    present = set(files)
    count = 0
    for name in files:
        if not name.lower().endswith(".md"):
            continue
        text = CODE.sub("", FENCE.sub("", (root / name).read_bytes().decode("utf-8", errors="replace")))
        for pattern in LINKS:
            for raw in pattern.findall(text):
                target = raw[1:-1] if raw.startswith("<") else raw
                if not target or target.startswith("#") or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                    continue
                count += 1
                path = target.split("#", 1)[0]
                joined = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
                if joined == ".." or joined.startswith("../"):
                    report.fail(f"{name}: link {target} leaves the repository")
                elif joined != "." and joined not in present and not any(f.startswith(joined + "/") for f in present):
                    report.fail(f"{name}: link {target} names nothing in the repository")
    report.note(f"{count} relative links")
    return report


def manual_source(root):
    try:
        return tomllib.loads((root / FACTS).read_bytes().decode("utf-8"))["source"]["trm"]
    except (OSError, KeyError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def check_reference(root, files, ctx):
    report = Report("reference")
    pin = manual_source(root).get("sha256")
    if not pin:
        report.fail(f"{FACTS} pins no sha256 for the manual, so its bytes cannot be refused")
    for name in files:
        data = (root / name).read_bytes()
        if name.lower().endswith(".pdf") or b"%PDF-" in data[:1024]:
            report.fail(f"{name}: a PDF; reference material stays out of the repository")
        if pin and hashlib.sha256(data).hexdigest() == pin:
            report.fail(f"{name}: has the bytes of Vernier's manual")
    report.note(f"{len(files)} files read")
    return report


def local_lines(ctx, name):
    path = ctx.git_root / ".git" / "info" / name
    if not path.is_file():
        return None
    lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def personal_data(text, extras):
    """(kind, offset) for each kind of personal data in text. Never the text itself."""
    found = {}
    for kind, pattern in PRIVACY:
        if kind in found:
            continue
        for match in pattern.finditer(text):
            if kind == "an email address" and match.group(0).lower() in ALLOWED_EMAILS:
                continue
            found[kind] = match.start()
            break
    lowered = text.lower()
    for item in extras or []:
        at = lowered.find(item.lower())
        if at >= 0 and "a string listed in .git/info/privacy-extra" not in found:
            found["a string listed in .git/info/privacy-extra"] = at
    return list(found.items())


def check_privacy(root, files, ctx):
    report = Report("privacy")
    extras = local_lines(ctx, "privacy-extra")
    if extras is None:
        report.skip("no .git/info/privacy-extra, so only the general patterns ran")
    for name in files:
        text = (root / name).read_bytes().decode("latin-1")
        for kind, at in personal_data(text, extras):
            report.fail(f"{name}:{text.count(chr(10), 0, at) + 1}: holds {kind}")
    report.note(f"{len(PRIVACY)} patterns and {len(extras or [])} local strings")
    return report


def check_eol(root, files, ctx):
    report = Report("eol")
    for name in files:
        count = (root / name).read_bytes().count(b"\r")
        if count:
            report.fail(f"{name}: holds {count} carriage return(s)")
    report.note(f"{len(files)} files")
    return report


def check_staged(root, files, ctx):
    report = Report("staged")
    if not (root / ".git").exists():
        report.note("not a repository, so nothing is staged")
        return report
    git = tool("git")

    def run(*args, data=None):
        return subprocess.run([git, "-C", str(root), *args], input=data,
                              capture_output=True, check=True).stdout

    has_head = subprocess.run([git, "-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD"],
                              capture_output=True).returncode == 0
    base = "HEAD" if has_head else run("hash-object", "-t", "tree", "--stdin", data=b"").decode("ascii").strip()
    staged = [n for n in run("diff-index", "--cached", "--name-only", "-z", base).decode("utf-8").split("\0") if n]
    index = {}
    for entry in run("ls-files", "--stage", "-z").decode("utf-8").split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            index[path] = meta.split()[1]
    present = []
    for name in staged:
        if name not in index:
            continue  # a staged deletion: nothing of it is committed
        if (root / name).is_file():
            present.append(name)
        else:
            report.fail(f"{name}: staged, but missing from the working tree the checks read")
    if present:
        hashes = run("hash-object", "--stdin-paths", data="\n".join(present).encode("utf-8")).decode("ascii").split()
        for name, digest in zip(present, hashes):
            if digest != index[name]:
                report.fail(f"{name}: its staged copy differs from the working copy the checks read")
    against = "the last commit" if has_head else "nothing (no commit yet)"
    report.note(f"{len(staged)} staged against {against}")
    return report


def fact_tables(node, report, prefix=""):
    """Yield (name, table) for each fact: a table that holds no further tables."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from fact_tables(item, report, f"{prefix}[{index}]")
        return
    nested = {key for key, value in node.items()
              if isinstance(value, dict)
              or (isinstance(value, list) and value and all(isinstance(x, dict) for x in value))}
    if not nested:
        yield prefix, node
        return
    for key, value in node.items():
        name = f"{prefix}.{key}" if prefix else key
        if key not in nested:
            report.fail(f"{name} sits outside any fact table")
        elif not (prefix == "" and key == "source"):
            yield from fact_tables(value, report, name)


def manual_pages(key, source, ctx, report):
    """The source's pages as collapsed text, or None with the reason reported."""
    local = source.get("local")
    if not local:
        report.skip(f"evidence for source {key!r} not checked: it names no local copy")
        return None
    path = ctx.reference_root / local
    if not path.is_file():
        report.skip(f"evidence not checked: {local} is not in the repository folder")
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source.get("sha256"):
        report.fail(f"{local} is present, but its SHA-256 is not the one pinned; the pages cited are the pinned file's")
        return None
    pdftotext = tool("pdftotext")
    if not pdftotext:
        report.skip("evidence not checked: pdftotext is not on PATH")
        return None
    if digest not in ctx.pages:
        version = subprocess.run([pdftotext, "-v"], capture_output=True)
        lines = (version.stderr or version.stdout).decode("utf-8", errors="replace").strip().splitlines()
        with tempfile.TemporaryDirectory(prefix="probetab-check-") as tmp:
            out = Path(tmp) / "pages.txt"
            subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", str(path), str(out)],
                           capture_output=True, check=True)
            text = out.read_bytes().decode("utf-8", errors="replace")
        ctx.pages[digest] = ([collapse(page) for page in text.split("\f")],
                             f"{lines[0] if lines else 'pdftotext, version not reported'} ({pdftotext})")
    pages, reader = ctx.pages[digest]
    report.note(f"pages read with {reader}")
    return pages


def check_facts(root, files, ctx):
    report = Report("facts")
    if FACTS not in files:
        report.fail(f"{FACTS} is missing")
        return report
    try:
        data = tomllib.loads((root / FACTS).read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        report.fail(f"{FACTS} does not parse: {exc}")
        return report
    sources = data.get("source", {})
    facts = list(fact_tables(data, report))
    usable = []
    shortest, longest = EVIDENCE_LENGTH
    for name, fact in facts:
        missing = [key for key in REQUIRED if key not in fact]
        if missing:
            report.fail(f"{name}: lacks {', '.join(missing)}")
            continue
        if fact["source"] not in sources:
            report.fail(f"{name}: its source {fact['source']!r} is not listed under [source]")
            continue
        if fact["status"] not in STATUSES:
            report.fail(f"{name}: its status {fact['status']!r} is neither manual nor bench")
        elif fact["status"] == "bench" and f"protocol/traces/{fact.get('trace', '')}" not in files:
            report.fail(f"{name}: a bench fact must name a trace in protocol/traces/, "
                        f"and {fact.get('trace')!r} is not one")
        length = len(collapse(str(fact["evidence"])))
        if length < shortest:
            report.fail(f"{name}: its evidence is too short to place on a page (under {shortest} characters)")
            continue
        if length > longest:
            report.fail(f"{name}: its evidence is longer than {longest} characters; "
                        f"evidence is a phrase, not a passage")
            continue
        page = fact["page"]
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            report.fail(f"{name}: page {page!r} is not a page number")
            continue
        usable.append((name, fact))
    found = 0
    for key, source in sorted(sources.items()):
        cited = [(name, fact) for name, fact in usable if fact["source"] == key]
        if not cited:
            continue
        pages = manual_pages(key, source, ctx, report)
        if pages is None:
            continue
        for name, fact in cited:
            evidence = collapse(str(fact["evidence"]))
            page = fact["page"]
            if page <= len(pages) and evidence in pages[page - 1]:
                found += 1
                continue
            elsewhere = [str(i + 1) for i, text in enumerate(pages) if evidence in text]
            where = f"it is on page {', '.join(elsewhere)}" if elsewhere else "it is on no page"
            report.fail(f"{name}: its evidence is not on page {page}; {where}")
    report.note(f"{len(facts)} facts, {found} found on their cited pages")
    return report


def check_history(revisions, ctx, repo=ROOT):
    report = Report("history")
    git = tool("git")

    def show(*args):
        return subprocess.run([git, "-C", str(repo), *args],
                              capture_output=True, check=True).stdout.decode("latin-1")

    listing = subprocess.run([git, "-C", str(repo), "rev-list", "--parents", revisions], capture_output=True)
    if listing.returncode != 0:
        report.fail(f"git rev-list {revisions} failed: "
                    f"{listing.stderr.decode('utf-8', errors='replace').strip()}")
        return report
    rows = [line.split() for line in listing.stdout.decode("ascii").splitlines() if line.strip()]
    ends = subprocess.run([git, "-C", str(repo), "rev-parse", "--short", revisions],
                          capture_output=True).stdout.decode("ascii", errors="replace").split()
    report.note(f"{revisions} is {' '.join(ends)} by local refs; {len(rows)} commits")
    if not rows:
        report.skip(f"no commits in {revisions}, so nothing was scanned")
        return report
    extras = local_lines(ctx, "privacy-extra")
    if extras is None:
        report.skip("no .git/info/privacy-extra, so only the general patterns ran")
    allowed = {line.lower() for line in local_lines(ctx, "privacy-allow-headers") or []}
    for commit, *parents in rows:
        headers = show("show", "-s", "--format=%an%n%ae%n%cn%n%ce", commit)
        headers = "\n".join(line for line in headers.splitlines() if line.strip().lower() not in allowed)
        message = show("show", "-s", "--format=%B", commit)
        if len(parents) > 1:
            diff = show("diff", "--text", "--no-color", "-U0", parents[0], commit)
        else:
            diff = show("show", "--text", "--no-color", "--format=", "-U0", commit)
        added = "\n".join(line[1:] for line in diff.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        for where, text in (("headers", headers), ("message", message), ("added lines", added)):
            for kind, _ in personal_data(text, extras):
                report.fail(f"commit {commit[:12]}, {where}: {kind}")
    return report


CHECKS = {
    "layout": check_layout,
    "licences": check_licences,
    "links": check_links,
    "reference": check_reference,
    "privacy": check_privacy,
    "eol": check_eol,
    "staged": check_staged,
    "facts": check_facts,
}


# Controls. Each plants one fault and names the check that must catch it, and
# the words its report must contain, so a control that fails for some other
# reason counts as missed. File controls plant in a fresh copy of the files;
# repository controls build a throwaway repository. Planting never deletes
# anything: a file is "removed" by leaving it out of the list a check is given.

class Unplantable(Exception):
    """The fault cannot be planted here; the control is skipped by name."""


def append(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def edit(root, name, pattern, replacement, within):
    """Replace the first match of pattern inside the section that begins at `within`."""
    path = root / name
    text = path.read_bytes().decode("utf-8")
    start = text.find(within)
    if start < 0:
        raise RuntimeError(f"control cannot be planted: {name} has no {within!r}")
    end = text.find("\n[", start + 1)
    end = len(text) if end < 0 else end
    section, count = re.subn(pattern, replacement, text[start:end], count=1)
    if not count:
        raise RuntimeError(f"control cannot be planted: no {pattern!r} after {within!r} in {name}")
    path.write_bytes((text[:start] + section + text[end:]).encode("utf-8"))


FACT = "[usb.vendor_id]"


def plant_unlisted_folder(root, files, ctx):
    append(root, "zz-planted/README.md", "# planted\n")
    return files + ["zz-planted/README.md"]


def plant_row_without_folder(root, files, ctx):
    return [f for f in files if not f.startswith("docs/")]


def plant_unknown_licence(root, files, ctx):
    edit(root, "README.md", r"\| MIT \|", "| GPL-3.0 |", within="<!-- folders:start")
    return files


def plant_missing_licence_file(root, files, ctx):
    return [f for f in files if f != "LICENSE-HARDWARE"]


def plant_broken_link(root, files, ctx):
    append(root, "README.md", "\n[planted](planted-missing.md)\n")
    return files


def plant_reference_link(root, files, ctx):
    append(root, "README.md", "\n[gone]: planted-gone.md\n")
    return files


def plant_html_link(root, files, ctx):
    append(root, "README.md", '\n<img src="planted-image.png" alt="">\n')
    return files


def plant_upper_case_md(root, files, ctx):
    append(root, "docs/PLANTED.MD", "[x](planted-upper.md)\n")
    return files + ["docs/PLANTED.MD"]


def plant_pdf(root, files, ctx):
    append(root, "docs/planted.pdf", b"%" + b"PDF-1.4\n% planted\n")
    return files + ["docs/planted.pdf"]


def plant_pdf_renamed(root, files, ctx):
    append(root, "docs/guide.dat", b"%" + b"PDF-1.7\n% planted\n")
    return files + ["docs/guide.dat"]


def plant_manual_renamed(root, files, ctx):
    local = manual_source(root).get("local", "")
    source = ctx.reference_root / local
    if not local or not source.is_file():
        raise Unplantable("the manual is not in the repository folder")
    append(root, "docs/notes.bin", source.read_bytes())
    return files + ["docs/notes.bin"]


def plant_home_path(root, files, ctx):
    append(root, "docs/README.md", "\nSaved to " + "C" + ":/" + "Users/planted/notes.txt\n")
    return files


def plant_lower_case_windows_path(root, files, ctx):
    append(root, "docs/README.md", "\nsaved to " + "c" + ":/" + "users/planted/notes.txt\n")
    return files


def plant_macos_path(root, files, ctx):
    append(root, "docs/README.md", "\nSaved to " + "/" + "Users/planted/notes.txt\n")
    return files


def plant_wsl_path(root, files, ctx):
    append(root, "docs/README.md", "\nmounted at " + "/" + "mnt/c/" + "Users/planted/notes.txt\n")
    return files


def plant_cygwin_path(root, files, ctx):
    append(root, "docs/README.md", "\nmounted at " + "/" + "cygdrive/c/" + "Users/planted/notes.txt\n")
    return files


def plant_scp_path(root, files, ctx):
    append(root, "docs/README.md", "\ncopied to box" + ":" + "/" + "Users/planted/notes.txt\n")
    return files


def plant_driveless_windows_path(root, files, ctx):
    append(root, "docs/README.md", "\nsaved under " + "\\" + "Users" + "\\" + "planted" + "\\" + "notes.txt\n")
    return files


def plant_upper_case_mdns(root, files, ctx):
    append(root, "docs/README.md", "\nThe bench host is PLANTED-MAC" + "." + "LOCAL\n")
    return files


def plant_email(root, files, ctx):
    append(root, "docs/README.md", "\nWrite to planted" + "@" + "example.org\n")
    return files


def plant_lan_address(root, files, ctx):
    append(root, "docs/README.md", "\nThe bridge answers at " + "192." + "168.4.1\n")
    return files


def plant_mdns_hostname(root, files, ctx):
    append(root, "docs/README.md", "\nThe bench host is planted-mac" + "." + "local\n")
    return files


def plant_token(root, files, ctx):
    append(root, "docs/README.md", "\ntoken " + "ghp" + "_" + "A" * 36 + "\n")
    return files


def plant_local_string(root, files, ctx):
    strings = local_lines(ctx, "privacy-extra")
    if not strings:
        raise Unplantable("no .git/info/privacy-extra to take a string from")
    append(root, "docs/README.md", "\n" + strings[0] + "\n")
    return files


def plant_crlf(root, files, ctx):
    append(root, "docs/README.md", b"planted line\r\n")
    return files


def plant_no_evidence(root, files, ctx):
    edit(root, FACTS, r"\nevidence =", "\nplanted_evidence =", within=FACT)
    return files


def plant_short_evidence(root, files, ctx):
    edit(root, FACTS, r'evidence = "[^"]*"', 'evidence = "VID=08f7"', within=FACT)
    return files


def plant_long_evidence(root, files, ctx):
    edit(root, FACTS, r'evidence = "[^"]*"', 'evidence = "' + "planted words " * 20 + '"', within=FACT)
    return files


def plant_wrong_page(root, files, ctx):
    edit(root, FACTS, r"page = 22", "page = 23", within=FACT)
    return files


def plant_bench_without_trace(root, files, ctx):
    edit(root, FACTS, r'status = "manual"', 'status = "bench"', within=FACT)
    return files


def plant_unlisted_source(root, files, ctx):
    edit(root, FACTS, r'source = "trm"', 'source = "planted"', within=FACT)
    return files


CONTROLS = [
    ("layout", "a folder with no row", plant_unlisted_folder, "folder zz-planted/"),
    ("layout", "a row with no folder", plant_row_without_folder, "row for docs/"),
    ("licences", "a licence the repository does not carry", plant_unknown_licence, "'GPL-3.0'"),
    ("licences", "a licence file missing", plant_missing_licence_file, "LICENSE-HARDWARE is missing"),
    ("links", "an inline link to nothing", plant_broken_link, "planted-missing.md names nothing"),
    ("links", "a reference definition to nothing", plant_reference_link, "planted-gone.md names nothing"),
    ("links", "an HTML src to nothing", plant_html_link, "planted-image.png names nothing"),
    ("links", "a link in a .MD file", plant_upper_case_md, "docs/PLANTED.MD: link planted-upper.md"),
    ("reference", "a PDF by name", plant_pdf, "docs/planted.pdf: a PDF"),
    ("reference", "a PDF under another name", plant_pdf_renamed, "docs/guide.dat: a PDF"),
    ("reference", "the manual's bytes under another name", plant_manual_renamed, "docs/notes.bin: has the bytes"),
    ("privacy", "a Windows home path", plant_home_path, "a Windows home path"),
    ("privacy", "a lower-case Windows home path", plant_lower_case_windows_path, "a Windows home path"),
    ("privacy", "a macOS home path", plant_macos_path, "a macOS home path"),
    ("privacy", "a macOS home path after host:", plant_scp_path, "a macOS home path"),
    ("privacy", "a WSL home path", plant_wsl_path, "an MSYS, WSL or Cygwin home path"),
    ("privacy", "a Cygwin home path", plant_cygwin_path, "an MSYS, WSL or Cygwin home path"),
    ("privacy", "a Windows home path with no drive", plant_driveless_windows_path, "a Windows home path"),
    ("privacy", "an upper-case mDNS hostname", plant_upper_case_mdns, "an mDNS hostname"),
    ("privacy", "an email address", plant_email, "an email address"),
    ("privacy", "a private IPv4 address", plant_lan_address, "a private IPv4 address"),
    ("privacy", "an mDNS hostname", plant_mdns_hostname, "an mDNS hostname"),
    ("privacy", "a GitHub token", plant_token, "a GitHub token"),
    ("privacy", "a string from the local list", plant_local_string, "privacy-extra"),
    ("eol", "a CRLF line", plant_crlf, "docs/README.md: holds 1 carriage return"),
    ("facts", "a fact without evidence", plant_no_evidence, "usb.vendor_id: lacks evidence"),
    ("facts", "evidence too short to place", plant_short_evidence, "usb.vendor_id: its evidence is too short"),
    ("facts", "evidence too long to be a phrase", plant_long_evidence, "usb.vendor_id: its evidence is longer"),
    ("facts", "evidence cited to the wrong page", plant_wrong_page, "usb.vendor_id: its evidence is not on page 23"),
    ("facts", "a bench fact with no trace", plant_bench_without_trace, "usb.vendor_id: a bench fact"),
    ("facts", "a source not listed", plant_unlisted_source, "usb.vendor_id: its source 'planted'"),
]


def control_repository(base, name):
    """A throwaway repository under base, and a function that runs git in it."""
    git = tool("git")
    repo = base / name
    repo.mkdir()
    identity = ["-c", "user.name=control", "-c", "user.email=control" + "@" + "example.invalid"]

    def run(*args):
        subprocess.run([git, "-C", str(repo), *identity, *args], capture_output=True, check=True)

    run("init", "-q", "-b", "main")
    return repo, run


def build_staged(base, ctx):
    repo, run = control_repository(base, "staged")
    append(repo, "notes.txt", "clean\n")
    run("add", "notes.txt")
    (repo / "notes.txt").write_bytes(b"changed after staging\n")
    return check_staged(repo, ["notes.txt"], ctx)


def build_linear_history(base, ctx):
    repo, run = control_repository(base, "history")
    append(repo, "notes.txt", "clean\n")
    run("add", "notes.txt")
    run("commit", "-q", "-m", "clean")
    append(repo, "notes.txt", "Saved to " + "C" + ":/" + "Users/planted/notes.txt\n")
    run("commit", "-q", "-a", "-m", "planted: write to planted" + "@" + "example.org")
    return check_history("HEAD", ctx, repo=repo)


def build_merge_history(base, ctx):
    repo, run = control_repository(base, "merge")
    append(repo, "a.txt", "one\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "one")
    run("checkout", "-q", "-b", "side")
    append(repo, "b.txt", "two\n")
    run("add", "b.txt")
    run("commit", "-q", "-m", "two")
    run("checkout", "-q", "main")
    append(repo, "c.txt", "three\n")
    run("add", "c.txt")
    run("commit", "-q", "-m", "three")
    run("merge", "-q", "--no-ff", "--no-commit", "side")
    append(repo, "a.txt", "kept in " + "/" + "home/planted/notes.txt\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "merge side")
    return check_history("HEAD", ctx, repo=repo)


def build_empty_range(base, ctx):
    repo, run = control_repository(base, "empty-range")
    append(repo, "notes.txt", "clean\n")
    run("add", "notes.txt")
    run("commit", "-q", "-m", "clean")
    return check_history("HEAD..HEAD", ctx, repo=repo)


REPOSITORY_CONTROLS = [
    ("staged", "a staged copy changed afterwards", build_staged, "fail",
     "notes.txt: its staged copy differs"),
    ("history", "a home path added by a commit", build_linear_history, "fail",
     "added lines: a Windows home path"),
    ("history", "an email address in a message", build_linear_history, "fail",
     "message: an email address"),
    ("history", "an email address in the headers", build_linear_history, "fail",
     "headers: an email address"),
    ("history", "a home path added by a merge", build_merge_history, "fail",
     "added lines: a Unix home path"),
    ("history", "a range with no commits", build_empty_range, "skip",
     "no commits in HEAD..HEAD"),
]


def copy_files(files, destination):
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return destination


def run_controls(files, ctx, require_all):
    print()
    print("Controls: each plants one fault; the check named must catch it, for the reason named.")
    missed = skipped = named_skips = 0
    with tempfile.TemporaryDirectory(prefix="probetab-control-") as tmp:
        base = Path(tmp)
        baseline_root = copy_files(files, base / "baseline")
        baseline = [check(baseline_root, walked_files(baseline_root), ctx) for check in CHECKS.values()]
        broken = [report.name for report in baseline if report.fails]
        if broken:
            print(f"  BASELINE FAILED: an untouched copy fails {', '.join(broken)}, so the controls mean nothing")
            print("CONTROLS: FAIL (baseline)")
            return True
        print("  baseline: an untouched copy passes every check")
        for number, (name, title, plant, expect) in enumerate(CONTROLS, start=1):
            root = copy_files(files, base / f"control-{number:02d}")
            try:
                planted = plant(root, walked_files(root), ctx)
            except Unplantable as why:
                skipped += 1
                print(f"  SKIP   {name:<9} {title}: not planted, {why}")
                continue
            report = CHECKS[name](root, planted, ctx)
            hits = [message for message in report.fails if expect in message]
            if hits:
                print(f"  caught {name:<9} {title}: {hits[0]}")
            elif not report.fails and report.skips:
                skipped += 1
                print(f"  SKIP   {name:<9} {title}: not exercised, {report.skips[0]}")
            else:
                missed += 1
                got = report.fails[0] if report.fails else "the check passed"
                print(f"  MISSED {name:<9} {title}: expected a failure containing {expect!r}; got: {got}")
        built = {}
        for name, title, build, outcome, expect in REPOSITORY_CONTROLS:
            if build not in built:
                built[build] = build(base, ctx)
            report = built[build]
            pool = report.fails if outcome == "fail" else report.skips
            hits = [message for message in pool if expect in message]
            verb = "caught" if outcome == "fail" else "skipped"
            if hits:
                named_skips += outcome == "skip"
                print(f"  {verb:<6} {name:<9} {title}: {hits[0]}")
            else:
                missed += 1
                print(f"  MISSED {name:<9} {title}: expected a {outcome} containing {expect!r}; "
                      f"got fails {report.fails[:1]} and skips {report.skips[:1]}")
    total = len(CONTROLS) + len(REPOSITORY_CONTROLS)
    caught = total - missed - skipped - named_skips
    if missed or (skipped and require_all):
        print(f"CONTROLS: FAIL ({caught} caught, {named_skips} skipped as named, {missed} missed, "
              f"{skipped} not exercised, of {total})")
        return True
    suffix = f"; {skipped} not exercised" if skipped else ""
    print(f"CONTROLS: PASS ({total - skipped} of {total} behaved as named: {caught} caught, "
          f"{named_skips} skipped as named{suffix})")
    return False


def show(report, require_all):
    if report.fails:
        status = "FAIL"
    elif report.skips:
        status = "FAIL" if require_all else "SKIP"
    else:
        status = "PASS"
    print(f"{status:<4} {report.name:<9} {'; '.join(report.notes)}")
    for message in report.fails:
        print(f"       {message}")
    for message in report.skips:
        print(f"       skipped: {message}")
    return status


def main():
    parser = argparse.ArgumentParser(description="ProbeTab's gate. The docstring says what each check holds.")
    parser.add_argument("--require-all", action="store_true", help="a skipped check fails")
    parser.add_argument("--control", action="store_true", help="plant a fault for each check and confirm it is caught")
    parser.add_argument("--history", nargs="?", const="HEAD", metavar="RANGE",
                        help="also scan the commits in RANGE for personal data")
    args = parser.parse_args()

    ctx = Context(reference_root=ROOT, git_root=ROOT)
    files = git_files(ROOT)
    reports = [check(ROOT, files, ctx) for check in CHECKS.values()]
    if args.history:
        reports.append(check_history(args.history, ctx))
    statuses = [show(report, args.require_all) for report in reports]
    failed = statuses.count("FAIL")
    skipped = statuses.count("SKIP")
    if failed:
        print(f"VERDICT: FAIL ({failed} of {len(reports)} checks)")
    elif skipped:
        print(f"VERDICT: PASS with {skipped} skipped ({len(reports)} checks; --require-all fails on a skip)")
    else:
        print(f"VERDICT: PASS ({len(reports)} checks)")
    control_failed = run_controls(files, ctx, args.require_all) if args.control else False
    sys.exit(1 if failed or control_failed else 0)


if __name__ == "__main__":
    main()
