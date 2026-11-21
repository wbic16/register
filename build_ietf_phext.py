#!/usr/bin/env python3
"""Build ietf.phext: the IETF standards corpus as a phext.

Will's One Day Build (2026-11-18, task 25.6.9/8.6.10/6.6.9): "Pull every
http://ietf.org/ standard into an ietf.phext, using the same rules as
MOAT. Entries that have been officially superseded are kept, but
annotated. The goal: an agentic RFC framework that literally knows all
of the Internet standards." Refinements (same morning): organize by
exocortex priority, accessible to all platforms; link each RFC to the
open-source project(s) that implement it (canonical implementation per
standard, for algorithmic composition -- RFC Box, task
34.5.9/7.6.10/6.5.9); capture dependency edges IN the phext (index
edges, normative/informative reference edges extracted from the texts,
implementation edges) with a generated reverse index (cited_by).

Source of truth: ietf-source.json -- one record per RFC (metadata,
MOAT record status/basis, fetch receipts incl. text SHA-256, priority
tier + rule, implementations with per-link basis/evidence, edges,
cited_by). Generated on the build node from rfc-index.xml + fetch log
+ refs extraction + impl_map (gen_source.py); edit that pipeline,
never the .phext.

Layout:
  1.1.1/1.1.1/1.1.1   Home: charter, MOAT classification decision,
                      implementation-layer decision, graph notes,
                      priority map, generated index by tier
  1.1.1/1.1.1/1.1.2   Registry overview (MOAT form)
  1.1.1/1.1.2/1.1.1   Registry, Tier 1 entries
  1.1.1/1.1.2/1.2.1   Registry, Tier 2 entries
  1.1.1/1.1.2/1.3.K   Registry, Tier 3 shard K (K = rfc//1000 + 1)
  1.1.1/1.2.1/1.1.N   RFC N: header (receipts, annotations, edges,
                      implementations) + full text

Texts are read from the corpus dir (default ~/ietf-build, override
--corpus or $IETF_CORPUS_DIR): the raw fetched files live on the build
node (plain-view); this VM holds the built phext. Fetched bytes are
stored verbatim except: (a) phext delimiter bytes are escaped as
[0xNN] markers (count cross-checked against the fetch census), and
(b) non-UTF-8 source bytes are normalized from Latin-1. Both are noted
in the scroll header; the header SHA-256 is always of the original
fetched bytes.

Regenerate:  python3 build_ietf_phext.py [--source S] [--corpus D] [--out P]
Check:       python3 build_ietf_phext.py --check [--out P]
             (rebuilds in memory; prints CURRENT / DRIFT, exit 0/1)
Conventions follow build_tasks_phext.py: the 9 phext delimiters,
coordinates 1-indexed, implode walks sorted coordinates.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]
DELIM_SET = set(LEVEL_BYTES)
DELIM_CHARS = {chr(b) for b in DELIM_SET}

HOME_COORD = "1.1.1/1.1.1/1.1.1"
REGISTRY_COORD = "1.1.1/1.1.1/1.1.2"
REG_T1_COORD = "1.1.1/1.1.2/1.1.1"
REG_T2_COORD = "1.1.1/1.1.2/1.2.1"
LIST_CAP = 60


def reg_t3_coord(rfc):
    return f"1.1.1/1.1.2/1.3.{rfc // 1000 + 1}"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def implode(scrolls):
    """Same state machine as build_tasks_phext.py / build_skills_phext.py."""
    items = sorted(((parse_coord(k), v) for k, v in scrolls.items()))
    out = bytearray()
    state = [1] * 9
    for target, text in items:
        for lvl in range(9):
            while state[lvl] < target[lvl]:
                out.append(LEVEL_BYTES[lvl])
                state[lvl] += 1
                for j in range(lvl + 1, 9):
                    state[j] = 1
        assert tuple(state) == target, (state, target)
        out += text.encode()
    return bytes(out)


def clean(s):
    """Strip phext delimiter chars from generated metadata text."""
    return "".join(ch for ch in str(s) if ch not in DELIM_CHARS)


def lst(nums):
    return ", ".join(str(n) for n in nums) if nums else "--"


def capped(nums, cap=LIST_CAP):
    if len(nums) <= cap:
        return lst(nums)
    return lst(nums[:cap]) + f", ... (+{len(nums) - cap} more in ietf-source.json)"


def subseries_str(e):
    parts = []
    if e["std"]:
        parts.append("STD " + ", ".join(str(x) for x in e["std"]))
    if e["bcp"]:
        parts.append("BCP " + ", ".join(str(x) for x in e["bcp"]))
    if e["fyi"]:
        parts.append("FYI " + ", ".join(str(x) for x in e["fyi"]))
    return "; ".join(parts) if parts else "--"


def escape_text(text, expected_delims, rfc):
    n = 0
    out = []
    for ch in text:
        if ch in DELIM_CHARS:
            out.append(f"[0x{ord(ch):02X}]")
            n += 1
        else:
            out.append(ch)
    assert n == expected_delims, f"RFC {rfc}: escape count {n} != fetch census {expected_delims}"
    return "".join(out)


def refs_of(e, kind):
    return [r["to_rfc"] for r in e["references"] if r["kind"] == kind]


def render_rfc_header(e, src):
    title = clean(e["title"]) if e["title"] else "(not issued)"
    lines = [f"# RFC {e['rfc']} -- {title}", ""]
    lines.append(f"RFC: {e['rfc']}")
    lines.append(f"Title: {title}")
    lines.append(f"Authors: {clean(', '.join(e['authors'])) if e['authors'] else '--'}")
    lines.append(f"Date: {e['date'] or '--'}")
    lines.append(f"Index status: {e['current_status'] or '--'}")
    lines.append(f"Subseries: {subseries_str(e)}")
    meta = []
    if e["stream"]:
        meta.append(f"Stream: {clean(e['stream'])}")
    if e["area"]:
        meta.append(f"Area: {clean(e['area'])}")
    if e["wg"]:
        meta.append(f"WG: {clean(e['wg'])}")
    if meta:
        lines.append(" | ".join(meta))
    if e["page_count"]:
        lines.append(f"Pages: {e['page_count']}")
    lines.append(f"Obsoletes: {lst(e['obsoletes'])}")
    lines.append(f"Obsoleted by: {lst(e['obsoleted_by'])}")
    lines.append(f"Updates: {lst(e['updates'])}")
    lines.append(f"Updated by: {lst(e['updated_by'])}")
    lines.append("Record (MOAT): True / VERIFIED -- record only: existence, "
                 "text identity, index status. The RFC's normative claims "
                 "remain the IETF's assertions, not adjudicated here.")
    if e["superseded"]:
        succ = ", ".join(e["successor_coordinates"])
        lines.append(f"Supersession: SUPERSEDED -- obsoleted by RFC "
                     f"{lst(e['obsoleted_by'])} (receipt: rfc-index.xml). "
                     f"Successor scroll(s): {succ}. This text is kept in "
                     f"full -- MOAT no-pruning: retirement is relocation "
                     f"with a redirect, never deletion.")
    elif e["fetch_status"] == "not_issued":
        lines.append("Supersession: not applicable -- never issued.")
    else:
        lines.append("Supersession: current -- not obsoleted.")
    lines.append(f"Priority: Tier {e['tier']} -- assigned by rule {e['tier_rule']} "
                 f"(table in ietf-source.json). Priority orders the index "
                 f"and registry; it never affects inclusion.")
    # ---- dependency graph
    lines.append("Dependency edges (also in ietf-source.json: edges):")
    lines.append(f"  Index edges: obsoletes [{lst(e['obsoletes'])}]; "
                 f"obsoleted by [{lst(e['obsoleted_by'])}]; "
                 f"updates [{lst(e['updates'])}]; updated by [{lst(e['updated_by'])}]")
    if e["references_extraction"] == "parsed":
        for kind, label in (("normative", "Normative references"),
                            ("informative", "Informative references"),
                            ("unspecified", "References (kind unspecified in source)")):
            nums = refs_of(e, kind)
            if nums:
                lines.append(f"  {label} (from text): {capped(nums)} ({len(nums)} edges)")
    elif e["references_extraction"] == "unparsed":
        lines.append("  Reference edges: UNPARSED -- no References section "
                     "could be located in the served text. Absence of edges "
                     "here is a parser limit, not a claim that this RFC "
                     "cites nothing.")
    else:
        lines.append("  Reference edges: not applicable (no text).")
    cb = e["cited_by"]
    if cb:
        if len(cb) <= LIST_CAP:
            by_kind = {}
            for c in cb:
                by_kind.setdefault(c["kind"], []).append(c["from_rfc"])
            parts = "; ".join(f"{k}: {lst(v)}" for k, v in sorted(by_kind.items()))
            lines.append(f"  Cited by ({len(cb)} edges, reverse index): {parts}")
        else:
            lines.append(f"  Cited by: {len(cb)} reference edges point at this "
                         f"RFC (full reverse index in ietf-source.json: cited_by).")
    # ---- implementation layer
    if e["impl_status"] == "none_identified":
        lines.append("Implementations: NONE IDENTIFIED -- no canonical "
                     "open-source implementation could be identified for "
                     "this standard (recorded explicitly, per MOAT; the "
                     "field is never filled by invention).")
    elif e["impl_status"] == "unmapped":
        lines.append("Implementations: UNMAPPED -- implementation mapping "
                     "not yet attempted for this entry (marked, not "
                     "silently empty).")
    else:
        lines.append(f"Implementations ({e['impl_status']}, rule {e['impl_rule']}):")
        for im in e["implementations"]:
            lines.append(f"  - {im['name']} ({im['role']}) -- {im['repo_url']} "
                         f"-- license {im['license']} -- {im['language']} "
                         f"-- basis {im['basis']}")
            lines.append(f"    evidence: {clean(im['evidence'])}")
    lines.append(f"Source: {e['text_url']}")
    lines.append(f"Fetched: {e['fetched_at']} (build node: {src['built_from']['build_node']})")
    lines.append(f"Index receipt: rfc-index.xml sha256 {src['built_from']['index_sha256']}")
    if e["fetch_status"] == "ok":
        lines.append(f"Text SHA-256 (as fetched): {e['text_sha256']}")
        lines.append(f"Text bytes (as fetched): {e['text_bytes']}")
        notes = []
        if e["delim_bytes"]:
            notes.append(f"{e['delim_bytes']} phext-delimiter byte(s) in the "
                         f"source are stored as [0xNN] markers; the SHA-256 "
                         f"above is of the original fetched bytes")
        if e["utf8"] is False:
            notes.append("source bytes were not valid UTF-8; stored text is "
                         "normalized from Latin-1; the SHA-256 above is of "
                         "the original fetched bytes")
        lines.append(f"Storage notes: {'; '.join(notes) if notes else '--'}")
    lines.append(f"Coordinate: {e['coordinate']}")
    lines.append("")
    return "\n".join(lines)


def render_rfc(e, src, corpus):
    head = render_rfc_header(e, src)
    if e["fetch_status"] == "not_issued":
        body = ("NOT ISSUED -- no document was ever published under this "
                "number. rfc-index.xml carries an rfc-not-issued-entry "
                "placeholder for RFC " + str(e["rfc"]) + " (receipt: the "
                "index entry itself, cross-checked at ingestion). There "
                "is no text to fetch and none is claimed. This scroll "
                "records the gap so the RFC number line in this corpus "
                "is complete and the absence is explicit, per MOAT: an "
                "absent thing is annotated as absent, never silently "
                "dropped.\n")
        return head + "\n" + body
    if e["fetch_status"] != "ok":
        body = ("TEXT NOT AVAILABLE ONLINE -- the RFC Editor does not serve "
                "a plain-text copy of this RFC. Fetch attempted "
                f"{e['fetched_at']}: HTTP {e['http_status']} for "
                f"{e['text_url']} and for the zero-padded variant; the "
                "attempt is recorded in fetch_log.jsonl on the build node. "
                "The record above is verified from the index receipt; the "
                "text is absent and is annotated as absent, per MOAT. "
                f"Formats the index lists for this RFC: "
                f"{', '.join(e['formats']) or '--'}.\n")
        return head + "\n" + body
    path = os.path.join(corpus, e["text_relpath"])
    with open(path, "rb") as f:
        raw = f.read()
    assert hashlib.sha256(raw).hexdigest() == e["text_sha256"], \
        f"RFC {e['rfc']}: corpus file hash != source receipt"
    assert len(raw) == e["text_bytes"]
    text = raw.decode("utf-8") if e["utf8"] else raw.decode("latin-1")
    if e["delim_bytes"]:
        text = escape_text(text, e["delim_bytes"], e["rfc"])
    return head + "\n--- RFC TEXT AS SERVED BY THE RFC EDITOR ---\n\n" + text


def impl_short(e):
    if e["impl_status"] == "none_identified":
        return "impl: none identified"
    if e["impl_status"] == "unmapped":
        return "impl: unmapped"
    names = "; ".join(f"{im['name']} ({im['role']}, {im['basis']})"
                      for im in e["implementations"])
    return f"impl [{e['impl_status']}]: {names}"


def registry_line(e, src):
    if e["fetch_status"] == "not_issued":
        claim = (f"RFC {e['rfc']}: NOT ISSUED -- the RFC Editor's index "
                 f"carries an rfc-not-issued-entry placeholder; no document "
                 f"was ever published under this number")
        ev = (f"evidence: rfc-index.xml rfc-not-issued-entry cross-checked "
              f"at ingestion (index sha256 "
              f"{src['built_from']['index_sha256'][:16]}...); no text "
              f"exists; absence annotated, not silent")
        return " | ".join([f"RFC {e['rfc']}", e["coordinate"],
                           f"claim: {claim}", "True / VERIFIED", ev,
                           f"tier {e['tier']} ({e['tier_rule']})",
                           "not issued", impl_short(e)])
    claim = (f"RFC {e['rfc']}, \"{clean(e['title'])}\" ({e['date'] or 'n.d.'}), "
             f"index status {e['current_status'] or 'UNKNOWN'}")
    ss = subseries_str(e)
    if ss != "--":
        claim += f", {ss}"
    if e["fetch_status"] == "ok":
        ev = (f"evidence: rfc-index.xml entry cross-checked at ingestion "
              f"(index sha256 {src['built_from']['index_sha256'][:16]}...); "
              f"source {e['text_url']}; text sha256 {e['text_sha256']}")
    else:
        ev = (f"evidence: rfc-index.xml entry cross-checked at ingestion "
              f"(index sha256 {src['built_from']['index_sha256'][:16]}...); "
              f"text fetch attempted {e['fetched_at']} -> HTTP "
              f"{e['http_status']} (fetch_log.jsonl, build node "
              f"{src['built_from']['build_node']}); TEXT NOT AVAILABLE ONLINE")
    nrefs = len(e["references"])
    parts = [f"RFC {e['rfc']}", e["coordinate"], f"claim: {claim}",
             "True / VERIFIED", ev, f"tier {e['tier']} ({e['tier_rule']})",
             f"refs: {nrefs} ({e['references_extraction']})",
             f"cited_by: {len(e['cited_by'])}", impl_short(e)]
    if e["superseded"]:
        parts.append(f"SUPERSEDED: obsoleted by RFC {lst(e['obsoleted_by'])} "
                     f"(receipt: rfc-index.xml)")
        parts.append(f"redirect: {', '.join(e['successor_coordinates'])}")
        parts.append(f"event: supersession recorded at ingestion "
                     f"{src['built_from']['fetch_date']}")
    else:
        parts.append("current")
    return " | ".join(parts)


def render_home(src):
    c = src["counts"]
    ec = c["edges"]
    by_tier = {t: [e for e in src["entries"] if e["tier"] == t] for t in (1, 2, 3)}
    lines = [
        "# ietf.phext -- the Internet standards, as a phext",
        "",
        f"Charter (Will, 2026-11-18; task {src['task_coordinate']}): "
        "\"Pull every http://ietf.org/ standard into an ietf.phext, using "
        "the same rules as MOAT. Entries that have been officially "
        "superseded are kept, but annotated. The goal: an agentic RFC "
        "framework that literally knows all of the Internet standards.\" "
        "Refinements (same morning): organize by exocortex priority, "
        "accessible to all platforms; link each RFC to its canonical "
        "open-source implementation(s); capture the dependency graph "
        "in the phext itself, for RFC Box (task 34.5.9/7.6.10/6.5.9).",
        "",
        f"Corpus: {c['total']} RFC-line entries (RFC "
        f"{src['entries'][0]['rfc']} .. RFC {src['entries'][-1]['rfc']}), "
        f"fetched from the RFC Editor on {src['built_from']['fetch_date']} "
        f"(build node: {src['built_from']['build_node']}). Reconciliation "
        f"against rfc-index.xml is exact: {c['issued']} issued RFCs + "
        f"{c['not_issued']} not-issued numbers (index placeholders for "
        f"numbers never published; each kept as an annotated record) = "
        f"{c['total']}. The index's BCP/STD/FYI subseries entries are "
        f"views over these same RFCs, not additional documents. Of the "
        f"issued RFCs: {c['text_ok']} with full text; "
        f"{c['text_unavailable']} whose text the RFC Editor does not "
        f"serve online (records kept, absence annotated); "
        f"{c['superseded']} superseded (kept in full, annotated, with "
        f"redirects); {c['current']} current.",
        f"Index receipt: {src['built_from']['index_url']} sha256 "
        f"{src['built_from']['index_sha256']} (fetched "
        f"{src['built_from']['index_fetched_at']}).",
        "Source of truth: ietf-source.json beside this builder "
        "(build_ietf_phext.py); never hand-edit the .phext.",
        "",
        "## Classification -- the MOAT decision",
        "",
        src["classification_decision"],
        "",
        "## Implementation layer -- basis discipline",
        "",
        src["implementation_decision"],
        "",
        "Implementation coverage by tier (canonical / multiple / "
        "none identified / unmapped):",
    ]
    for t in (1, 2, 3):
        cov = c["impl_coverage"].get(str(t), {})
        lines.append(f"- Tier {t}: canonical {cov.get('canonical', 0)}, "
                     f"multiple {cov.get('multiple', 0)}, "
                     f"none identified {cov.get('none_identified', 0)}, "
                     f"unmapped {cov.get('unmapped', 0)}")
    lines += [
        "",
        "## Dependency graph",
        "",
        src["graph_notes"],
        "",
        f"Edge counts: index edges -- obsoletes {ec['index_obsoletes']}, "
        f"obsoleted_by {ec['index_obsoleted_by']}, updates "
        f"{ec['index_updates']}, updated_by {ec['index_updated_by']}; "
        f"reference edges extracted -- normative "
        f"{ec['references_normative']}, informative "
        f"{ec['references_informative']}, unspecified "
        f"{ec['references_unspecified']}; implementation edges "
        f"{ec['implementations']}. Reference extraction: "
        f"{ec['refs_parsed']} parsed, {ec['refs_unparsed']} unparsed, "
        f"{ec['refs_not_applicable']} not applicable (no text / not issued).",
        "",
        "## Priority map (exocortex tiers)",
        "",
        f"Tier 1 -- what the exocortex directly runs on: {len(by_tier[1])} RFCs.",
        f"Tier 2 -- adjacent infrastructure: {len(by_tier[2])} RFCs.",
        f"Tier 3 -- everything else, complete: {len(by_tier[3])} RFCs.",
        "Priority orders this index and the registry. It never affects "
        "inclusion: every RFC the index lists is in this corpus. Tier "
        "assignment is deterministic (number sets by family, then title "
        "patterns) with hand overrides where judgement lives; the full "
        "table is ietf-source.json:tier_rules and every entry records "
        "the rule that fired.",
        "",
        "## Coordinates",
        "",
        f"- Home: {HOME_COORD} (this scroll)",
        f"- Registry overview: {REGISTRY_COORD}",
        f"- Registry Tier 1: {REG_T1_COORD}; Tier 2: {REG_T2_COORD}; "
        "Tier 3 shards: 1.1.1/1.1.2/1.3.K (K = rfc//1000 + 1)",
        "- RFC n: 1.1.1/1.2.1/1.1.n",
        "",
    ]
    for t, name in ((1, "Tier 1 -- exocortex core"),
                    (2, "Tier 2 -- adjacent infrastructure"),
                    (3, "Tier 3 -- the complete corpus")):
        lines.append(f"## Index -- {name}")
        lines.append("")
        for e in by_tier[t]:
            flags = []
            ss = subseries_str(e)
            if ss != "--":
                flags.append(ss)
            if e["superseded"]:
                flags.append(f"SUPERSEDED -> RFC {lst(e['obsoleted_by'])}")
            if e["fetch_status"] == "not_issued":
                flags.append("NOT ISSUED -- number never published")
            elif e["fetch_status"] != "ok":
                flags.append("TEXT NOT AVAILABLE ONLINE")
            if e["impl_status"] == "canonical":
                canon = [im["name"] for im in e["implementations"]
                         if im["role"] == "canonical"]
                if canon:
                    flags.append(f"impl: {canon[0]}")
            tail = f" [{' | '.join(flags)}]" if flags else ""
            title = clean(e["title"]) if e["title"] else "(not issued)"
            lines.append(f"- RFC {e['rfc']} -- {e['coordinate']} -- "
                         f"{title}{tail}")
        lines.append("")
    return "\n".join(lines)


def render_registry_overview(src):
    c = src["counts"]
    lines = [
        "# Registry -- ietf.phext (MOAT form)",
        "",
        "One entry per RFC: coordinate, one-line claim, status, basis, "
        "evidence pointer, tier + assigning rule, reference-edge and "
        "cited-by counts, implementation summary, and -- for superseded "
        "RFCs -- the annotation, the redirect, and the ingestion event "
        "that recorded the supersession. Entries live by tier:",
        f"- Tier 1: {REG_T1_COORD} ({c['tiers'].get('1', 0)} entries)",
        f"- Tier 2: {REG_T2_COORD} ({c['tiers'].get('2', 0)} entries)",
        f"- Tier 3: 1.1.1/1.1.2/1.3.K ({c['tiers'].get('3', 0)} entries, "
        "sharded by RFC thousands)",
        "",
        f"Population: {c['total']} entries, all True / VERIFIED (record "
        f"fidelity only -- see the Home scroll's classification decision). "
        f"{c['superseded']} carry supersession annotations with redirects; "
        f"each is also a registry event: at ingestion "
        f"({src['built_from']['fetch_date']}) the rfc-index receipt moved "
        f"the record's annotation from current to SUPERSEDED, the record "
        f"itself remaining True / VERIFIED throughout. "
        f"{c['text_unavailable']} entries record text the RFC Editor does "
        f"not serve online; their absence is annotated, never silent. "
        f"{c['not_issued']} entries record numbers the RFC Editor never "
        f"issued (rfc-not-issued-entry placeholders), verified on the "
        f"index receipt alone.",
        "",
        "Implementation links carry their own per-link basis (VERIFIED "
        "only where the ingestion check ran: repo resolves and project "
        "docs name the protocol or an RFC; otherwise ATTRIBUTED). The "
        "registry line shows each link's basis beside its name; the full "
        "evidence pointers live in the scroll headers and "
        "ietf-source.json.",
        "",
        "Status counts by basis: VERIFIED "
        f"{c['total']}. No False / REFUTED entries exist in this corpus by "
        "design: a superseded standard is a true record of a retired "
        "standard, not a refuted claim (Home scroll, classification "
        "decision). Fiction and Unknown do not arise for bibliographic "
        "records checked at ingestion.",
        "",
    ]
    return "\n".join(lines)


def build(source_path, corpus):
    with open(source_path) as f:
        src = json.load(f)
    scrolls = {HOME_COORD: render_home(src),
               REGISTRY_COORD: render_registry_overview(src)}
    reg = {1: [], 2: [], 3: {}}
    for e in src["entries"]:
        line = registry_line(e, src)
        if e["tier"] == 1:
            reg[1].append(line)
        elif e["tier"] == 2:
            reg[2].append(line)
        else:
            reg[3].setdefault(reg_t3_coord(e["rfc"]), []).append(line)
    scrolls[REG_T1_COORD] = ("# Registry -- Tier 1 (exocortex core)\n\n"
                             + "\n".join(reg[1]) + "\n")
    scrolls[REG_T2_COORD] = ("# Registry -- Tier 2 (adjacent infrastructure)\n\n"
                             + "\n".join(reg[2]) + "\n")
    for coord_k, lines_k in sorted(reg[3].items()):
        scrolls[coord_k] = (f"# Registry -- Tier 3 shard {coord_k}\n\n"
                            + "\n".join(lines_k) + "\n")
    for e in src["entries"]:
        scrolls[e["coordinate"]] = render_rfc(e, src, corpus)
    for coord_s, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord_s}: {bad}"
    return implode(scrolls), src


def main():
    args = sys.argv[1:]
    check = "--check" in args

    def opt(name, env, default=None):
        if name in args:
            return args[args.index(name) + 1]
        return os.environ.get(env, default)

    here = os.path.dirname(os.path.abspath(__file__))
    source = opt("--source", "IETF_SOURCE")
    if not source:
        for cand in (os.path.expanduser("~/ietf-build/ietf-source.json"),
                     os.path.join(here, "ietf-source.json")):
            if os.path.exists(cand):
                source = cand
                break
    corpus = opt("--corpus", "IETF_CORPUS_DIR", os.path.expanduser("~/ietf-build"))
    out = opt("--out", "IETF_OUT",
              os.path.join(os.path.dirname(os.path.abspath(source)), "ietf.phext"))
    blob, src = build(source, corpus)
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(out):
            with open(out, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: ietf.phext matches ietf-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: ietf.phext does not match ietf-source.json (rebuilt sha256 {digest})")
        return 1
    with open(out, "wb") as f:
        f.write(blob)
    c = src["counts"]
    print(f"ietf.phext: {c['total']} RFCs + home + registry, "
          f"{len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
