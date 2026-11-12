"""Condense the IEEE SRS presentation while preserving every numbered requirement."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import re
from docx import Document
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.table import Table

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/docx/YouTube_Video_Intelligence_SRS_IEEE.docx'
DEST=ROOT/'output/docx/YouTube_Video_Intelligence_SRS_IEEE_Compact.docx'
TMP=ROOT/'tmp/srs-compact'

def main():
    TMP.mkdir(parents=True,exist_ok=True)
    originals=[SOURCE]+[p for p in (ROOT/'output/pdf').glob('*.pdf') if not p.stem.endswith('_Compact')]
    snapshot={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    (TMP/'preservation.json').write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
    d=Document(SOURCE)
    requirements=json.loads((ROOT/'docs/requirements/requirements.json').read_text())
    source_tables=list(d.tables)
    # Keep the actual template headings and numbering; tighten their paragraph rhythm.
    for name,size,before,after in [('Heading 1',16,12,6),('Heading 2',13,8,4),('Heading 3',12,6,3),('TOCEntry',16,4,6)]:
        s=d.styles[name];s.font.size=Pt(size)
        s.paragraph_format.space_before=Pt(before);s.paragraph_format.space_after=Pt(after)
        s.paragraph_format.keep_with_next=True
    for name in ['toc 1','toc 2']:
        s=d.styles[name];s.font.size=Pt(11)
        s.paragraph_format.space_before=Pt(0);s.paragraph_format.space_after=Pt(0)
        s.paragraph_format.line_spacing=Pt(11)
    # The body remains 12-point Times. Compact verification metadata is still readable.
    for p in d.paragraphs:
        if p.style.name=='Normal':
            p.paragraph_format.space_after=Pt(4)
        if p.text.startswith('Verification:'):
            p.paragraph_format.space_after=Pt(4)
            p.paragraph_format.line_spacing=Pt(11)
            for r in p.runs:r.font.size=Pt(10.5)
        elif re.match(r'^(FR-|NFR-|SK-|GOV-)',p.text):
            p.paragraph_format.space_after=Pt(2)
        if p.style.name=='TOCEntry' and p.text in ['Revision History','Appendix B: Analysis Models','Appendix C: To Be Determined List']:
            p.paragraph_format.page_break_before=False
        if p.text=='9 November 2026' and p.style.name=='ByLine':p.text='12 November 2026'
    def replace(p,text,boldlead=None):
        p.clear()
        if boldlead:p.add_run(boldlead).bold=True
        p.add_run(text)
        p.paragraph_format.space_after=Pt(4)
        return p
    def remove(element):
        parent=element.getparent()
        if parent is not None:parent.remove(element)
    # Condense explanatory prose; numbered requirements are never matched here.
    replacements={
        'This Software Requirements Specification defines version': 'This SRS defines version 1.0 of the YouTube Video Intelligence MCP Server for Team Random Stuff. It specifies required product behaviour, interfaces, quality, skills and acceptance evidence. The submitted topic and requirements form the fixed baseline; implementation and test results are separate deliverables.',
        'Shall denotes a mandatory': 'Shall denotes a mandatory obligation. FR, NFR, SK and GOV identify functional, quality, skill and engineering requirements; AT identifies acceptance scenarios. All numbered requirements and all system features have mandatory High priority unless a condition is stated. Requirement IDs remain stable.',
        'The instructor and reviewers should read': 'Reviewers should read Sections 1-2 for scope, Sections 3-5 for interfaces and behaviour, Section 6 for skills, engineering and verification, and Appendices A-C for terminology, models and open items. Developers and testers shall use the numbered requirements and their verification links.',
        'Learners use YouTube to study': 'Learners need focused educational playlists without manually filtering distracting content, evaluating creators and checking runtimes. This local MCP server connects an AI client to the official YouTube Data API v3 for discovery, metadata-based similarity, personalised recommendations, collection analysis and constrained playlist creation after explicit human confirmation.',
        'The baseline excludes scraping': 'Excluded: scraping/unofficial APIs, video/audio downloads, arbitrary transcript retrieval, watch history, playback, uploads, comments, likes/subscription changes, and editing/deleting existing playlists. A hosted service, custom web application, model training and support for every AI client are not required. Summaries use available API metadata and identify that evidence basis.',
        'The supplied project statement and common SDLC': 'Scope authorities are [R1] and [R2]. Technical references below were consulted on 7 November 2026. This document follows the teaching assistants\' Karl E. Wiegers SRS template; its permission notice is retained.',
        'This is a new local integration': 'The product is a new local integration used by an existing AI client. The server owns validation, metadata processing, quota/proposal state and write safeguards. Google/YouTube provide identity, consent, metadata and playlist operations. Appendix B shows the system boundary and lifecycle.',
        'The performance reference is': 'Performance tests use the NFR-08 reference machine: at least four CPU cores and 8 GB RAM. No special hardware or GPU is required; client/runtime and dependency versions are design selections.',
        'Use only the official YouTube Data API': 'Use only YouTube Data API v3 through a replaceable provider. Compute similarity locally from metadata; assume neither watch history nor related-video/channel endpoints. CI uses fixtures; extra Cloud projects shall not evade quotas. Only approved new-playlist creation and item insertion are in scope.',
        'Deliver a setup guide': 'Deliver versioned Markdown/client help for setup, connection, consent/privacy, feature examples, approval, limits and recovery. Developer documentation covers MCP schemas/resources, provider interfaces and tests. GOV-04 governs OpenAPI documentation only if a REST interface is introduced.',
        'The existing AI client provides': 'The AI client accepts identifiers or natural-language goals and displays source links, durations, reasons, errors and the exact playlist proposal. Approval uses a trusted client control or separate local human interaction. Client-specific screen design is documented during implementation.',
        'The product uses standard operating-system': 'Use standard host process, disk, protected credential storage, browser and network facilities. No sensors, actuators, specialist peripherals or direct device protocols are required.',
        'The YouTube provider exchanges': 'The provider exchanges validated IDs and structured metadata; tokens stay in protected local storage. Proposals, quota and operation records are account-scoped. SKILL.md workflows are instructions loaded by the selected client, not a new MCP primitive.',
        'The client launches the MCP server': 'The client launches the local MCP process and exchanges structured messages over stdio; diagnostics use stderr. Google OAuth/API traffic uses HTTPS and the consent callback uses loopback only. No public listener, email or FTP service is required. See FR-8 and NFR-02/07/09.',
        'Each feature below is required': 'All features below are mandatory. The concise response sequences supplement the binding numbered requirements; shared error handling applies throughout.',
        'Worked constraint example:': 'Example: a two-hour limit is at most 7,200 seconds, with each item at most 1,200 seconds for a 20-minute cap. A 1,201-second item fails. A 6,420-second proposal reports 107 minutes used and 13 unused; unknown metadata cannot prove compliance.',
        'Performance thresholds apply': 'Timing targets apply to local fixtures. Report model, network and OAuth latency separately. Quota configuration remains dated and changeable.',
        'The product does not control physical': 'There is no physical equipment control or claimed safety certification. Account/data safeguards are explicit approval (FR-5.5), revalidation (FR-5.6), duplicate/partial-write recovery (FR-5.7, NFR-06) and privacy controls. Metadata relevance does not guarantee factual or teaching quality.',
        'Correctness of constraints': 'Correct constraints, human approval and privacy take precedence over ranking breadth and latency. Required attributes are reliability, usability, maintainability and repeatable testing; interoperability is defined in NFR-01.',
        'Each skill is a versioned directory': 'Each skill is a versioned SKILL.md directory with valid name/description frontmatter, inputs, invocation conditions, workflow, outputs and failure handling. It cites a distilled note and cannot override server checks or approval.',
        'The following catalogue defines': 'The acceptance catalogue below defines planned evidence. Requirement-level verification links identify the applicable cases; product test execution is not claimed.',
        'Tests are planned, not executed': 'Acceptance requires passing evidence for every applicable mandatory requirement. Record failures and external blocks explicitly. Approval bypass, secret disclosure, cross-account access or duplicate writes block release. Significant defects require regression tests; blocked cases are never marked passed.',
        'Brain note numbers identify': 'GOV-05 requires the maintained requirement-to-issue-to-PR-to-test-to-skill-to-note matrix. Add actual links as work is created; missing links remain pending. Requirement IDs and AT references in this SRS provide the baseline mapping.',
        'These conceptual models explain': 'These conceptual models show the boundary and required playlist lifecycle; they do not prescribe implementation technology.',
        'In Figure B2,': 'Changed/expired proposals need fresh approval. Revalidate before writes, reconcile uncertain outcomes and return recorded results on replay (FR-5.4 to FR-5.7).',
        'Core information objects': 'Core information records use the following fields; unknown metadata remains unknown and private records are account-bound.',
        'The following items are tracked': 'These open items require recorded decisions. They do not make mandatory features optional or permit silent changes to the submitted scope.'
    }
    descriptions=[];sequences=[];current_feature=None;mode=None
    for p in list(d.paragraphs):
        if p.style.name=='Heading 2' and p.text in ['Similar Videos','Similar Channels','Personalised Recommendations','Engagement Analysis','Constrained Playlist Creation','Authorisation and Account Management','Quota Budgeting','Input Validation Coverage and Errors']:
            current_feature=p.text
        if p.style.name=='Heading 3':mode=p.text
        if current_feature and mode=='Stimulus/Response Sequences' and p.style.name=='Normal' and p.text[:1].isdigit():
            sequences.append((current_feature,p))
        if p.style.name=='Normal' and p.text.startswith(('The product is a Model Context Protocol server connected','The learner interacts with an existing AI client.')):
            remove(p._p);continue
        if p.style.name=='Normal':
            for prefix,value in replacements.items():
                if p.text.startswith(prefix):replace(p,value);break
    flows={
        'Similar Videos':'Input video URL/ID and limit -> validate and reserve quota -> retrieve seed/candidates -> rank distinct videos with reasons, or return a typed availability/data error.',
        'Similar Channels':'Input channel URL/handle/ID -> resolve and compare bounded metadata samples -> return distinct ranked channels with evidence and limitations.',
        'Personalised Recommendations':'Grant read consent -> retrieve accessible likes/subscriptions/playlists -> return explained recommendations and coverage; request a seed if no usable signals exist.',
        'Engagement Analysis':'Select collections and periods -> use supported event timestamps -> return counts, duration statistics and valid comparisons with denominators and missing-data limits.',
        'Constrained Playlist Creation':'Specify constraints -> preview a compliant proposal -> reject, revise or approve the exact version -> recheck and create -> return the URL and actual completed/partial/unknown state. Rejection makes no writes.',
        'Authorisation and Account Management':'Request private data/write access -> browser consent -> protect/refresh tokens. On expiry or revocation, guide re-authorisation; disconnect clears local account data and attempts revocation.',
        'Quota Budgeting':'Request a workflow -> estimate/reserve all applicable buckets -> reject before calls if insufficient -> account for attempts and release unused reservations.',
        'Input Validation Coverage and Errors':'Receive inputs -> validate/normalise before calls -> disclose pagination and inaccessible data -> return stable, secret-free errors with safe next actions.'
    }
    first=set()
    for feature,p in sequences:
        if feature not in first:replace(p,flows[feature]);first.add(feature)
        else:remove(p._p)
    # Keep the full bibliography but omit explanatory annotations repeated elsewhere.
    references={
        'R1':'YouTube Video Intelligence MCP Server project statement. Supplied Project_1_YouTube_MCP.pdf, pp. 1-2.',
        'R2':'AI-Assisted SDLC. Supplied SDLC_and_Workflow.pdf, pp. 1-3.',
        'R3':'Google. YouTube Data API reference. https://developers.google.com/youtube/data/reference/rest',
        'R4':'Google. Videos list. https://developers.google.com/youtube/data/reference/rest/v3/videos/list',
        'R5':'Google. PlaylistItems and Subscriptions resources. https://developers.google.com/youtube/data/reference/rest/v3/playlistItems ; https://developers.google.com/youtube/data/reference/rest/v3/subscriptions',
        'R6':'Google. Quota calculator. https://developers.google.com/youtube/data/determine_quota_cost',
        'R7':'Google. OAuth for desktop apps. https://developers.google.com/identity/protocols/oauth2/native-app',
        'R8':'Google. OAuth token expiry. https://developers.google.com/identity/protocols/oauth2',
        'R9':'Google. Playlist and item creation. https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert ; https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert',
        'R10':'MCP specification 2025-11-25, tools and related sections. https://modelcontextprotocol.io/specification/2025-11-25/server/tools',
        'R11':'Agent Skills specification. https://agentskills.io/specification',
        'R12':'Google. YouTube Developer Policies, III.E.4. https://developers.google.com/youtube/terms/developer-policies'
    }
    for p in d.paragraphs:
        match=re.match(r'^\[(R\d+)\]',p.text)
        if match:
            replace(p,references[match[1]],'['+match[1]+'] ')
            p.paragraph_format.space_after=Pt(3)
            for r in p.runs:r.font.size=Pt(11)
    # Replace verbose repeated-record tables with full-width labelled records.
    def labelled_records(t,skip_header=True):
        rows=t.rows[1:] if skip_header else t.rows
        for row in rows:
            vals=[c.text for c in row.cells]
            p=Paragraph(OxmlElement('w:p'),t._parent);t._tbl.addprevious(p._p);p.style=d.styles['Normal']
            p.paragraph_format.space_after=Pt(4);p.paragraph_format.keep_together=True
            p.add_run(vals[0]+(' ' if vals[0].endswith(('.',':')) else '. ')).bold=True;p.add_run(' '.join(vals[1:]))
        remove(t._tbl)
    # Functions, user classes, dependencies, interfaces, rules, stages and data objects.
    for index in [1,2,3,4,5,6,11]:labelled_records(source_tables[index])
    # The detailed traceability register is maintained separately under GOV-05.
    remove(source_tables[9]._tbl)
    # Preserve all source testing obligations in a concise labelled paragraph per level.
    labelled_records(source_tables[8])
    # Pair acceptance scenarios in a compact repeated-record matrix.
    old=source_tables[7]
    original_rows=[[c.text for c in row.cells] for row in old.rows[1:]]
    focus=[
        'MCP connection, schemas, resources and stdout integrity.',
        'Video rankings, seed/duplicate exclusion, ties and missing tags.',
        'Channel resolution and explainable distinct rankings.',
        'All preference sources, sparse data and pagination.',
        'Analysis arithmetic, period boundaries and unavailable dates.',
        'Constrained preview, approval and exact creation workflow.',
        'Constraint boundaries, unknown metadata and infeasibility.',
        'Missing, declined, expired, changed, replayed or wrong-account approval; no writes.',
        'Partial writes, restart, timeout reconciliation and replay.',
        'Malformed inputs, unsupported hosts and unavailable content.',
        'Expired/revoked tokens, failed refresh, denied scopes, missing channel.',
        'Metadata injection and model-forged approval are rejected.',
        'Bucket preflight before any call and concurrent reservations.',
        'Least privilege, credentials, isolation, redaction, retention and deletion.',
        'Caps, pagination, quota accounting, reset and restart.',
        'Rate limits, timeouts, provider faults and bounded retries.',
        'NFR-08 offline performance benchmark.',
        'Skill evaluations, note/link/schema validation and offline CI.',
        'Documentation, selected client and live skill walkthroughs.',
        'Design, plan, ADR, review, traceability and release evidence.'
    ]
    new=d.add_table(rows=1,cols=4)
    new._tbl.tblPr.clear()
    for child in old._tbl.tblPr:new._tbl.tblPr.append(deepcopy(child))
    margins=new._tbl.tblPr.find(qn('w:tblCellMar'))
    if margins is not None:
        for edge in ['top','bottom']:
            value=margins.find(qn('w:'+edge))
            if value is not None:value.set(qn('w:w'),'50')
    new.autofit=False
    for cell,txt in zip(new.rows[0].cells,['ID','Acceptance focus','ID','Acceptance focus']):cell.text=txt
    for i in range(10):
        cells=new.add_row().cells
        for cell,txt in zip(cells,[original_rows[i][0],focus[i],original_rows[i+10][0],focus[i+10]]):cell.text=txt
    for ri,row in enumerate(new.rows):
        for cell,width in zip(row.cells,[0.53,2.82,0.53,2.82]):cell.width=Inches(width)
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(1);p.paragraph_format.line_spacing=1
                for r in p.runs:
                    r.font.size=Pt(10.5)
                    if ri==0:r.bold=True
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    new.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    old._tbl.addprevious(new._tbl);remove(old._tbl)
    for p in d.paragraphs:
        if p.text.startswith('TQ-1 Unit.'):
            p.paragraph_format.space_before=Pt(3)
    # Compact glossary and open-items tables, keeping all entries and their semantics.
    for t in [source_tables[10],source_tables[12]]:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(1);p.paragraph_format.line_spacing=1
                    for r in p.runs:r.font.size=Pt(11)
    revision=source_tables[0]
    row=revision.add_row()
    for cell,value in zip(row.cells,['Random Stuff','2026-11-12','Condensed presentation; all numbered requirements retained.','1.0']):cell.text=value
    for ri,row in enumerate(revision.rows):
        if ri==1:row.cells[1].text='2026-11-07'
        if ri==2:
            row.cells[1].text='2026-11-09';row.cells[2].text='Reorganised into the supplied IEEE template.';row.cells[3].text='1.0'
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(1);p.paragraph_format.line_spacing=1
                for r in p.runs:r.font.size=Pt(10.5)
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    # Remove empty layout spacers except section breaks and picture/field paragraphs.
    for p in list(d.paragraphs):
        if not p.text.strip() and p.style.name=='Normal' and not p._p.xpath('.//w:drawing|.//w:fldChar|.//w:sectPr'):
            remove(p._p)
    d.core_properties.subject='Version 1.0 IEEE SRS condensed for submission'
    d.core_properties.author='Random Stuff'
    DEST.parent.mkdir(parents=True,exist_ok=True)
    d.save(DEST)
    body='\n'.join(p.text for p in d.paragraphs)
    for requirement in requirements:
        assert requirement['id']+' '+requirement['title']+'. '+requirement['statement'] in body,requirement['id']
        assert 'Verification: '+requirement['verification'] in body,requirement['id']
    for path,expected in snapshot.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
    print('Created separate compact DOCX; all 46 exact requirements and verification strings retained.')

if __name__=='__main__':main()
