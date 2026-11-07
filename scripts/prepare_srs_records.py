"""Capture the initial research and traceability for the SRS preparation run.

One-time preparation helper. Existing notes are never overwritten.
"""
from pathlib import Path
import csv
import io
import json

ROOT=Path(__file__).resolve().parents[1]
DATE='2026-11-07'
NOTES=[
('01-project-problem-and-scope','Project problem and scope',['Project_1_YouTube_MCP.pdf pp. 1-2'],['FR-1','FR-2','FR-3','FR-4','FR-5'],
 'The supplied problem is the effort required to curate focused educational content from distracting YouTube results. It requires an MCP server backed by the official YouTube Data API v3, not a replacement video platform. The five core features are similar videos, similar channels, personalised recommendations, engagement analysis and confirmed playlist creation.',
 'Preserve the source feature IDs in the SRS. Cover all five even if playlist creation is the most visible workflow. Exclude unrelated account mutations and media downloading. The user selected the YouTube topic in this conversation; no topic switch is assumed.',
 ['02-metadata-based-similarity','06-preview-and-human-approval','12-engineering-and-knowledge-workflow']),
('02-metadata-based-similarity','Metadata based similarity',['Project_1_YouTube_MCP.pdf p. 2','https://developers.google.com/youtube/data/reference/rest'],['FR-1','FR-2'],
 'The brief explicitly says there is no related-video or related-channel endpoint and requires locally computed similarity. It suggests TF-IDF, cosine similarity or basic weighted scoring using video/channel metadata.',
 'Specify observable ranking behaviour, seed exclusion, stable tie rules, missing-feature handling and selection reasons. Leave exact weights for design. Similarity is an application estimate and does not establish teaching quality. Consult the policy dependency before enabling live derived processing.',
 ['01-project-problem-and-scope','13-api-policy-dependency']),
('03-authorised-preference-signals','Authorised preference signals',['Project_1_YouTube_MCP.pdf pp. 1-2','https://developers.google.com/youtube/data/reference/rest/v3/videos/list'],['FR-3','FR-4','FR-0.2'],
 'The brief requires recommendations from likes, subscriptions and playlists and excludes watch-history assumptions. The official videos.list method supports authorised myRating retrieval and documents a maximum of 1,000 returned rated videos.',
 'Treat accessible collections as bounded preference evidence. Report collection completeness, deduplicate shared videos and disclose unavailable sources. Do not claim the retrieved set is the complete lifetime account history. Ask for a seed or topic when no usable signals exist.',
 ['05-time-based-analysis','08-oauth-and-secret-handling']),
('04-duration-and-language-constraints','Duration and language constraints',['Project_1_YouTube_MCP.pdf pp. 1-2','https://developers.google.com/youtube/data/reference/rest/v3/videos/list'],['FR-5.1','FR-5.2','FR-5.3','FR-0.1'],
 'The project requires topic, total-duration, maximum-video-length and language constraints. These need precise acceptance semantics. API metadata may omit useful fields, so relevance or search hints alone cannot establish every constraint.',
 'Project choice: interpret total duration as an upper bound; use integer seconds internally; clarify exact-fill requests. Exclude unknown durations, live/upcoming items and unknown language under a strict filter. Report unused time and infeasibility rather than silently relaxing constraints.',
 ['06-preview-and-human-approval','10-test-fixtures-and-error-cases']),
('05-time-based-analysis','Time based analysis without watch history',['Project_1_YouTube_MCP.pdf pp. 1-2','https://developers.google.com/youtube/data/reference/rest/v3/playlistItems','https://developers.google.com/youtube/data/reference/rest/v3/subscriptions'],['FR-4.1','FR-4.2','FR-4.3'],
 'Official playlist-item metadata identifies when an item was added; subscription metadata identifies subscription creation. A video publication timestamp describes the video, not when the user engaged. Available likes do not establish watch time or reliable like-event dates.',
 'Base comparisons on supported timestamps and name the date basis. Define start-inclusive/end-exclusive UTC intervals, missing-date handling and zero-baseline percentages. Distinguish collection composition from actual viewing behaviour. Mean runtime is a property of selected videos, not time watched.',
 ['03-authorised-preference-signals','13-api-policy-dependency']),
('06-preview-and-human-approval','Preview and human approval',['Project_1_YouTube_MCP.pdf pp. 1-2','https://modelcontextprotocol.io/specification/2025-11-25/server/tools'],['FR-5.4','FR-5.5','NFR-03'],
 'The project requires a playlist preview and explicit confirmation before account creation. It specifically requires security testing against untrusted video metadata bypassing confirmation.',
 'Project choice: approve the exact account-bound proposal version through a trusted human control or local approval interaction. Model-provided confirmed=true is insufficient. Bind title, privacy, ordered video IDs and constraints to approval; changes and expiry invalidate it. Treat external descriptions as data.',
 ['04-duration-and-language-constraints','07-playlist-writes-and-partial-failure']),
('07-playlist-writes-and-partial-failure','Playlist writes and partial failure',['https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert','https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert','Project_1_YouTube_MCP.pdf p. 2'],['FR-5.6','FR-5.7','NFR-06'],
 'Playlist creation and item insertion are separate authorised API methods. Both currently cost 50 general quota units per call. A multi-step workflow can partially succeed, and the project brief requires missing-channel handling.',
 'Keep operation IDs, created playlist IDs and insertion progress. Reconcile uncertain write timeouts rather than blindly retrying; report partial/unknown states honestly. Replayed completed operations return the recorded result. Do not automatically delete or silently substitute videos.',
 ['06-preview-and-human-approval','09-quota-buckets-and-budgeting']),
('08-oauth-and-secret-handling','OAuth and secret handling',['https://developers.google.com/identity/protocols/oauth2/native-app','https://developers.google.com/identity/protocols/oauth2','Project_1_YouTube_MCP.pdf p. 2'],['FR-6','NFR-02','NFR-04','NFR-05','NFR-07'],
 'Google documents installed-app authorisation using a browser, PKCE and loopback redirects. Refresh tokens can stop working, and external apps in Testing with YouTube scopes normally receive seven-day refresh tokens.',
 'Request read capability separately from write capability when possible. Store tokens through OS protection, never in chat or the repository. Handle failed refresh with re-authorisation, and provide disconnect and local deletion. OAuth capability does not replace proposal-specific approval.',
 ['06-preview-and-human-approval','13-api-policy-dependency']),
('09-quota-buckets-and-budgeting','Quota buckets and budgeting',['Project_1_YouTube_MCP.pdf p. 2','https://developers.google.com/youtube/data/determine_quota_cost'],['FR-7','NFR-12'],
 'The brief describes a 10,000-unit daily default and requires rejecting over-budget workflows before any call. Current official documentation separates search.list into a 100-call daily bucket while other relevant methods use the 10,000-unit general bucket; resets occur at midnight Pacific Time.',
 'Use a configurable dated cost profile. Estimate bounded pagination, revalidation, writes and retries; reserve every applicable bucket before the first call. Keep local estimates conservative and disclose shared-project usage that is invisible locally. Extra Cloud projects must not be used to evade limits.',
 ['07-playlist-writes-and-partial-failure','10-test-fixtures-and-error-cases']),
('10-test-fixtures-and-error-cases','Test fixtures and error cases',['Project_1_YouTube_MCP.pdf p. 2','SDLC_and_Workflow.pdf pp. 2-3'],['FR-8','NFR-09','NFR-11','SK-06'],
 'The brief requires unit, integration and MCP-driven system tests. Explicit negatives include malformed IDs, private/deleted videos, missing tags, quotaExceeded, youtubeSignupRequired, expired tokens and rate limits. PR CI must use fixtures or mocks; live API testing belongs in a separately budgeted scheduled workflow.',
 'Keep synthetic fixture data and predictable scoring/constraint assertions. Test zero provider calls after failed preflight and zero writes without valid human approval. Do not present planned tests as passed tests. Add regression cases for significant defects.',
 ['09-quota-buckets-and-budgeting','11-mcp-and-agent-skill-contracts']),
('11-mcp-and-agent-skill-contracts','MCP and agent skill contracts',['https://modelcontextprotocol.io/specification/2025-11-25/server/tools','https://agentskills.io/specification','SDLC_and_Workflow.pdf p. 2'],['NFR-01','SK-01','SK-02','SK-03','SK-04','SK-05','SK-06'],
 'MCP tools provide named operations and schemas. Agent Skills use instruction folders containing SKILL.md with YAML frontmatter. A skill is not a distinct MCP protocol primitive. The SDLC requires brain-ingest, brain-refine, brain-query and local-check, while the YouTube brief adds video-to-playlist.',
 'Deliver skills as versioned instructions and document the supported client loading route; expose help resources without claiming automatic compatibility with all clients. Keep stdout reserved for the stdio protocol. Every skill must cite a distilled note and have stage-appropriate evaluations.',
 ['12-engineering-and-knowledge-workflow','06-preview-and-human-approval']),
('12-engineering-and-knowledge-workflow','Engineering and knowledge workflow',['SDLC_and_Workflow.pdf pp. 1-3'],['GOV-01','GOV-02','GOV-03','GOV-04','GOV-05','SK-01'],
 'The SDLC requires a PARA Second Brain, linked notes, index, run log, stage reviews, source-backed ADRs and skills, root AGENTS.md, human-reviewed PRs and visible contributions by every member. SRS requirements must include FR, NFR and SK and connect through issues, PRs, tests, skills and notes.',
 'Maintain knowledge alongside implementation. Attribute AI-authored notes honestly. Local file preparation does not satisfy human authorship, review or merged PR evidence. This run prepares an SRS and research foundation; it does not complete the entire Stage 1 repository/CI deliverable.',
 ['01-project-problem-and-scope','10-test-fixtures-and-error-cases']),
('13-api-policy-dependency','API policy dependency',['https://developers.google.com/youtube/terms/developer-policies','Project_1_YouTube_MCP.pdf pp. 1-2'],['FR-1','FR-2','FR-3','FR-4','NFR-05'],
 'The official developer policy restricts derived metrics and data. The brief requires similarity and aggregated analysis, creating a policy applicability question for live use. Metadata also has refresh/deletion and user-removal obligations.',
 'Record dependency D-02 in the SRS. Obtain instructor/provider clarification before affected live deployment. Do not claim that labelling computed scores alone resolves permission. Continue fixture-based verification without representing it as live evidence.',
 ['02-metadata-based-similarity','05-time-based-analysis','08-oauth-and-secret-handling'])
]

