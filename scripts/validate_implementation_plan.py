"""Check planning integrity; this does not run product or live acceptance tests.

Run with the canonical/local compatible Python. PyYAML is needed for note
frontmatter (already available in the inspected planning environment).
Only --write-report mutates a file, and requires an explicit reference date.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'docs/implementation'
PEOPLE = {'Aadyant': 'A', 'Jeswin': 'J', 'Paul': 'P'}


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-report', action='store_true')
    parser.add_argument('--checked-on', help='Explicit YYYY-MM-DD date for a saved report')
    args = parser.parse_args()
    if args.write_report and not args.checked_on:
        parser.error('--write-report requires --checked-on')
    if args.checked_on:
        from datetime import date
        date.fromisoformat(args.checked_on)

    results: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        results.append((name, bool(condition), detail))

    data = json.loads((PLAN / 'tasks.json').read_text(encoding='utf-8'))
    tasks = data['tasks']
    task_map = {t['id']: t for t in tasks}
    expected_ids = {f'{prefix}2-{i:02}' for prefix in PEOPLE.values() for i in range(1, 9)}
    check('Current task register', data['plan_version'] == '2.2' and len(tasks) == len(task_map) == 24 and set(task_map) == expected_ids, '24 unique A2/J2/P2 implementation tasks under governance version 2.2, eight for each member')
    counts = Counter(t['owner'] for t in tasks)
    check('Equal task counts', counts == Counter({person: 8 for person in PEOPLE}), str(dict(counts)))
    totals = {person: [sum(t['hours'][i] for t in tasks if t['owner'] == person) for i in (0, 1)] for person in PEOPLE}
    check('Equal implementation effort arithmetic', all(bounds == [56, 80] for bounds in totals.values()), f'Implementation hours including tests/docs/integration, AI-assisted author verification, handoffs and feedback fixes: {totals}; midpoint 68 each, 33.33% each; centralized lead review/coordination is additional')
    policy = data['review_policy']
    reviewer_matrix = {'Aadyant': [], 'Jeswin': ['Aadyant'], 'Paul': ['Aadyant']}
    check('Lead and own-work reviewer matrix', policy['team_lead'] == 'Aadyant' and policy['teammate_work_requires_lead_review'] is True and policy['eligible_reviewers_by_author'] == reviewer_matrix and policy['teammate_human_approvals_required'] == 1 and policy['do_not_assign_jeswin_or_paul_to_lead_prs'] is True, 'Aadyant reviews teammate work; Jeswin/Paul are not assigned to his PRs')
    check('Human owner review and current-version integrity', all(policy[key] is True for key in ('human_review_required_by_srs','ai_review_does_not_replace_human_review','owner_review_is_not_independent_github_approval','coauthorship_disclosed','material_changes_require_re_review','existing_repository_protections_must_be_respected')) and policy['own_work_review_mode'] == 'chosen_ai_review_plus_recorded_human_owner_review', 'Actual human verification retained; AI findings and owner review are not independent GitHub approval; protections remain')
    expected_scope = {'pull_requests', 'code', 'tests_and_fixtures', 'designs_and_contracts', 'documentation', 'skills', 'brain_notes', 'reports_and_demos', 'stage_and_release_evidence'}
    check('All teammate deliverables reviewed', set(policy['scope']) == expected_scope and set(policy['evidence']) == {'reviewer_identity', 'commit_or_artifact_version', 'actual_decision', 'review_link'}, 'Lead review includes every listed deliverable type with real reviewer/version/decision/link evidence')
    check('Review workload disclosure', 'excludes centralized lead review/coordination' in data['effort_unit'] and 'additional' in policy['lead_review_effort'] and 'pending' in policy['remote_enforcement_status'], 'Equal implementation estimates do not claim equal total workload or existing repository enforcement')
    check('Every task retains actual human review', all(t['eligible_reviewers'] == reviewer_matrix[t['owner']] and t['human_review_responsible'] == 'Aadyant' and t['review_status'] == ('pending_ai_and_human_owner_review' if t['owner']=='Aadyant' else 'pending_lead_human_review') and ('actual recorded human owner review' in t['review_requirement'] if t['owner']=='Aadyant' else 'human lead review by Aadyant' in t['review_requirement']) for t in tasks), 'Own tasks require chosen-AI plus actual recorded owner review; teammate tasks require actual lead review; no invented completion')
    srs_state = data['srs_status']
    check('Submitted SRS status and freeze', srs_state['state']=='submitted_user_reported' and srs_state['baseline_changes_authorized'] is False and srs_state['exact_submission_date'] is None and srs_state['submitted_rendition'] is None, 'User-reported submission recorded without invented date/rendition or SRS editing authority')
    check('Task scope and ownership', all(t['owner'] in PEOPLE and t['id'].startswith(PEOPLE[t['owner']] + '2-') and 0 < t['hours'][0] <= t['hours'][1] and t['deliverable'] and t['paths'] for t in tasks), 'Each task has a real owner, positive range, deliverable and path targets')
    unknown = [(t['id'], dep) for t in tasks for dep in t['depends_on'] + t['integration_requires'] if dep not in task_map or dep == t['id']]
    check('Dependency references', not unknown, f'Prerequisite/integration references: {unknown or "all registered, no self-dependencies"}')
    indegree = {t['id']: len(t['depends_on']) for t in tasks}
    successors: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for dep in task['depends_on']:
            successors[dep].append(task['id'])
    ready = sorted(tid for tid, degree in indegree.items() if degree == 0)
    order = []
    while ready:
        tid = ready.pop(0)
        order.append(tid)
        for successor in successors[tid]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    check('Acyclic implementation prerequisites', len(order) == len(tasks), 'depends_on is acyclic; integration_requires are separately verified cross-component gate obligations, not build prerequisites')

    requirements = json.loads((ROOT / 'docs/requirements/requirements.json').read_text(encoding='utf-8'))
    source = {r['id']: r for r in requirements}
    rows = list(csv.DictReader((PLAN / 'coverage.csv').open(encoding='utf-8', newline='')))
    check('Coverage CSV newline integrity', b'\r\r\n' not in (PLAN / 'coverage.csv').read_bytes(), 'No duplicated carriage returns from Windows newline translation')
    row_ids = [r['requirement_id'] for r in rows]
    check('Exact requirement coverage', len(rows) == len(set(row_ids)) == len(source) == 46 and set(row_ids) == set(source), '46 unchanged numbered requirements, no duplicates/missing/extra IDs')
    check('Requirement text identity', all(r['requirement_title'] == source[r['requirement_id']]['title'] and r['srs_verification'] == source[r['requirement_id']]['verification'] for r in rows), 'Exact source titles and verification strings preserved')
    check('Current coverage task references', all(r['plan_version'] == '2.2' and set(r['task_ids'].split(';')) <= set(task_map) and r['planned_test_or_evidence_paths'] for r in rows), 'Every governance-v2.2 planning row uses registered A2/J2/P2 tasks and planned evidence targets')
    check('Requirement review gates', all('Aadyant reviews all teammate artefacts' in r['review_gate'] and 'recorded human owner review' in r['review_gate'] and 'Jeswin/Paul not assigned' in r['review_gate'] and '19-owner-ai-assisted-review-and-submitted-srs' in r['brain_notes'] for r in rows), 'All 46 rows retain human review while removing teammate assignment to lead PRs')
    check('Coverage owner consistency', all(set(r['primary_owner'].split(';')) <= {task_map[tid]['owner'] for tid in r['task_ids'].split(';')} for r in rows), 'Each stated requirement owner owns at least one mapped task')
    mapped_tasks = {tid for r in rows for tid in r['task_ids'].split(';')}
    check('All tasks traced', mapped_tasks == set(task_map), 'All 24 tasks appear in requirement coverage')
    check('Honest pending evidence', all(r['issue_url'] == r['pr_url'] == 'pending' and 'execution evidence and human review pending' in r['implementation_status'] for r in rows), 'No uncreated Issue/PR, executed test or human review is claimed')
    ats = {at for r in rows for at in r['acceptance_ids'].split(';') if at}
    master = (PLAN / 'MASTER_PLAN.md').read_text(encoding='utf-8')
    check('Acceptance coverage', ats == {f'AT-{i:02}' for i in range(1, 21)} and all(f'| AT-{i:02} |' in master for i in range(1, 21)), 'AT-01 through AT-20 remain mapped with current responsibility')

    team = (PLAN / 'TEAM_WORKPLAN.md').read_text(encoding='utf-8')
    team_tasks = set(re.findall(r'^\| ([AJP]2-\d{2}) \|', team, flags=re.M))
    table_ranges = {tid: [int(low), int(high)] for tid, low, high in re.findall(r'^\| ([AJP]2-\d{2}) \| (\d+)–(\d+) h \|', team, flags=re.M)}
    check('Workplan task/range agreement', team_tasks == set(task_map) and all(table_ranges.get(t['id']) == t['hours'] for t in tasks), 'Human-readable 24-task table matches tasks.json and equal totals')
    role_errors = []
    for person, prefix in PEOPLE.items():
        role = (PLAN / 'roles' / f'{person.upper()}.md').read_text(encoding='utf-8')
        if f'{prefix}2-01–{prefix}2-08' not in role or '56–80' not in role or 'integration' not in role.lower() or 'review' not in role.lower():
            role_errors.append(person)
    check('Role workload agreement', not role_errors, f'Role ranges, engineering/integration/review ownership agree; errors: {role_errors}')
    root_agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    check('Agent coordination and commit rules', all(f'{p}2-01–{p}2-08' in root_agents for p in PEOPLE.values()) and 'commit regularly' in root_agents and 'affected-owner technical input' in root_agents and 'one third' in root_agents and 'team lead and required human reviewer' in root_agents and 'Jeswin and Paul must not be assigned to review Aadyant' in root_agents and 'AI output alone does not satisfy SRS GOV-03' in root_agents, 'Regular commits/implementation ownership and actual human review retained; no teammate review assignment to lead PRs')
    migration = (PLAN / 'TASK_MIGRATION.md').read_text(encoding='utf-8')
    legacy = {f'A{i:02}' for i in range(1, 13)} | {f'{p}{i:02}' for p in ('J', 'P') for i in range(1, 5)}
    check('Retired task migration', set(re.findall(r'^\| ([AJP]\d{2}) \|', migration, flags=re.M)) == legacy, 'All 20 earlier IDs mapped; history and existing authorship not reassigned')

    notes = {}
    for path in (ROOT / 'brain').rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        if text.startswith('---\n'):
            metadata = yaml.safe_load(text.split('---', 2)[1])
            notes.setdefault(path.stem, []).append((path, metadata))
    check('Unique substantive note stems', all(len(entries) == 1 for entries in notes.values()), f'{len(notes)} substantive note stems checked')
    check('Coverage distilled-note links', all(stem in notes and notes[stem][0][1]['status'] == 'distilled' for r in rows for stem in r['brain_notes'].split(';')), 'Every row links existing distilled notes, including current allocation')

    new_notes = [ROOT / 'brain/resources/17-equal-team-allocation.md', ROOT / 'brain/projects/youtube-mcp/2026-11-19-equal-workload-revision.md', ROOT / 'brain/resources/18-team-lead-review-governance.md', ROOT / 'brain/projects/youtube-mcp/2026-11-21-team-lead-review-update.md', ROOT / 'brain/resources/19-owner-ai-assisted-review-and-submitted-srs.md', ROOT / 'brain/projects/youtube-mcp/2026-11-21-own-pr-review-clarification.md']
    required = {'id', 'type', 'title', 'created', 'author', 'status', 'sources', 'requirements'}
    fm_errors = []
    for path in new_notes:
        metadata = yaml.safe_load(path.read_text(encoding='utf-8').split('---', 2)[1])
        if not required <= metadata.keys() or metadata['author'] != 'Codex' or metadata['type'] not in {'research', 'decision', 'ai-session', 'review'} or metadata['status'] not in {'distilled', 'recorded', 'pending-review'} or not metadata['sources'] or not metadata['requirements']:
            fm_errors.append(path.name)
    check('New note authorship/frontmatter', not fm_errors, f'Required schema/sources/requirements and honest Codex authorship; errors: {fm_errors}')

    paths = [*PLAN.rglob('*.md'), *(ROOT / 'docs/adr').glob('*.md'), *new_notes, ROOT / 'AGENTS.md', ROOT / 'brain/index.md', ROOT / 'brain/resources/15-implementation-boundaries-and-contracts.md', ROOT / 'brain/projects/youtube-mcp/2026-11-16-implementation-master-plan.md']
    link_errors, wiki_errors, fence_errors = [], [], []
    for path in paths:
        content = path.read_text(encoding='utf-8')
        if len(re.findall(r'^```', content, flags=re.M)) % 2:
            fence_errors.append(path.name)
        for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)', content):
            target = target.strip().strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            local = unquote(target.split('#', 1)[0])
            if not (path.parent / local).resolve().exists():
                link_errors.append(f'{path.relative_to(ROOT)} -> {target}')
        for target in re.findall(r'\[\[([^\]]+)\]\]', content):
            stem = target.split('|', 1)[0].split('#', 1)[0]
            if stem not in notes:
                wiki_errors.append(f'{path.relative_to(ROOT)} -> {stem}')
    check('Local Markdown links', not link_errors, f'{len(paths)} Markdown files checked; broken: {link_errors}')
    check('Wikilinks', not wiki_errors, f'Broken new/current/historical-supersession links: {wiki_errors}')
    check('Markdown fences', not fence_errors, f'Balanced code/diagram fences; errors: {fence_errors}; diagrams not renderer-tested')
    adr_errors = []
    adrs = list((ROOT / 'docs/adr').glob('*.md'))
    for path in adrs:
        content = path.read_text(encoding='utf-8')
        cited = []
        for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)', content):
            resolved = (path.parent / target).resolve()
            if resolved.stem in notes and any(resolved == p.resolve() and meta['status'] == 'distilled' for p, meta in notes[resolved.stem]):
                cited.append(resolved)
        if not cited:
            adr_errors.append(path.name)
    check('ADR distilled basis', len(adrs) == 8 and not adr_errors, f'Eight ADRs cite distilled notes; errors: {adr_errors}')

    active = [ROOT / 'AGENTS.md', PLAN / 'MASTER_PLAN.md', PLAN / 'CONTRACTS.md', PLAN / 'TEAM_WORKPLAN.md', *(PLAN / 'roles').glob('*.md'), *adrs]
    stale = []
    patterns = ['owns most complex', 'own the bulk', 'smaller, substantive contributions', 'Aadyant remains the critical path', 'analytics/presentation; corresponding unit tests', 'rotating reviews', 'Rotate reviews and coordination', 'rotate reviews/phase coordination', "Jeswin's is Paul", "review Paul's critical invariants", 'review another track']
    for path in active:
        content = path.read_text(encoding='utf-8')
        for pattern in patterns:
            if pattern in content:
                stale.append(f'{path.relative_to(ROOT)}: {pattern}')
        for line_no, line in enumerate(content.splitlines(), 1):
            if re.search(r'\b[AJP]\d{2}\b', line) and not any(word in line.lower() for word in ('retired', 'old sequence', 'replaces', 'earlier', 'historical')):
                # Mermaid internal node identifiers are not task assignments.
                if not re.match(r'\s+[A-Z]\d{2}(?:\[|\s)', line) and not re.search(r'--> [A-Z]\d{2}', line):
                    stale.append(f'{path.relative_to(ROOT)}:{line_no}: retired ID in active instruction')
    check('No stale active allocation', not stale, f'Current docs/roles/ADRs checked; historical allocation remains only with supersession context; errors: {stale}')

    preservation = json.loads((PLAN / 'protected-baseline-2026-11-19.json').read_text(encoding='utf-8'))
    changed = [name for name, digest in preservation['sha256'].items() if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    check('SRS/source/output preservation', not changed, f'{len(preservation["sha256"])} pre-revision files compared by SHA-256; changed: {changed}')

    failed = [name for name, ok, _ in results if not ok]
    summary = {'checks': len(results), 'passed': len(results) - len(failed), 'failed': failed, 'task_counts': dict(counts), 'hours': totals, 'topological_order_example': order}
    if args.write_report:
        report = '# Implementation plan integrity checks\n\n'
        report += f'Plan/governance version {data["plan_version"]} · Checked {args.checked_on} · Author: Codex\n\n'
        report += 'This report supersedes earlier planning reports. It verifies implementation-allocation/review-policy/document integrity only: **no product tests, actual CI/live API runs, human review or release are claimed**. Matching implementation estimates are not measured equal productivity or equal total workload; centralized lead-review/coordination is additional. The user reported SRS submission; the baseline is frozen.\n\n'
        report += '| Check | Observed result | Evidence |\n| --- | --- | --- |\n'
        for name, ok, detail in results:
            report += f'| {name} | {"PASS" if ok else "FAIL"} | {detail.replace("|", "/")} |\n'
        report += '\nReproduce with the canonical/local compatible Python and PyYAML: `python scripts/validate_implementation_plan.py`. For a new dated report use `--write-report --checked-on YYYY-MM-DD`. The preservation reference is [protected-baseline-2026-11-19.json](protected-baseline-2026-11-19.json); [tasks.json](tasks.json) and [coverage.csv](coverage.csv) remain planning data.\n\n'
        report += 'Manual scope review: each member retains implementation/tests/docs/integration and feedback fixes. Aadyant reviews teammate work; his own workflow uses chosen-AI findings plus his actual recorded human owner review, without assigning Jeswin/Paul or claiming independent GitHub approval. SRS requirements, algorithms, API-only boundary and playlist human approval remain unchanged. Earlier records remain historical.\n\n'
        report += 'Pending: dependency lock/client/native proof, D-02, actual credentials/runner/quota/review-enforcement configuration, implementation/performance/live tests, actual PR/CI/human-review evidence and later-stage release. SRS submission is user-reported; exact date/rendition not supplied. The SDLC brief page 2 was checked for human-review wording; API/SDK facts remain dated 16 November. No environment installation was performed.\n'
        (PLAN / 'PLAN_QA.md').write_text(report, encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if failed:
        for name, ok, detail in results:
            if not ok:
                print(f'{name}: {ascii(detail)}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(run())
