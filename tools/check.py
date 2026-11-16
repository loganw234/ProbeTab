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
Programs are started by the full path shutil.which finds, never by a bare name;
the bench check's Python and the types check's tsc are found by their paths, as
those checks say.

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
             Where the manual is present with its pinned SHA-256 and pdftotext
             is found, no file shares a run of 8 or more words in a row with the
             manual's text. Without the manual, that part is skipped by name.
             How words are compared:
               - both texts are decomposed (NFKD), so a ligature or a
                 full-width letter counts as its plain letters, and an accented
                 letter as its letter;
               - marks (Unicode categories Mn and Me) and invisible format
                 characters (Cf) are removed;
               - case and punctuation are ignored;
               - a file with a UTF-32 or UTF-16 byte-order mark is read as
                 such.
             In the facts file, a line is excepted when its value is one of the
             facts' evidence phrases. A line shaped like one inside a note is
             checked, unless it repeats a fact's evidence.
             Limits: these are not caught:
               - a PDF inside another format, such as a zip;
               - an extract re-encoded (base64, say), or in UTF-16 or UTF-32
                 with no byte-order mark;
               - letters swapped for look-alikes from other scripts, or for
                 Latin letters that do not decompose into a plain letter and
                 a mark, such as ø, ł, đ, ħ and ı;
               - words or markup inserted every few words, or words broken by
                 a space or by an invisible character that is a letter or a
                 symbol, such as U+3164 or U+2800;
               - a passage in pieces of 7 words or fewer, or split across
                 files;
               - a close paraphrase, which a verifier judges;
               - many short evidence phrases that together carry a page.
             Matching depends on the pdftotext build, as for facts.
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
               - a home path through a WSL network share (wsl$ or
                 wsl.localhost);
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
  facts      protocol/labpro-facts.toml parses, and every fact in it has:
               - a value;
               - a source listed under [source];
               - a page;
               - evidence of 16 to 200 characters;
               - a status, "manual" or "bench".
             A fact is a table holding no further tables, as
             tools/labpro_facts.py decides. A bench fact names a recording: a
             file name in protocol/traces/, listed in SHA256SUMS with its hash,
             that parses as a recording.
             Where the manual is present with its pinned SHA-256 and pdftotext
             is found, each fact's evidence must appear on its cited page, with
             runs of whitespace collapsed; otherwise that part is skipped by
             name.
             Limits:
               - whether a fact's value agrees with its evidence is not
                 checked;
               - whether a recording was recorded rather than written is not
                 checked (see traces);
               - source tables are not checked beyond what the evidence check
                 uses;
               - matching depends on the pdftotext build, whose version is
                 printed; another build may lay a page out differently.
  traces     protocol/traces/SHA256SUMS and the .trace files beside it agree in
             both directions, and each listed file's bytes match its hash.
             These must parse, as tools/traces.py defines the format:
               - every .trace file in protocol/traces/, as a recording;
               - every .trace file in protocol/fixtures/, as a fixture;
               - the example in protocol/traces/FORMAT.md, as a recording.
             Nothing else sits in either folder, apart from SHA256SUMS and
             FORMAT.md in protocol/traces/ and README.md in protocol/fixtures/.
             tools/traces.py's writer refuses what would not read back as
             given, and --control holds it to that. A header's device lines
             hold to FORMAT.md: a device descriptor of 18 bytes, a
             configuration descriptor as long as it says, and a serial masked
             as tools/traces.py's rule keeps it.
             Limits:
               - a fixture copied into protocol/traces/ with a recording's
                 header passes. Which traces were recorded is the lead's
                 ledger's record, not the gate's;
               - a descriptor's fields beyond its length and type are not
                 checked.
  generated  app/src/generated/labpro-facts.ts and app/test/generated/fixtures.ts
             are exactly what tools/generate.py makes of
             protocol/labpro-facts.toml and of the fixtures in
             protocol/fixtures/. Node loads both. It must find every fact's
             value, unit, channels, source, page and status equal to the
             TOML's, and every fixture's model and transfers equal to what
             tools/traces.py reads, type included: a boolean equals only a
             boolean, and a string only a string.
             With no node on PATH, that round trip is skipped by name. A Node
             that cannot load .ts files fails it, naming its version.
             Limits:
               - JavaScript has one number type, so an integer and a
                 whole-number float of the same value are the same to it, and
                 to this check;
               - TypeScript's types are not checked, as Node strips them;
               - what the app does with the values is not checked.
  bench      The bench script's tests pass. Each tools/bench/test_*.py is run,
             and its tests replay fixtures through a fake pyusb backend in
             place of a LabPro. A file passes only when it ran at least one
             test and unittest's summary is plain OK: a skipped test, an
             expected failure or an unexpected success fails it. A file still
             running after 300 seconds fails by name. The tests run
             under a Python that has pyusb: the one running this script if it
             has it, otherwise the repository's .venv, found by its path. With
             neither, the check is skipped by name. In what it reports, the
             paths of the repository and the temp folder are shown as <repo>
             and <temp>, where written plainly, with the doubled backslashes
             of a Python repr, or with forward slashes as in a file URL;
             other forms, and other paths, are not rewritten.
             Limits:
               - the fake is the lead's model of a LabPro, built from the facts
                 and a fixture, so passing tests say the script agrees with
                 that model, not with a LabPro;
               - the script's paths through a real backend, such as libusb,
                 are not run;
               - what the tests assert is not read here, only whether they
                 pass; --control plants faults they must catch;
               - a test deleted from a file that still runs, or a test file
                 deleted, goes unnoticed; review has to catch those.
  app        The app's tests pass, and its simulated LabPro stays apart from
             its protocol code:
               - each app/test/*.test.ts runs alone, in a node process of its
                 own, under the TAP reporter. A file passes only when node
                 exits 0 and prints its summary, with at least one test, and
                 every test passed. A failure, a skip, a todo or a cancellation
                 fails it. So does a missing summary, which is what a file
                 gives that holds no tests or exits early. A file still running
                 after 300 seconds fails by name.
               - app/test/fake-labpro.ts reaches nothing under
                 app/src/protocol/. Its imports are followed through the
                 repository by their relative specifiers, percent-decoded and
                 compared without regard to case.
             With no node on PATH, the tests are skipped by name. Paths are
             shown as the bench check shows them.
             Limits:
               - the tests run on Node, not in a browser, and the WebUSB
                 transport runs against a simulated device;
               - an import whose path is built at run time, such as from a
                 template literal, or one reached through createRequire or
                 import.meta.resolve, is not followed;
               - the tests themselves are not type-checked (see types);
               - a test file that prints node's summary itself and exits 0
                 passes. That is forgery, which the threat model below leaves
                 to review;
               - an "imports" entry (a #name) in app/package.json can lead the
                 fake to the protocol code without this check seeing it;
               - a test deleted from a file that still runs goes unnoticed;
                 review has to catch it.
  types      app/src type-checks under tsc --noEmit with app/tsconfig.json,
             which allows erasable syntax only, so an enum, a namespace with
             code or a parameter property fails it, as it would fail Node. The
             tsc is the repository's app/node_modules one, found by its path,
             and it must be the version app/package.json pins. Without it, the
             check is skipped by name. No file in app/src may hold
             @ts-nocheck, @ts-ignore or @ts-expect-error, which would hide
             errors from tsc. A tsc still running after 300 seconds fails by
             name.
             Limits: tsc's timeout has no control of its own; and
             app/test is not type-checked, since that needs Node's own types
             (@types/node), which are not installed.

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
import json
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # noqa: E402
import labpro_facts  # noqa: E402
import traces  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FACTS = labpro_facts.FACTS
TRACES = "protocol/traces/"
FIXTURES = "protocol/fixtures/"
MANIFEST = TRACES + "SHA256SUMS"
FORMAT_DOC = TRACES + "FORMAT.md"
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+\.trace)")
EXAMPLE = re.compile(r"^```trace\n(.*?)^```", re.S | re.M)
RUN = 8  # a run of this many words in a row shared with the manual counts as copied
WORD = re.compile(r"[a-z0-9]+")
DROPPED = {"Mn", "Me", "Cf"}  # marks and invisible format characters, removed before words are compared
BENCH = "tools/bench/"
APP_TESTS = "app/test/"
FAKE = "app/test/fake-labpro.ts"
PROTOCOL_CODE = "app/src/protocol/"
TSC = "app/node_modules/typescript/bin/tsc"
TSCONFIG = "app/tsconfig.json"
TS_DIRECTIVES = ("@ts-nocheck", "@ts-ignore", "@ts-expect-error")  # each hides errors from tsc
IMPORT = re.compile(r"""\bfrom\s*["']([^"']+)["']|\bimport\s*\(\s*["']([^"']+)["']\s*\)|^\s*import\s*["']([^"']+)["']""",
                    re.M)
EVIDENCE_LINE = re.compile(r"""^evidence = (?:"[^"\n]*"|'[^'\n]*')[ \t]*$""", re.M)
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
        self.runs = {}
        self.render = generate.render  # a control may put a mutant here
        self.render_fixtures = generate.render_fixtures  # and here
        self.files = []                # the real file set, for controls that build copies
        self.pythons = None            # where the bench check looks for pyusb; a control may narrow it
        self.test_timeout = 300        # seconds a test file, or tsc, may run; a control shortens it


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


def words_of(text):
    """Words as the word-run check compares them.

    The text is decomposed (NFKD), so a ligature or a full-width letter becomes
    its plain letters, and an accented letter its letter and its accent. Marks
    (categories Mn and Me, such as accents and the combining grapheme joiner)
    and invisible format characters (Cf, such as zero-width spaces and soft
    hyphens) are removed, and it is lower-cased; that is done twice, as
    lower-casing can itself add a mark. Only letters a to z and digits count.
    """
    def plain(part):
        return "".join(ch for ch in unicodedata.normalize("NFKD", part) if unicodedata.category(ch) not in DROPPED)

    return WORD.findall(plain(plain(text).lower()))


def file_text(data):
    """A file's text for the word-run check: UTF-32 or UTF-16 by its byte-order mark, otherwise UTF-8."""
    if data[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return data.decode("utf-32", errors="replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def drop_evidence_lines(text, root):
    """The facts file's text with each line that gives a fact its own evidence blanked.

    That is the one place the manual's own words belong. A line shaped like
    one whose value is no fact's evidence, such as one inside a note, is kept
    and checked.
    """
    try:
        evidence = {str(fact.get("evidence")) for _, fact in labpro_facts.facts(labpro_facts.load(root))}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return text
    kept = []
    for line in text.split("\n"):
        if EVIDENCE_LINE.fullmatch(line):
            try:
                value = tomllib.loads(line).get("evidence")
            except tomllib.TOMLDecodeError:
                value = None
            if value in evidence:
                kept.append("")
                continue
        kept.append(line)
    return "\n".join(kept)


def word_runs(pages):
    words = words_of(" ".join(pages))
    return {tuple(words[i:i + RUN]) for i in range(len(words) - RUN + 1)}


def shared_runs(text, runs):
    """(line, length) for each run of RUN or more words in a row that text shares with the manual."""
    tokens = []
    for number, line in enumerate(text.split("\n"), start=1):
        tokens.extend((word, number) for word in words_of(line))
    words = [word for word, _ in tokens]
    found, index = [], 0
    while index + RUN <= len(words):
        if tuple(words[index:index + RUN]) in runs:
            end = index + 1
            while end + RUN <= len(words) and tuple(words[end:end + RUN]) in runs:
                end += 1
            found.append((tokens[index][1], end - index + RUN - 1))
            index = end + RUN - 1
        else:
            index += 1
    return found


def check_reference(root, files, ctx):
    report = Report("reference")
    source = manual_source(root)
    pin = source.get("sha256")
    if not pin:
        report.fail(f"{FACTS} pins no sha256 for the manual, so its bytes cannot be refused")
    for name in files:
        data = (root / name).read_bytes()
        if name.lower().endswith(".pdf") or b"%PDF-" in data[:1024]:
            report.fail(f"{name}: a PDF; reference material stays out of the repository")
        if pin and hashlib.sha256(data).hexdigest() == pin:
            report.fail(f"{name}: has the bytes of Vernier's manual")
    report.note(f"{len(files)} files read")
    pages = manual_pages("trm", source, ctx, report, "copied runs") if pin else None
    if pages is None:
        return report
    if pin not in ctx.runs:
        ctx.runs[pin] = word_runs(pages)
    copied = 0
    for name in files:
        text = file_text((root / name).read_bytes())
        if name == FACTS:
            text = drop_evidence_lines(text, root)
        for line, length in shared_runs(text, ctx.runs[pin]):
            copied += 1
            report.fail(f"{name}:{line}: shares a run of {length} words with the manual")
    if not copied:
        report.note(f"no file shares {RUN} words in a row with the manual, outside evidence lines")
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


def trace_census(root, files):
    """(listed, present, states, general).

    listed:  what SHA256SUMS lists, name -> sha256.
    present: the .trace files in protocol/traces/.
    states:  each present file's problem, or None when it is a sound recording.
    general: problems with the folder as a whole.
    """
    listed, general = {}, []
    if MANIFEST in files:
        text = (root / MANIFEST).read_bytes().decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            match = MANIFEST_LINE.fullmatch(line)
            if not match:
                general.append(f"{MANIFEST}:{number}: not a '<sha256>  <name>.trace' line")
            elif match.group(2) in listed:
                general.append(f"{MANIFEST}:{number}: lists {match.group(2)} twice")
            else:
                listed[match.group(2)] = match.group(1)
    else:
        general.append(f"{MANIFEST} is missing")
    for name in files:
        if name.startswith(TRACES) and not name.endswith(".trace") and name not in (MANIFEST, FORMAT_DOC):
            general.append(f"{name}: only recordings, SHA256SUMS and FORMAT.md belong in {TRACES}")
    present, states = set(), {}
    for name in files:
        if not (name.startswith(TRACES) and name.endswith(".trace")):
            continue
        short = name[len(TRACES):]
        if "/" in short:
            general.append(f"{name}: recordings sit directly in {TRACES}, not in a folder under it")
            continue
        present.add(short)
        data = (root / name).read_bytes()
        if short in listed and hashlib.sha256(data).hexdigest() != listed[short]:
            states[short] = "its bytes do not match SHA256SUMS"
            continue
        try:
            trace = traces.parse(data.decode("utf-8"))
        except UnicodeDecodeError:
            states[short] = "it is not UTF-8 text"
            continue
        except traces.TraceError as exc:
            states[short] = str(exc)
            continue
        states[short] = None if trace.kind == "trace" else \
            f"it is a {trace.kind}, and only recordings belong in {TRACES}"
    return listed, present, states, general


def bench_problem(trace, census):
    """Why a bench fact's trace is not a sound, listed recording, or None if it is one."""
    listed, present, states, _ = census
    if not isinstance(trace, str) or not trace.endswith(".trace") or "/" in trace or "\\" in trace:
        return f"a bench fact's trace must be a file name in {TRACES}, and {trace!r} is not one"
    if trace not in present:
        return f"its trace {trace} is not in {TRACES}"
    if trace not in listed:
        return f"its trace {trace} is not listed in SHA256SUMS"
    if states.get(trace):
        return f"its trace {trace} is not a sound recording: {states[trace]}"
    return None


def manual_pages(key, source, ctx, report, purpose="evidence"):
    """The source's pages as collapsed text, or None with the reason reported."""
    local = source.get("local")
    if not local:
        report.skip(f"{purpose} for source {key!r} not checked: it names no local copy")
        return None
    path = ctx.reference_root / local
    if not path.is_file():
        report.skip(f"{purpose} not checked: {local} is not in the repository folder")
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source.get("sha256"):
        report.fail(f"{local} is present, but its SHA-256 is not the one pinned; the pages cited are the pinned file's")
        return None
    pdftotext = tool("pdftotext")
    if not pdftotext:
        report.skip(f"{purpose} not checked: pdftotext is not on PATH")
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
    facts = labpro_facts.facts(data, stray=lambda name: report.fail(f"{name} sits outside any fact table"))
    census = trace_census(root, files)
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
        elif fact["status"] == "bench":
            problem = bench_problem(fact.get("trace"), census)
            if problem:
                report.fail(f"{name}: {problem}")
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


def check_traces(root, files, ctx):
    report = Report("traces")
    listed, present, states, general = trace_census(root, files)
    for message in general:
        report.fail(message)
    for name in sorted(present - listed.keys()):
        report.fail(f"{TRACES}{name}: not listed in SHA256SUMS")
    for name in sorted(listed.keys() - present):
        report.fail(f"SHA256SUMS lists {name}, which is not in {TRACES}")
    for name in sorted(present):
        if states.get(name):
            report.fail(f"{TRACES}{name}: {states[name]}")
    for name in files:
        if name.startswith(FIXTURES) and not name.endswith(".trace") and name != FIXTURES + "README.md":
            report.fail(f"{name}: only fixtures and README.md belong in {FIXTURES}")
    fixtures = [name for name in files if name.startswith(FIXTURES) and name.endswith(".trace")]
    for name in fixtures:
        try:
            fixture = traces.parse((root / name).read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, traces.TraceError) as exc:
            report.fail(f"{name}: {exc}")
            continue
        if fixture.kind != "fixture":
            report.fail(f"{name}: it is a {fixture.kind}, and only fixtures belong in {FIXTURES}")
    examples = []
    if FORMAT_DOC not in files:
        report.fail(f"{FORMAT_DOC} is missing")
    else:
        examples = EXAMPLE.findall((root / FORMAT_DOC).read_bytes().decode("utf-8", errors="replace"))
        if not examples:
            report.fail(f"{FORMAT_DOC} has no trace example to check")
        for example in examples:
            try:
                parsed = traces.parse(example)
            except traces.TraceError as exc:
                report.fail(f"{FORMAT_DOC}: its example does not parse: {exc}")
                continue
            if parsed.kind != "trace":
                report.fail(f"{FORMAT_DOC}: its example is a {parsed.kind}, not a recording")
    def count(number, noun):
        return f"{number} {noun}{'' if number == 1 else 's'}"

    report.note(f"{count(len(present), 'recording')}, {count(len(fixtures), 'fixture')}, "
                f"{count(len(examples), 'example')} in {FORMAT_DOC}")
    return report


def same_value(got, want):
    """Equal as the app sees them: a boolean equals only a boolean, and a string only a string.
    JavaScript has one number type, so an int and a float of the same value are one number."""
    if isinstance(got, bool) or isinstance(want, bool):
        return type(got) is type(want) and got == want
    if isinstance(got, (int, float)) and isinstance(want, (int, float)):
        return got == want
    return type(got) is type(want) and got == want


def same_fact(got, want):
    return (isinstance(got, dict) and isinstance(want, dict) and got.keys() == want.keys()
            and all(same_value(got[key], want[key]) for key in want))


def same_json(got, want):
    """Equal as same_value has it, all the way down through objects and arrays."""
    if isinstance(want, dict):
        return isinstance(got, dict) and got.keys() == want.keys() and all(same_json(got[k], want[k]) for k in want)
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(map(same_json, got, want))
    return same_value(got, want)


def node_export(node, path, export):
    """(the export's value, None), loaded from the module at path through Node, or (None, why not)."""
    script = (f"import(process.argv[1]).then(m => process.stdout.write(JSON.stringify(m[{json.dumps(export)}] ?? null)),"
              " e => { process.stderr.write(String(e)); process.exit(1); })")
    loaded = subprocess.run([node, "-e", script, path.resolve().as_uri()], capture_output=True)
    if loaded.returncode != 0:
        return None, loaded.stderr.decode("utf-8", errors="replace").strip()[:300]
    value = json.loads(loaded.stdout.decode("utf-8"))
    return (value, None) if value is not None else (None, f"it has no export {export}")


def check_generated(root, files, ctx):
    report = Report("generated")
    output, fixtures_output = generate.OUTPUT, generate.FIXTURES_OUTPUT
    try:
        data = labpro_facts.load(root)
        expected = ctx.render(data)
        found = generate.fixtures(root)
        expected_fixtures = ctx.render_fixtures(found)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, generate.Refused) as exc:
        report.fail(f"the generator cannot run: {exc}")
        return report
    for name, text, source in ((output, expected, FACTS), (fixtures_output, expected_fixtures, generate.FIXTURES)):
        if name not in files:
            report.fail(f"{name} is missing; run python tools/generate.py")
        elif (root / name).read_bytes() != text.encode("utf-8"):
            report.fail(f"{name} differs from what tools/generate.py makes of {source}; run python tools/generate.py")
    if any(name not in files for name in (output, fixtures_output)):
        return report
    node = tool("node")
    if not node:
        report.skip("the round trip through Node is not checked: node is not on PATH")
        return report
    version = subprocess.run([node, "--version"], capture_output=True).stdout.decode("ascii", errors="replace").strip()
    got, problem = node_export(node, root / output, "LABPRO_FACTS")
    if problem:
        report.fail(f"node {version} could not load {output}; the round trip needs a Node that loads .ts "
                    f"files by stripping types: {problem}")
        return report
    want = {name: {field: fact.get(field) for field in generate.FIELDS}
            for name, fact in labpro_facts.facts(data)}
    for name in sorted(set(got) | set(want)):
        if not same_fact(got.get(name), want.get(name)):
            report.fail(f"round trip: {name} loads from {output} as {got.get(name)!r}, "
                        f"but {FACTS} has {want.get(name)!r}")
    got_fixtures, problem = node_export(node, root / fixtures_output, "FIXTURES")
    if problem:
        report.fail(f"node {version} could not load {fixtures_output}: {problem}")
        return report
    want_fixtures = {name: {"model": trace.header["model"],
                            "transfers": [{"direction": direction, "micros": micros, "bytes": data.hex(" ")}
                                          for direction, micros, data in trace.transfers]}
                     for name, trace in found}
    for name in sorted(set(got_fixtures) | set(want_fixtures)):
        if not same_json(got_fixtures.get(name), want_fixtures.get(name)):
            report.fail(f"round trip: {name} loads from {fixtures_output} unlike {generate.FIXTURES}{name}")
    fixtures_counted = f"{len(want_fixtures)} fixture{'' if len(want_fixtures) == 1 else 's'}"
    report.note(f"{len(want)} facts and {fixtures_counted} loaded back through node {version} ({node})")
    return report


def reached(root, start):
    """{file: the chain of imports from start to it}, for each repository file that start
    imports, directly or through other files, by a relative specifier."""
    chains, queue = {start: [start]}, [start]
    while queue:
        name = queue.pop(0)
        path = root / name
        if not path.is_file():
            continue
        for match in IMPORT.finditer(path.read_bytes().decode("utf-8", errors="replace")):
            specifier = next(group for group in match.groups() if group)
            if not specifier.startswith("."):
                continue
            # Node resolves a percent-encoded path, and Windows a path in any case, so both are read as the file.
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(specifier)))
            if target not in chains:
                chains[target] = chains[name] + [target]
                queue.append(target)
    return chains


def tap_problems(output):
    """One line for each failing test in node's TAP report: its name, then what it raised."""
    problems, lines = [], output.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^\s*not ok \d+ - (.*)$", line)
        if not match:
            continue
        details = []
        for detail in lines[index + 1:]:
            stripped = detail.strip()
            if re.match(r"^(ok|not ok) \d+ ", stripped) or stripped == "..." or stripped.startswith("stack:"):
                break
            if stripped and not stripped.startswith(("---", "duration_ms:", "type:", "location:")):
                details.append(stripped)
        problems.append(f"{match.group(1)}: {collapse(' '.join(details))[:600]}")
    return problems


def check_app(root, files, ctx):
    report = Report("app")
    tests = [name for name in files if name.startswith(APP_TESTS) and name.endswith(".test.ts")]
    if not tests:
        report.fail(f"{APP_TESTS} holds no *.test.ts, so nothing tests the app")
        return report
    if FAKE not in files:
        report.fail(f"{FAKE} is missing")
    else:
        for target, chain in sorted(reached(root, FAKE).items()):
            if target.casefold().startswith(PROTOCOL_CODE.casefold()):
                report.fail(f"{' -> '.join(chain)}: the fake shares no code with the protocol code")
    node = tool("node")
    if not node:
        report.skip("the app's tests are not run: node is not on PATH")
        return report
    version = subprocess.run([node, "--version"], capture_output=True).stdout.decode("ascii", errors="replace").strip()
    passed = 0
    for name in tests:
        # Each file runs alone, in one process: node prints its TAP summary only when the file's
        # tests ran to their end, so a file that holds none, or exits early, prints none.
        try:
            run = subprocess.run([node, "--test-reporter=tap", name], cwd=root, capture_output=True,
                                 timeout=ctx.test_timeout)
        except subprocess.TimeoutExpired:
            report.fail(f"{name}: did not finish within {ctx.test_timeout} s, so it counts as failed")
            continue
        output = (run.stdout + run.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
        output = masked(output, ((str(root), "<repo>"), (tempfile.gettempdir(), "<temp>")))
        counts = {key: int(value) for key, value in re.findall(
            r"^# (tests|pass|fail|cancelled|skipped|todo) (\d+)$", output, re.M)}
        unpassed = {key: counts[key] for key in ("fail", "cancelled", "skipped", "todo") if counts.get(key)}
        if run.returncode == 0 and counts.get("tests", 0) > 0 and counts.get("pass") == counts["tests"] \
                and not unpassed:
            passed += counts["pass"]
            continue
        problems = tap_problems(output)
        if "tests" not in counts:
            problems.append("node printed no TAP summary, so the file held no tests or ended before they did")
        if unpassed:
            problems.append("node reports " + ", ".join(f"{number} {key}" for key, number in unpassed.items())
                            + "; only a test that passes counts")
        # A file that fails to load prints its cause, not a TAP result.
        causes = [line.removeprefix("# ").strip() for line in output.split("\n")
                  if re.match(r"^(?:# )?(?:\w*Error\b|\s*code: '[A-Z_]+')", line)]
        if causes:
            problems.append(f"node's diagnostics: {collapse(' | '.join(causes))[:600]}")
        for problem in problems or [collapse(output)[-300:] or f"node exited with status {run.returncode}"]:
            report.fail(f"{name}: {problem}")
    report.note(f"{passed} tests passed under node {version} ({node}), each file run alone"
                if not report.fails else f"run under node {version} ({node})")
    return report


def check_types(root, files, ctx):
    report = Report("types")
    if TSCONFIG not in files:
        report.fail(f"{TSCONFIG} is missing")
        return report
    for name in files:
        if name.startswith("app/src/") and name.endswith(".ts"):
            text = (root / name).read_bytes().decode("utf-8", errors="replace")
            for directive in TS_DIRECTIVES:
                if directive in text:
                    report.fail(f"{name}: holds {directive}, which would hide errors from this check")
    tsc = ctx.reference_root / TSC
    if not tsc.is_file():
        report.skip("app/src is not type-checked: typescript is not installed in app/node_modules; "
                    "app/README.md says how to install it")
        return report
    node = tool("node")
    if not node:
        report.skip("app/src is not type-checked: node is not on PATH")
        return report
    try:
        pinned = json.loads((root / "app/package.json").read_bytes())["devDependencies"]["typescript"]
    except (OSError, ValueError, KeyError, TypeError):
        report.fail("app/package.json pins no typescript version")
        return report
    installed = subprocess.run([node, str(tsc), "--version"], capture_output=True).stdout.decode(
        "ascii", errors="replace").strip().removeprefix("Version ")
    if installed != pinned:
        report.fail(f"app/node_modules has TypeScript {installed}, but app/package.json pins {pinned}; "
                    f"run npm ci in app/")
        return report
    try:
        run = subprocess.run([node, str(tsc), "--noEmit", "-p", str(root / TSCONFIG)], cwd=root, capture_output=True,
                             timeout=ctx.test_timeout)
    except subprocess.TimeoutExpired:
        report.fail(f"tsc did not finish within {ctx.test_timeout} s")
        return report
    output = masked((run.stdout + run.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n"),
                    ((str(root), "<repo>"), (tempfile.gettempdir(), "<temp>")))
    if run.returncode != 0:
        errors = [line.strip() for line in output.split("\n") if re.search(r"error TS\d+", line)]
        for error in errors or [collapse(output)[-300:] or f"tsc exited with status {run.returncode}"]:
            report.fail(error)
        return report
    report.note(f"app/src type-checked by TypeScript {installed}, the version app/package.json pins")
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


def bench_pythons(ctx):
    """Where the bench check looks for a Python with pyusb, in order, each with how it is named."""
    if ctx.pythons is not None:
        return ctx.pythons
    venv = ctx.reference_root / ".venv"
    return [("the Python running this script", Path(sys.executable)),
            (".venv/Scripts/python.exe", venv / "Scripts" / "python.exe"),
            (".venv/bin/python", venv / "bin" / "python")]


def bench_python(ctx):
    """(a Python that has pyusb, how to say which), or (None, why there is none)."""
    probe = "import platform, usb; print(platform.python_version(), usb.__version__)"
    for label, python in bench_pythons(ctx):
        if not python.is_file():
            continue
        found = subprocess.run([str(python), "-I", "-B", "-c", probe], capture_output=True)
        if found.returncode == 0:
            version, pyusb = found.stdout.decode("ascii", errors="replace").split()[:2]
            return python, f"python {version} with pyusb {pyusb} ({label})"
    return None, ("pyusb is in neither the Python running this script nor .venv; "
                  "tools/bench/README.md says how to install it")


def test_problems(output):
    """One line for each failing test in unittest's report: its name, then what it raised."""
    problems = []
    for block in re.split(r"^={40,}$", output, flags=re.M)[1:]:
        lines = block.strip("\n").split("\n")
        message, started = [], False
        for line in lines[1:]:
            if re.fullmatch(r"-{40,}", line):
                if started:
                    break
                continue
            if not started and (line.startswith("Traceback") or line.startswith(" ") or not line.strip()):
                continue
            started = True
            message.append(line)
        problems.append(f"{lines[0].strip()}: {collapse(' '.join(message))[:1200]}")
    return problems


def masked(text, paths):
    """text with each (path, name) in paths shown as name, where the path is written plainly, with
    the doubled backslashes a Python repr gives it on Windows, or with forward slashes, as in a
    file URL."""
    for path, name in paths:
        text = text.replace(path, name)
        if "\\" in path:
            text = text.replace(path.replace("\\", "\\\\"), name).replace(path.replace("\\", "/"), name)
    return text


def check_bench(root, files, ctx):
    report = Report("bench")
    tests = [name for name in files
             if name.startswith(BENCH) and posixpath.basename(name).startswith("test_") and name.endswith(".py")]
    if not tests:
        report.fail(f"{BENCH} holds no test_*.py, so nothing tests the bench script")
        return report
    python, which = bench_python(ctx)
    if python is None:
        report.skip(f"the bench script's tests are not run: {which}")
        return report
    passed = 0
    temp = tempfile.gettempdir()
    for name in tests:
        try:
            run = subprocess.run([str(python), "-I", "-B", str(root / name)], cwd=root, capture_output=True,
                                 timeout=ctx.test_timeout)
        except subprocess.TimeoutExpired:
            report.fail(f"{name}: did not finish within {ctx.test_timeout} s, so it counts as failed")
            continue
        # On Windows, Python writes CRLF to a piped stderr; the report is read line by line. Paths under
        # the repository and the temp folder can name the user, so they are shown as <repo> and <temp>.
        output = run.stderr.decode("utf-8", errors="replace").replace("\r\n", "\n")
        output = masked(output, ((str(root), "<repo>"), (temp, "<temp>")))
        ran = re.search(r"^Ran (\d+) tests? in ", output, re.M)
        summary = output.strip().split("\n")[-1].strip()
        if run.returncode == 0 and ran and int(ran.group(1)) > 0 and summary == "OK":
            passed += int(ran.group(1))
            continue
        if run.returncode == 0 and ran and summary.startswith("OK ("):
            report.fail(f"{name}: unittest reports {summary}; a skipped test, an expected failure or an "
                        f"unexpected success is not a pass")
            continue
        problems = test_problems(output) or [collapse(output)[-300:] or f"it exited with status {run.returncode}"]
        for problem in problems:
            report.fail(f"{name}: {problem}")
    if report.fails:
        report.note(f"run by {which}")
    else:
        report.note(f"{passed} tests passed against the fake backend, run by {which}")
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
    "traces": check_traces,
    "generated": check_generated,
    "bench": check_bench,
    "app": check_app,
    "types": check_types,
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


RECORDING_HEADER = {"date": "2026-11-20T14:03:11-07:00", "os": "planted os",
                    "stack": "planted stack", "firmware": "unknown"}


def plant_recording(root, name="planted.trace", listed=True, text=None):
    """A recording in the copy's protocol/traces/, listed in SHA256SUMS unless told otherwise."""
    text = text or traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s{7}\r"), ("IN", 1532, b"{ 1.0}\r")])
    append(root, TRACES + name, text)
    if listed:
        append(root, MANIFEST, f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  {name}\n")
    return name


def plant_changed_recording(root, files, ctx):
    name = plant_recording(root)
    path = root / TRACES / name
    path.write_bytes(path.read_bytes().replace(b" 0d\n", b" 0a\n", 1))
    return walked_files(root)


def plant_odd_hex(root, files, ctx):
    sound = traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")])
    plant_recording(root, "odd.trace", text=sound.replace("OUT 0 73", "OUT 0 7"))
    return walked_files(root)


def plant_host_header(root, files, ctx):
    sound = traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")])
    plant_recording(root, "host.trace",
                    text=sound.replace("# firmware: unknown\n", "# firmware: unknown\n# host: planted-bench\n"))
    return walked_files(root)


def plant_unlisted_recording(root, files, ctx):
    plant_recording(root, "unlisted.trace", listed=False)
    return walked_files(root)


def plant_ghost_listing(root, files, ctx):
    append(root, MANIFEST, "0" * 64 + "  ghost.trace\n")
    return walked_files(root)


def plant_fixture_among_recordings(root, files, ctx):
    fixtures = sorted((root / FIXTURES).glob("*.trace"))
    if not fixtures:
        raise Unplantable(f"no fixture in {FIXTURES} to copy")
    plant_recording(root, fixtures[0].name, text=fixtures[0].read_bytes().decode("utf-8"))
    return walked_files(root)


def plant_recording_among_fixtures(root, files, ctx):
    append(root, FIXTURES + "recorded.trace", traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")]))
    return walked_files(root)


def plant_stray_among_recordings(root, files, ctx):
    append(root, TRACES + "session-notes.txt", "planted\n")
    return walked_files(root)


def plant_stray_among_fixtures(root, files, ctx):
    append(root, FIXTURES + "sketch.bin", b"planted\n")
    return walked_files(root)


def plant_broken_example(root, files, ctx):
    edit(root, FORMAT_DOC, r"OUT 0 73 7b 37 7d 0d", "OUT 0 73 7b 3 7d 0d", within="```trace")
    return files


def plant_hand_edited_generated(root, files, ctx):
    edit(root, generate.OUTPUT, r"value: 2295,", "value: 2296,", within='"usb.vendor_id"')
    return files


def plant_bench_fact_on_fixture(root, files, ctx):
    edit(root, FACTS, r'status = "manual"', 'status = "bench"\ntrace = "../fixtures/status-request.trace"',
         within=FACT)
    return files


def plant_bench_fact_on_missing_name(root, files, ctx):
    edit(root, FACTS, r'status = "manual"', 'status = "bench"\ntrace = "nonexistent.trace"', within=FACT)
    return files


def plant_bench_fact_on_fixture_name(root, files, ctx):
    edit(root, FACTS, r'status = "manual"', 'status = "bench"\ntrace = "status-request.trace"', within=FACT)
    return files


def plant_bench_fact_on_unlisted(root, files, ctx):
    name = plant_recording(root, "unlisted.trace", listed=False)
    edit(root, FACTS, r'status = "manual"', f'status = "bench"\ntrace = "{name}"', within=FACT)
    return walked_files(root)


def plant_bench_fact_on_changed(root, files, ctx):
    name = plant_recording(root)
    path = root / TRACES / name
    path.write_bytes(path.read_bytes().replace(b" 0d\n", b" 0a\n", 1))
    edit(root, FACTS, r'status = "manual"', f'status = "bench"\ntrace = "{name}"', within=FACT)
    return walked_files(root)


def plant_duplicate_listing(root, files, ctx):
    plant_recording(root)
    last = (root / MANIFEST).read_bytes().decode("utf-8").split("\n")[-2]
    append(root, MANIFEST, last + "\n")
    return walked_files(root)


def plant_recording_in_subfolder(root, files, ctx):
    append(root, TRACES + "old/sub.trace", traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")]))
    return walked_files(root)


def plant_malformed_listing(root, files, ctx):
    append(root, MANIFEST, "not-a-hash  planted.trace\n")
    return walked_files(root)


def plant_example_as_fixture(root, files, ctx):
    path = root / FORMAT_DOC
    fixture = traces.write("fixture", {"date": RECORDING_HEADER["date"], "model": "planted"}, [("OUT", 0, b"s")])
    changed, count = EXAMPLE.subn(lambda match: "```trace\n" + fixture + "```",
                                  path.read_bytes().decode("utf-8"), count=1)
    if not count:
        raise RuntimeError(f"control cannot be planted: {FORMAT_DOC} has no example")
    path.write_bytes(changed.encode("utf-8"))
    return files


def plant_date_with_space(root, files, ctx):
    sound = traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")])
    plant_recording(root, "spaced.trace", text=sound.replace("2026-11-20T14:03:11", "2026-11-20 14:03:11"))
    return walked_files(root)


def plant_unprintable_header(root, files, ctx):
    sound = traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s")])
    plant_recording(root, "unprintable.trace",
                    text=sound.replace("# os: planted os", "# os: planted" + chr(0x2028) + "os"))
    return walked_files(root)


def manual_page(root, ctx, number):
    source = manual_source(root)
    pages = manual_pages("trm", source, ctx, Report("unused"), "copied runs") if source.get("sha256") else None
    if not pages:
        raise Unplantable("the manual's text is not available")
    return pages[number - 1]


def plant_pasted_manual_sentence(root, files, ctx):
    append(root, "docs/README.md", "\n" + " ".join(manual_page(root, ctx, 22).split()[40:52]) + "\n")
    return files


def plant_run_of_eight(root, files, ctx):
    words = words_of(manual_page(root, ctx, 22))[40:48]
    append(root, "docs/README.md", "\nzzplanted " + " ".join(words) + " zzplanted\n")
    return files


def plant_zero_width_run(root, files, ctx):
    words = words_of(manual_page(root, ctx, 22))[40:56]
    split = [word[0] + chr(0x200B) + word[1:] if index % 5 == 4 and len(word) > 1 else word
             for index, word in enumerate(words)]
    append(root, "docs/README.md", "\n" + " ".join(split) + "\n")
    return files


def plant_utf16_run(root, files, ctx):
    words = words_of(manual_page(root, ctx, 22))[40:56]
    append(root, "docs/notes.txt", (chr(0xFEFF) + " ".join(words) + "\n").encode("utf-16-le"))
    return walked_files(root)


def plant_evidence_line_in_a_note(root, files, ctx):
    words = words_of(manual_page(root, ctx, 22))[40:63]
    edit(root, FACTS, r'status = "manual"',
         'status = "manual"\nnote = """\nevidence = \'' + " ".join(words) + '\'\n"""', within=FACT)
    return files


def plant_evidence_in_a_comment(root, files, ctx):
    phrases = [str(fact.get("evidence", "")) for _, fact in labpro_facts.facts(labpro_facts.load(root))]
    long = [phrase for phrase in phrases if len(WORD.findall(phrase.lower())) >= RUN + 2]
    if not long:
        raise RuntimeError("control cannot be planted: no evidence phrase of ten words or more")
    append(root, FACTS, "\n# " + long[0] + "\n")
    return files


def manual_run(root, ctx, length, keep):
    """length words in a row from page 22, from its 41st word on, each one that keep accepts."""
    words = words_of(manual_page(root, ctx, 22))
    for start in range(40, len(words) - length):
        run = words[start:start + length]
        if all(keep(word) for word in run):
            return run
    raise RuntimeError(f"control cannot be planted: page 22 has no run of {length} such words")


ACCENTED = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ý"}


def plant_accented_run(root, files, ctx):
    words = manual_run(root, ctx, 12, keep=lambda word: any(ch in ACCENTED for ch in word))
    accented = []
    for word in words:
        index = next(i for i, ch in enumerate(word) if ch in ACCENTED)
        accented.append(word[:index] + ACCENTED[word[index]] + word[index + 1:])
    append(root, "docs/README.md", "\n" + " ".join(accented) + "\n")
    return files


def plant_joiner_run(root, files, ctx):
    words = manual_run(root, ctx, 12, keep=lambda word: len(word) > 1)
    append(root, "docs/README.md", "\n" + " ".join(word[0] + chr(0x034F) + word[1:] for word in words) + "\n")
    return files


def plant_utf32_run(root, files, ctx):
    words = words_of(manual_page(root, ctx, 22))[40:56]
    append(root, "docs/notes32.txt", (chr(0xFEFF) + " ".join(words) + "\n").encode("utf-32-le"))
    return walked_files(root)


def plant_bench_sends_a_reset(root, files, ctx):
    edit(root, BENCH + "labpro_bench.py", r'self\.facts\["command\.request_system_status"\]',
         'self.facts["command.reset"]', within="    def status(self)")
    return files


def plant_bench_resetting_a_busy_unit(root, files, ctx):
    edit(root, BENCH + "labpro_bench.py", r'RESETTABLE = \("status\.state_idle", "status\.state_done"\)',
         'RESETTABLE = ("status.state_idle", "status.state_done", "status.state_busy")', within="RESETTABLE")
    return files


def plant_discard_resetting_a_busy_unit(root, files, ctx):
    edit(root, BENCH + "labpro_bench.py", r"if name not in RESETTABLE:", "if name not in RESETTABLE and not discard:",
         within="def read_ch1")
    return files


def plant_ch1_reply_corrupted(root, files, ctx):
    """Command 9's first value in the CH1 fixture, +1.94383E+00, loses its leading digit to an x."""
    edit(root, FIXTURES + "ch1-reading.trace", r"7b 20 2b 31 2e 39 34 33 38 33", "7b 20 2b 78 2e 39 34 33 38 33",
         within="# probetab-fixture 1")
    return files


def recording_with(line):
    """A recording's text with one header line added, written by hand so that the writer cannot refuse it."""
    text = traces.write("trace", RECORDING_HEADER, [("OUT", 0, b"s{7}\r"), ("IN", 1532, b"{ 1.0}\r")])
    head, rest = text.split("\n", 1)
    return f"{head}\n{line}\n{rest}"


def plant_short_device_line(root, files, ctx):
    plant_recording(root, text=recording_with("# device: " + " ".join(["12", "01"] + ["00"] * 15)))
    return walked_files(root)


def plant_unmasked_serial(root, files, ctx):
    plant_recording(root, text=recording_with("# serial: ABC12345XY"))
    return walked_files(root)


def plant_device_line_of_another_type(root, files, ctx):
    plant_recording(root, text=recording_with("# device: " + " ".join(["12", "02"] + ["00"] * 16)))
    return walked_files(root)


def plant_configuration_total_disagreeing(root, files, ctx):
    """A configuration line whose total-length field says 32 bytes, holding 31."""
    plant_recording(root, text=recording_with("# configuration: " + " ".join(["09", "02", "20", "00"] + ["00"] * 27)))
    return walked_files(root)


def plant_bench_resetting_an_initializing_unit(root, files, ctx):
    edit(root, BENCH + "labpro_bench.py", r'WAITING = \("status\.state_initializing", "status\.state_self_test"\)',
         'WAITING = ("status.state_self_test",)', within="WAITING")
    edit(root, BENCH + "labpro_bench.py", r'RESETTABLE = \("status\.state_idle", "status\.state_done"\)',
         'RESETTABLE = ("status.state_idle", "status.state_done", "status.state_initializing")', within="RESETTABLE")
    return files


def plant_bench_every_unbounded(root, files, ctx):
    edit(root, BENCH + "labpro_bench.py", r"if value > MAX_EVERY:", "if False:", within="def interval")
    return files


def plant_bench_losing_the_trace_to_an_error(root, files, ctx):
    """main writes the trace only when phase0 returns, as it did before the finally."""
    edit(root, BENCH + "labpro_bench.py", r"    try:\n        phase0\(facts, args, backend, say, run\)\n    finally:\n",
         "    phase0(facts, args, backend, say, run)\n    if True:\n", within="    run = Run()")
    return files


def plant_fixture_reply_changed(root, files, ctx):
    """8888, fourth in the fixture's reply, becomes 8887."""
    edit(root, FIXTURES + "status-request.trace", r"2b 38 2e 38 38 38 30 30", "2b 38 2e 38 38 37 30 30",
         within="# probetab-fixture 1")
    return files


def plant_bench_tests_skipped(root, files, ctx):
    edit(root, BENCH + "test_bench.py", r"class FirstContact\(unittest\.TestCase\):",
         '@unittest.skip("planted")\nclass FirstContact(unittest.TestCase):', within="class FirstContact")
    return files


def plant_bench_failure_showing_a_path(root, files, ctx):
    """A failing assertion whose message holds the script's output, and in it a scratch path, in a repr."""
    edit(root, BENCH + "test_bench.py", r'self\.assertIn\("never writes over a file", printed\)',
         'self.assertIn("zzplanted", printed)', within="def test_never_writes_over_a_file")
    return files


def plant_bench_tests_left_out(root, files, ctx):
    return [name for name in files if not (name.startswith(BENCH) and posixpath.basename(name).startswith("test_"))]


def plant_app_enum(root, files, ctx):
    append(root, "app/src/transport/transport.ts", "\nexport enum Planted { One }\n")
    return files


def plant_parameter_property(root, files, ctx):
    append(root, "app/src/transport/transport.ts",
           "\nexport class Planted {\n  constructor(private readonly planted: number) {}\n}\n")
    return files


def plant_import_without_extension(root, files, ctx):
    edit(root, "app/src/transport/memory.ts", r'from "\./transport\.ts"', 'from "./transport"', within="import")
    return files


def plant_failing_app_test(root, files, ctx):
    edit(root, APP_TESTS + "memory.test.ts", r"assert\.equal\(await link\.write\(data\), 3\);",
         "assert.equal(await link.write(data), 4);", within="a write reaches")
    return files


def plant_skipped_app_test(root, files, ctx):
    edit(root, APP_TESTS + "memory.test.ts", r'test\("a read with nothing to read times out"',
         'test.skip("a read with nothing to read times out"', within='test("a read with nothing')
    return files


def plant_fake_importing_protocol(root, files, ctx):
    append(root, FAKE, '\nimport "../src/protocol/status.ts";\n')
    return files


def plant_fake_reaching_protocol_indirectly(root, files, ctx):
    append(root, "app/src/transport/memory.ts", '\nexport { cite } from "../protocol/facts.ts";\n')
    return files


def plant_app_test_file_emptied(root, files, ctx):
    (root / APP_TESTS / "webusb.test.ts").write_bytes(b"")
    return files


def plant_app_test_exiting_early(root, files, ctx):
    edit(root, APP_TESTS + "status.test.ts", r"const TIMEOUT_MS = 100;", "const TIMEOUT_MS = 100;\nprocess.exit(0);",
         within="const TIMEOUT_MS")
    return files


def plant_fake_importing_protocol_in_another_case(root, files, ctx):
    append(root, FAKE, '\nimport "../SRC/Protocol/status.ts";\n')
    return files


def plant_fake_importing_protocol_percent_encoded(root, files, ctx):
    append(root, FAKE, '\nimport "../src/%70rotocol/status.ts";\n')
    return files


def plant_ts_nocheck(root, files, ctx):
    append(root, "app/src/protocol/facts.ts", "\n// @ts-nocheck\n")
    return files


def plant_app_tests_left_out(root, files, ctx):
    return [name for name in files if not (name.startswith(APP_TESTS) and name.endswith(".test.ts"))]


def plant_type_error(root, files, ctx):
    append(root, "app/src/protocol/facts.ts", '\nexport const planted: number = "not a number";\n')
    return files


def plant_hand_edited_fixtures(root, files, ctx):
    edit(root, generate.FIXTURES_OUTPUT, r'bytes: "73 7b 37 7d 0d"', 'bytes: "73 7b 38 7d 0d"', within="export const")
    return files


def plant_unsafe_integer(root, files, ctx):
    edit(root, FACTS, r"value = 0x08F7", "value = 9007199254740993", within=FACT)
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
    ("facts", "a bench fact on a fixture", plant_bench_fact_on_fixture,
     "'../fixtures/status-request.trace' is not one"),
    ("traces", "a recording changed after listing", plant_changed_recording,
     "planted.trace: its bytes do not match"),
    ("traces", "a byte of one hex digit", plant_odd_hex, "'7' is not a byte"),
    ("traces", "a header carrying a host", plant_host_header, "unknown header key 'host'"),
    ("traces", "a recording not listed", plant_unlisted_recording, "unlisted.trace: not listed in SHA256SUMS"),
    ("traces", "a listing with no recording", plant_ghost_listing, "SHA256SUMS lists ghost.trace"),
    ("traces", "a fixture among the recordings", plant_fixture_among_recordings,
     "it is a fixture, and only recordings belong"),
    ("traces", "a recording among the fixtures", plant_recording_among_fixtures,
     "recorded.trace: it is a trace, and only fixtures belong"),
    ("traces", "a stray file among the recordings", plant_stray_among_recordings,
     "session-notes.txt: only recordings, SHA256SUMS and FORMAT.md belong"),
    ("traces", "a stray file among the fixtures", plant_stray_among_fixtures,
     "sketch.bin: only fixtures and README.md belong"),
    ("traces", "FORMAT.md's example broken", plant_broken_example, "its example does not parse"),
    ("generated", "a hand-edited generated file", plant_hand_edited_generated,
     "differs from what tools/generate.py makes"),
    ("facts", "a bench fact on a name with no file", plant_bench_fact_on_missing_name,
     "its trace nonexistent.trace is not in protocol/traces/"),
    ("facts", "a bench fact on the fixture's bare name", plant_bench_fact_on_fixture_name,
     "its trace status-request.trace is not in protocol/traces/"),
    ("facts", "a bench fact on an unlisted recording", plant_bench_fact_on_unlisted,
     "its trace unlisted.trace is not listed in SHA256SUMS"),
    ("facts", "a bench fact on a changed recording", plant_bench_fact_on_changed,
     "its trace planted.trace is not a sound recording"),
    ("traces", "a recording listed twice", plant_duplicate_listing, "lists planted.trace twice"),
    ("traces", "a recording in a subfolder", plant_recording_in_subfolder, "recordings sit directly in"),
    ("traces", "a malformed manifest line", plant_malformed_listing, "not a '<sha256>  <name>.trace' line"),
    ("traces", "FORMAT.md's example as a fixture", plant_example_as_fixture,
     "its example is a fixture, not a recording"),
    ("traces", "a date with a space for its T", plant_date_with_space, "does not read YYYY-MM-DDTHH:MM:SS+HH:MM"),
    ("traces", "a header value that is not printable", plant_unprintable_header, "not printable text"),
    ("generated", "an integer beyond JavaScript's safe ones", plant_unsafe_integer,
     "beyond the integers JavaScript holds exactly"),
    ("reference", "a sentence pasted from the manual", plant_pasted_manual_sentence,
     "docs/README.md:8: shares a run of"),
    ("reference", "an evidence phrase copied into a comment", plant_evidence_in_a_comment,
     "shares a run of"),
    ("reference", "a run of exactly eight words", plant_run_of_eight, "docs/README.md:8: shares a run of 8 words"),
    ("reference", "zero-width spaces inside the words", plant_zero_width_run, "docs/README.md:8: shares a run of"),
    ("reference", "a passage in a UTF-16 file", plant_utf16_run, "docs/notes.txt:1: shares a run of"),
    ("reference", "an evidence-shaped line inside a note", plant_evidence_line_in_a_note,
     "protocol/labpro-facts.toml:"),
    ("reference", "an accented letter in every word", plant_accented_run, "docs/README.md:8: shares a run of"),
    ("reference", "a combining grapheme joiner in every word", plant_joiner_run, "docs/README.md:8: shares a run of"),
    ("reference", "a passage in a UTF-32 file", plant_utf32_run, "docs/notes32.txt:1: shares a run of"),
    ("bench", "the bench script sending a reset", plant_bench_sends_a_reset, "the script sent"),
    ("bench", "the fixture's reply changed", plant_fixture_reply_changed, "status.check_value"),
    ("bench", "the bench tests left out", plant_bench_tests_left_out, "holds no test_*.py"),
    ("bench", "the bench tests skipped", plant_bench_tests_skipped, "unittest reports OK (skipped="),
    ("bench", "a failure that shows a scratch path", plant_bench_failure_showing_a_path,
     "'zzplanted' not found in 'refused: <temp>"),
    ("bench", "the bench script resetting a busy unit", plant_bench_resetting_a_busy_unit,
     "test_armed_and_busy_are_never_reset"),
    ("bench", "--discard resetting a busy unit", plant_discard_resetting_a_busy_unit,
     "test_armed_and_busy_are_never_reset"),
    ("bench", "the CH1 fixture's reply to Command 9 corrupted", plant_ch1_reply_corrupted,
     "test_reads_ch1_as_the_fixture_has_it"),
    ("traces", "a recording whose device line is 17 bytes", plant_short_device_line,
     "a device descriptor is 18 bytes; this one is 17"),
    ("traces", "a recording with its serial unmasked", plant_unmasked_serial, "serial 'ABC12345XY' is not masked"),
    ("traces", "a recording whose device line is of another type", plant_device_line_of_another_type,
     "a device descriptor begins 12 01; this one begins 12 02"),
    ("traces", "a recording whose configuration line disagrees with its total", plant_configuration_total_disagreeing,
     "its total length says 32 bytes, but the line holds 31"),
    ("bench", "the bench script resetting an initializing unit", plant_bench_resetting_an_initializing_unit,
     "test_initializing_is_read_again_until_idle"),
    ("bench", "the bench script taking an --every without bound", plant_bench_every_unbounded,
     "test_every_is_bounded_and_for_is_not"),
    ("bench", "the bench script losing the trace to an error it does not name",
     plant_bench_losing_the_trace_to_an_error, "test_an_unnamed_error_keeps_the_trace_and_goes_on"),
    ("app", "an enum in the app", plant_app_enum, "ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX"),
    ("app", "an import without its .ts", plant_import_without_extension, "ERR_MODULE_NOT_FOUND"),
    ("app", "a failing app test", plant_failing_app_test, "a write reaches the device's end as one piece, copied:"),
    ("app", "a skipped app test", plant_skipped_app_test, "node reports 1 skipped"),
    ("app", "the fake importing the protocol code", plant_fake_importing_protocol,
     "app/test/fake-labpro.ts -> app/src/protocol/status.ts: the fake shares no code"),
    ("app", "the fake reaching the protocol code through another file", plant_fake_reaching_protocol_indirectly,
     "app/test/fake-labpro.ts -> app/src/transport/memory.ts -> app/src/protocol/facts.ts: the fake shares no code"),
    ("app", "the app tests left out", plant_app_tests_left_out, "holds no *.test.ts"),
    ("app", "an app test file emptied", plant_app_test_file_emptied,
     "app/test/webusb.test.ts: node printed no TAP summary"),
    ("app", "an app test file that exits early", plant_app_test_exiting_early,
     "app/test/status.test.ts: node printed no TAP summary"),
    ("app", "the fake importing the protocol code in another case", plant_fake_importing_protocol_in_another_case,
     "app/test/fake-labpro.ts -> app/SRC/Protocol/status.ts: the fake shares no code"),
    ("app", "the fake importing the protocol code percent-encoded", plant_fake_importing_protocol_percent_encoded,
     "app/test/fake-labpro.ts -> app/src/protocol/status.ts: the fake shares no code"),
    ("types", "a @ts-nocheck in the app", plant_ts_nocheck, "holds @ts-nocheck"),
    ("types", "a type error in the app", plant_type_error, "error TS2322"),
    ("types", "an enum in the app", plant_app_enum, "error TS1294"),
    ("types", "a parameter property in the app", plant_parameter_property, "error TS1294"),
    ("generated", "a hand-edited fixtures file", plant_hand_edited_fixtures,
     "app/test/generated/fixtures.ts differs from what tools/generate.py makes of protocol/fixtures/"),
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


def build_generated_mutant(base, ctx):
    """A generator that writes one value wrong, consistently: the file matches the generator,
    so only the round trip through Node can see it."""
    root = copy_files(ctx.files, base / "generated-mutant")
    good = generate.render(labpro_facts.load(root))
    bad = good.replace("value: 2295,", "value: 2296,", 1)
    if bad == good:
        raise RuntimeError("control cannot be planted: no 'value: 2295,' in the generated text")
    (root / generate.OUTPUT).write_bytes(bad.encode("utf-8"))
    mutant = Context(ctx.reference_root, ctx.git_root)
    mutant.render = lambda data: bad
    return check_generated(root, walked_files(root), mutant)


def build_generated_boolean_mutant(base, ctx):
    """A generator that writes true where the TOML has 1, consistently: equal in Python, not to the app."""
    root = copy_files(ctx.files, base / "generated-boolean")
    good = generate.render(labpro_facts.load(root))
    target = '"usb.product_id": Object.freeze({ value: 1,'
    bad = good.replace(target, target.replace("value: 1,", "value: true,"), 1)
    if bad == good:
        raise RuntimeError("control cannot be planted: no usb.product_id with value 1 in the generated text")
    (root / generate.OUTPUT).write_bytes(bad.encode("utf-8"))
    mutant = Context(ctx.reference_root, ctx.git_root)
    mutant.render = lambda data: bad
    return check_generated(root, walked_files(root), mutant)


def build_write_refusals(base, ctx):
    """tools/traces.py's writer must refuse what would not read back as given."""
    report = Report("traces")
    cases = (("a value holding a line break", dict(RECORDING_HEADER, os="planted\n# note: smuggled")),
             ("a value that is not text", dict(RECORDING_HEADER, os=5)))
    for label, header in cases:
        try:
            traces.write("trace", header, [("OUT", 0, b"s")])
        except ValueError as exc:
            report.fail(f"traces.write refused {label}: {exc}")
    return report


def build_run_of_seven(base, ctx):
    """Seven words in a row from the manual are one short of a run, and must pass."""
    root = copy_files(ctx.files, base / "run-of-seven")
    words = words_of(manual_page(root, ctx, 22))[40:47]
    append(root, "docs/README.md", "\nzzplanted " + " ".join(words) + " zzplanted\n")
    return check_reference(root, walked_files(root), ctx)


def build_fixtures_mutant(base, ctx):
    """A generator that writes one fixture byte wrong, consistently: the file matches the generator,
    so only the round trip through Node can see it."""
    root = copy_files(ctx.files, base / "fixtures-mutant")
    good = generate.render_fixtures(generate.fixtures(root))
    bad = good.replace('bytes: "73 7b 37 7d 0d"', 'bytes: "73 7b 38 7d 0d"', 1)
    if bad == good:
        raise RuntimeError("control cannot be planted: no Command 7 in the generated fixtures")
    (root / generate.FIXTURES_OUTPUT).write_bytes(bad.encode("utf-8"))
    mutant = Context(ctx.reference_root, ctx.git_root)
    mutant.render_fixtures = lambda found: bad
    return check_generated(root, walked_files(root), mutant)


def build_hanging_app_test(base, ctx):
    """An app test that never settles in time: the check must fail it by name, and go on."""
    root = copy_files(ctx.files, base / "hanging-app-test")
    append(root, APP_TESTS + "memory.test.ts",
           '\ntest("planted: hangs", async () => {\n  await new Promise((resolve) => setTimeout(resolve, 60000));\n});\n')
    hurried = Context(ctx.reference_root, ctx.git_root)
    hurried.test_timeout = 3
    return check_app(root, walked_files(root), hurried)


def build_hanging_bench_test(base, ctx):
    """A bench test that never ends in time: the check must fail it by name, and go on."""
    root = copy_files(ctx.files, base / "hanging-bench-test")
    edit(root, BENCH + "test_bench.py", r'if __name__ == "__main__":',
         'class Planted(unittest.TestCase):\n    def test_hangs(self):\n        import time\n        time.sleep(60)\n\n\n'
         'if __name__ == "__main__":', within='if __name__')
    hurried = Context(ctx.reference_root, ctx.git_root)
    hurried.test_timeout = 3
    return check_bench(root, walked_files(root), hurried)


def build_types_without_typescript(base, ctx):
    """No typescript installed: the types check must be skipped by name, not passed."""
    root = copy_files(ctx.files, base / "types-without-typescript")
    bare = Context(base / "nowhere", ctx.git_root)
    return check_types(root, walked_files(root), bare)


def build_bench_without_pyusb(base, ctx):
    """No Python with pyusb to be found: the bench check must be skipped by name, not passed."""
    root = copy_files(ctx.files, base / "bench-without-pyusb")
    bare = Context(ctx.reference_root, ctx.git_root)
    bare.pythons = []
    return check_bench(root, walked_files(root), bare)


def build_bench_fact_on_recording(base, ctx):
    """A bench fact naming a sound, listed recording: the bench rule must let it pass."""
    root = copy_files(ctx.files, base / "bench-recording")
    name = plant_recording(root)
    edit(root, FACTS, r'status = "manual"', f'status = "bench"\ntrace = "{name}"', within=FACT)
    return check_facts(root, walked_files(root), ctx)


BUILT_CONTROLS = [
    ("generated", "a generator that writes a wrong value consistently", build_generated_mutant, "fail",
     "round trip: usb.vendor_id loads"),
    ("facts", "a bench fact on a sound, listed recording", build_bench_fact_on_recording, "clean",
     "usb.vendor_id"),
    ("generated", "a generator that writes true for 1, consistently", build_generated_boolean_mutant, "fail",
     "round trip: usb.product_id loads"),
    ("traces", "traces.write given a value holding a line break", build_write_refusals, "fail",
     "refused a value holding a line break"),
    ("traces", "traces.write given a value that is not text", build_write_refusals, "fail",
     "refused a value that is not text"),
    ("reference", "a run of seven words from the manual", build_run_of_seven, "clean", "docs/README.md:"),
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
    ("bench", "no Python with pyusb", build_bench_without_pyusb, "skip",
     "the bench script's tests are not run"),
    ("generated", "a generator that writes a fixture byte wrong, consistently", build_fixtures_mutant, "fail",
     "loads from app/test/generated/fixtures.ts unlike protocol/fixtures/"),
    ("types", "no typescript installed", build_types_without_typescript, "skip", "app/src is not type-checked"),
    ("app", "an app test that hangs", build_hanging_app_test, "fail",
     "app/test/memory.test.ts: did not finish within 3 s"),
    ("bench", "a bench test that hangs", build_hanging_bench_test, "fail",
     "tools/bench/test_bench.py: did not finish within 3 s"),
]


def copy_files(files, destination):
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return destination


def run_controls(files, ctx, require_all):
    print()
    print("Controls: each plants a fault the check named must catch, for the reason named,")
    print("or, where it says so, a sound case the check must pass.")
    missed = skipped = named_skips = cleans = 0
    ctx.files = files
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
        for name, title, build, outcome, expect in BUILT_CONTROLS:
            if build not in built:
                try:
                    built[build] = build(base, ctx)
                except Unplantable as why:
                    built[build] = why
            report = built[build]
            if isinstance(report, Unplantable):
                skipped += 1
                print(f"  SKIP   {name:<9} {title}: not built, {report}")
                continue
            if outcome == "clean":
                wrong = [message for message in report.fails if expect in message]
                if wrong:
                    missed += 1
                    print(f"  MISSED {name:<9} {title}: expected no failure naming {expect!r}; got: {wrong[0]}")
                else:
                    cleans += 1
                    print(f"  passed {name:<9} {title}: no failure names {expect}")
                continue
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
    total = len(CONTROLS) + len(BUILT_CONTROLS)
    caught = total - missed - skipped - named_skips - cleans
    if missed or (skipped and require_all):
        print(f"CONTROLS: FAIL ({caught} caught, {named_skips} skipped as named, {cleans} passed as named, "
              f"{missed} missed, {skipped} not exercised, of {total})")
        return True
    suffix = f"; {skipped} not exercised" if skipped else ""
    print(f"CONTROLS: PASS ({total - skipped} of {total} behaved as named: {caught} caught, "
          f"{named_skips} skipped as named, {cleans} passed as named{suffix})")
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