def write_new(path,text):
    if path.exists(): raise FileExistsError(f'Refusing to overwrite existing record: {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')

def fm(rid,kind,title,status,sources,reqs):
    vals={'id':rid,'type':kind,'title':title,'created':DATE,'author':'Codex','status':status,'sources':sources,'requirements':reqs}
    return '---\n'+'\n'.join(f'{k}: {json.dumps(v)}' for k,v in vals.items())+'\n---\n\n'

def main():
    for stem,title,sources,reqs,finding,implication,related in NOTES:
        text=fm('RN-'+stem[:2],'research',title,'distilled',sources,reqs)
        text+=f'# {title}\n\n## Finding\n\n{finding}\n\n## Project implication\n\n{implication}\n\n## Sources\n\n'
        for source in sources:
            text+=f'- {source}'+(' (accessed 7 November 2026)' if source.startswith('https:') else ' (supplied brief)')+'\n'
        text+='\n## Related notes\n\n'+'; '.join('[['+x+']]' for x in related)+'.\n'
        text+='\nIssues and PRs: pending; no external work item is claimed.\n'
        write_new(ROOT/'brain/resources'/f'{stem}.md',text)
    index='# YouTube project Second Brain\n\nEntry point for the Obsidian-compatible vault. Open this `brain` folder as a vault. Research notes were ingested using the repository brain-ingest skill on 7 November 2026. AI authorship is explicit.\n\n## Active project\n\n- [[srs-baseline]]\n- [[2026-11-07-srs-preparation]]\n- [[requirements-preparation-review]]\n\n## Distilled research\n\n'
    index+='\n'.join(f'- [[{n[0]}]]' for n in NOTES)
    index+='\n\n## Structure\n\n`inbox/` is unprocessed material; `projects/` is current work; `areas/` is continuing responsibilities; `resources/` is distilled reference; `archive/` is inactive material. The note schema is `schema.md`; actual operations are in `log.md`.\n\n## Current evidence\n\nSRS preparation is complete locally. Human team details, individual human notes, implementation, CI, GitHub issues/PR review and submission remain pending. No GitHub mutation has been performed by this preparation run.\n'
    write_new(ROOT/'brain/index.md',index)
    baseline=fm('PROJECT-SRS','decision','YouTube SRS baseline','pending-review',['Project_1_YouTube_MCP.pdf pp. 1-2','SDLC_and_Workflow.pdf pp. 1-3'],['FR-1','FR-2','FR-3','FR-4','FR-5','GOV-05'])
    baseline+='''# YouTube SRS baseline

The user selected YouTube and requested the first graded SRS. The user stated team details will be added later. Submission is one document per team, and the topic and SRS cannot be edited afterwards.

## Local artefacts

- Editable source: `docs/requirements/SRS.md` outside the vault.
- Submission candidate: `output/pdf/YouTube_Video_Intelligence_SRS.pdf` outside the vault.
- Traceability register: `docs/requirements/traceability.csv` outside the vault.
- Rebuild source: `scripts/build_srs.py` outside the vault.

## Scope choices

Preserve all five core features. Use a local stdio MCP server with one documented client. Interpret duration as an upper limit and require verifiable language evidence. Summarise video metadata honestly. Use a trusted proposal-specific approval interaction and preserve partial-write state. These are proposed requirements, not implemented behaviour.

## Dependencies and pending work

Resolve D-02 for affected live derived processing. Add team metadata before final submission. Complete repository/CI setup and team review separately. Add actual issue/PR links when available. No submission, review or release is claimed.

Basis: [[01-project-problem-and-scope]], [[04-duration-and-language-constraints]], [[06-preview-and-human-approval]], [[09-quota-buckets-and-budgeting]], [[13-api-policy-dependency]].
'''
    write_new(ROOT/'brain/projects/youtube-mcp/srs-baseline.md',baseline)
    session=fm('AI-2026-11-07-SRS','ai-session','SRS preparation','recorded',['Project_1_YouTube_MCP.pdf pp. 1-2','SDLC_and_Workflow.pdf pp. 1-3'],['GOV-02','GOV-05','SK-01'])
    session+='''# SRS preparation

## Goal

Prepare the YouTube project SRS for the first graded submission while maintaining the Second Brain.

## Outcome

Read both source briefs, researched official API/OAuth/quota/MCP/skill references, prepared an SRS with 46 numbered requirements and 20 planned acceptance scenarios, added source-linked research and a brain-ingest skill, and generated a single submission PDF. Team identity was intentionally deferred at the user's request. This is local preparation, not submission or human approval.

## What worked

Preserving FR-1 to FR-5 made scope coverage explicit. Separating collection timestamps from viewing history avoided unsupported analytics claims. Explicit duration, language, approval and partial-write rules made acceptance tests concrete.

## What failed or needs correction

The handout's quota summary alone is insufficient for the current separate search allowance. Current policy introduces a live derived-data dependency that cannot be established as resolved in this session. No product implementation experiments or API calls were performed.

## Verification

The final verification record is `docs/requirements/SRS_QA.md` outside the vault. It covers PDF page inspection, requirement/test consistency, source links, frontmatter and wikilinks. These document checks do not establish passing product tests or complete Stage 1 delivery.

## Related knowledge

[[srs-baseline]]; [[09-quota-buckets-and-budgeting]]; [[13-api-policy-dependency]]; [[requirements-preparation-review]].

Issues and PRs: pending. Human authorship and human review: pending.
'''
    write_new(ROOT/'brain/projects/youtube-mcp/2026-11-07-srs-preparation.md',session)
    review=fm('REVIEW-REQUIREMENTS-PREPARATION','review','Requirements preparation review','pending-review',['SDLC_and_Workflow.pdf pp. 1-3'],['GOV-01','GOV-02'])
    review+='''# Requirements preparation review

## What worked

The SRS retains the required feature IDs, declares feasible evidence boundaries, and connects requirements to acceptance scenarios and research notes. Research has traceable sources and honest AI authorship.

## What did not work or remains open

Live API policy applicability is unresolved. Team cover information, human-authored notes, reviewed PRs and a CI skeleton are not completed by this document task. None are reported as done.

## What to change next

Have team members review and explain the SRS before the immutable submission; add their cover details; resolve the live-policy dependency with the instructor; create issues and a reviewed SRS PR; then complete the remaining Stage 1 evidence. This is a preparation review, not a claim that Stage 1 has been submitted.

Related: [[srs-baseline]], [[2026-11-07-srs-preparation]], [[12-engineering-and-knowledge-workflow]], [[13-api-policy-dependency]].
'''
    write_new(ROOT/'brain/projects/youtube-mcp/requirements-preparation-review.md',review)
    write_new(ROOT/'brain/log.md','''# Brain run log

## 2026-11-07 SRS preparation

- Workflow: repository brain-ingest skill; performed by Codex.
- Inputs: both supplied PDFs and official technical references accessed on this date.
- Output: 13 distinct distilled research notes, project baseline note, significant AI-session note, requirements-preparation review, index, schema and PARA vault structure.
- Requirement links: FR-1 to FR-8, NFR, SK and GOV families in the SRS and traceability register.
- Result: local records prepared; review and submission pending. No human contribution or GitHub approval is fabricated.

Subsequent operations must append their actual outcome here.
''')
    reqs=json.loads((ROOT/'docs/requirements/requirements.json').read_text())
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(['requirement_id','title','source','acceptance_scenarios','skill','brain_note','issue_url','pr_url','implementation_test','status'])
    for r in reqs:
        rid=r['id']
        if rid.startswith('FR-1'): source='R1 FR-1'; notes='02-metadata-based-similarity';skill='video-to-playlist'
        elif rid.startswith('FR-2'): source='R1 FR-2';notes='02-metadata-based-similarity';skill='local-check'
        elif rid.startswith('FR-3'): source='R1 FR-3';notes='03-authorised-preference-signals';skill='local-check'
        elif rid.startswith('FR-4'): source='R1 FR-4';notes='05-time-based-analysis';skill='local-check'
        elif rid.startswith('FR-5'): source='R1 FR-5';notes='04-duration-and-language-constraints;06-preview-and-human-approval;07-playlist-writes-and-partial-failure';skill='video-to-playlist'
        elif rid=='FR-6':source='R1 OAuth and TQ-4';notes='08-oauth-and-secret-handling';skill='local-check'
        elif rid=='FR-7' or rid=='NFR-12':source='R1 TQ-6;R6';notes='09-quota-buckets-and-budgeting';skill='local-check'
        elif rid.startswith('SK-'):source='R1 product skill;R2 common skills';notes='11-mcp-and-agent-skill-contracts;12-engineering-and-knowledge-workflow';skill={'SK-01':'brain-ingest','SK-02':'brain-refine','SK-03':'brain-query','SK-04':'local-check','SK-05':'video-to-playlist','SK-06':'all applicable skills'}[rid]
        elif rid.startswith('GOV-'):source='R2';notes='12-engineering-and-knowledge-workflow';skill='brain-ingest;brain-refine;brain-query'
        else:source='R1 TQ and security;R2 SE';notes='10-test-fixtures-and-error-cases;11-mcp-and-agent-skill-contracts;13-api-policy-dependency';skill='local-check'
        writer.writerow([rid,r['title'],source,r['verification'],skill,notes,'','','','specified; implementation and evidence pending'])
    write_new(ROOT/'docs/requirements/traceability.csv',stream.getvalue())
    print(f'Captured {len(NOTES)} research notes and {len(reqs)} traceability records')

if __name__=='__main__':main()
