#!/usr/bin/env python3
"""Regenerate the index block in findings/README.md from each finding's frontmatter.

Also validates the tree: unique ids, known statuses, resolvable cross-links, and
that a file's directory matches its declared status.

    tools/findings-index.py            # rewrite the index, report problems
    tools/findings-index.py --check    # report only, exit 1 if anything is wrong
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "findings"
README = FINDINGS / "README.md"
STATUSES = ["verified", "unverified", "refuted"]
BEGIN, END = "<!-- BEGIN INDEX -->", "<!-- END INDEX -->"

BLURB = {
    "verified": "Survived a deliberate attempt to falsify it.",
    "unverified": "Measured once. Not yet re-tested against a falsification attempt. "
                  "Each file names the test that would close it.",
    "refuted": "Tested and found false. Kept because each one is still reachable by "
               "plausible reasoning, and because acting on it costs real time.",
}


def parse_frontmatter(path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise SystemExit(f"{path}: no frontmatter")
    meta, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        km = re.match(r"^(\w+):\s*(.*)$", line)
        if km:
            key, raw = km.group(1), km.group(2).strip()
            if raw.startswith("[") and raw.endswith("]"):
                meta[key] = [v.strip().strip('"').strip("'")
                             for v in raw[1:-1].split(",") if v.strip()]
            else:
                meta[key] = raw.strip('"').strip("'")
        elif key and line.startswith(("  ", "\t")):
            meta[key] = f"{meta[key]} {line.strip()}".strip()
    return meta


def collect():
    out = []
    for status in STATUSES:
        for path in sorted((FINDINGS / status).glob("*.md")):
            meta = parse_frontmatter(path)
            meta["_path"] = path
            meta["_dir"] = status
            out.append(meta)
    return out


def validate(findings):
    problems = []
    by_id = {}
    for f in findings:
        fid = f.get("id")
        if not fid:
            problems.append(f"{f['_path'].name}: no id")
            continue
        if fid in by_id:
            problems.append(f"duplicate id {fid}: {by_id[fid]['_path'].name} and {f['_path'].name}")
        by_id[fid] = f
        if f.get("status") != f["_dir"]:
            problems.append(f"{f['_path'].name}: status {f.get('status')!r} but sits in {f['_dir']}/")
        if not f.get("title"):
            problems.append(f"{f['_path'].name}: no title")

    for f in findings:
        for field in ("see_also", "replaced_by"):
            for ref in f.get(field, []):
                if ref not in by_id:
                    problems.append(f"{f['_path'].name}: {field} -> unknown id {ref!r}")
        for target in re.findall(r"\]\((\.\./[^)]+|[0-9][^)]*\.md)\)", f["_path"].read_text()):
            if not (f["_path"].parent / target).resolve().exists():
                problems.append(f"{f['_path'].name}: broken link -> {target}")
    return problems, by_id


def render(findings):
    lines = [BEGIN, ""]
    for status in STATUSES:
        group = [f for f in findings if f["_dir"] == status]
        lines += [f"### {status} ({len(group)})", "", BLURB[status], ""]
        for f in group:
            link = f"{status}/{f['_path'].name}"
            lines.append(f"- **[{f['id']}]({link})** — {f['title']}")
            if f.get("supersedes"):
                lines.append(f"  - supersedes: {f['supersedes']}")
            if f.get("replaced_by"):
                lines.append(f"  - replaced by: {', '.join(f['replaced_by'])}")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def main():
    check_only = "--check" in sys.argv
    findings = collect()
    problems, _ = validate(findings)
    for p in problems:
        print(f"PROBLEM: {p}", file=sys.stderr)

    if not check_only:
        text = README.read_text()
        if BEGIN not in text or END not in text:
            raise SystemExit(f"{README}: missing {BEGIN} / {END} markers")
        new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), render(findings), text, flags=re.S)
        README.write_text(new)
        print(f"wrote {README.relative_to(ROOT)}: {len(findings)} findings", file=sys.stderr)

    counts = {s: sum(1 for f in findings if f["_dir"] == s) for s in STATUSES}
    print(" ".join(f"{s}={counts[s]}" for s in STATUSES), file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
