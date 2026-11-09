"""Populate the supplied IEEE-style template without rebuilding the prior SRS."""
from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import hashlib
import json
import runpy
import shutil
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tmp/ieee-srs'
FINAL=ROOT/'output/docx/YouTube_Video_Intelligence_SRS_IEEE.docx'
REFERENCE=ROOT/'docs/templates/srs_template-ieee-reference.docx'
if not REFERENCE.exists():REFERENCE=TMP/'template-reference.docx'
SOURCE=runpy.run_path(str(ROOT/'scripts/build_srs.py'))
PAGES=SOURCE['PAGES']
REQS=json.loads((ROOT/'docs/requirements/requirements.json').read_text(encoding='utf-8'))
BY_ID={r['id']:r for r in REQS}
MAPPING=[]
MD=[]

def text_block(page_index, prefix):
    return next(b[1] for b in PAGES[page_index][1] if b[0]=='p' and b[1].startswith(prefix))

def table_block(page_index,index=0):
    return [b for b in PAGES[page_index][1] if b[0]=='table'][index]

def diagram(path,kind):
    im=Image.new('RGB',(1800,620),'white'); draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',36)
    bold=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',38)
    def box(x,y,w,h,lines):
        draw.rectangle((x,y,x+w,y+h),outline='black',width=3)
        for j,line in enumerate(lines):
            bb=draw.textbbox((0,0),line,font=bold if j==0 else font)
            draw.text((x+(w-(bb[2]-bb[0]))/2,y+24+j*40),line,font=bold if j==0 else font,fill='black')
    def arrow(x1,y1,x2,y2,label=''):
        draw.line((x1,y1,x2,y2),fill='black',width=3)
        if x1==x2:draw.polygon([(x2,y2),(x2-10,y2-18),(x2+10,y2-18)],fill='black')
        else:draw.polygon([(x2,y2),(x2-18,y2-10),(x2-18,y2+10)],fill='black')
        if label:
            bb=draw.textbbox((0,0),label,font=font)
            draw.text(((x1+x2-(bb[2]-bb[0]))/2,(y1+y2)/2-45),label,font=font,fill='black')
    if kind=='context':
        box(20,190,270,145,['Learner','Request','Consent'])
        box(435,190,300,145,['AI client','Conversation'])
        box(880,190,365,145,['Local MCP server','Rules and provider'])
        box(1390,190,385,145,['YouTube Data API','Official metadata'])
        arrow(290,260,435,260,'Chat')
        arrow(735,260,880,260,'MCP')
        arrow(1245,260,1390,260,'HTTPS')
        draw.text((125,410),'The server checks account consent, constraints, quota and human approval.',font=font,fill='black')
        draw.text((125,460),'Results return through the same interfaces. Google handles browser sign-in.',font=font,fill='black')
    else:
        xs=[20,480,940,1400]
        for x,ls in zip(xs,[['Proposed','Read-only preview'],['Approved','Exact version'],['Creating','Remote writes'],['Completed','Playlist URL']]):box(x,70,375,140,ls)
        for j,label in enumerate(['Human approval','Recheck and start','All items inserted']):arrow(xs[j]+375,140,xs[j+1],140)
        box(20,390,375,125,['Rejected','No writes']);arrow(207,210,207,390)
        box(480,390,375,125,['Expired or changed','New approval needed']);arrow(667,210,667,390)
        box(940,390,375,125,['Partial or unknown','Reconcile safely']);arrow(1127,210,1127,390)
        draw.text((25,560),'Replayed completed operations return the recorded result without duplicate creation.',font=font,fill='black')
    im.save(path)

def main():
    provenance=ROOT/'docs/requirements/ieee-template-provenance.json'
    state=provenance if provenance.exists() else TMP/'preservation.json'
    preservation=json.loads(state.read_text(encoding='utf-8-sig'))
    TMP.mkdir(parents=True,exist_ok=True)
    for name in ('template','original_srs'):
        assert hashlib.sha256(Path(preservation[name+'_path']).read_bytes()).hexdigest().upper()==preservation[name+'_sha256']
    FINAL.parent.mkdir(parents=True,exist_ok=True)
    retained=ROOT/'docs/templates'
    retained.mkdir(parents=True,exist_ok=True)
    for src,name in [(Path(preservation['template_path']),'srs_template-ieee.doc'),(REFERENCE,'srs_template-ieee-reference.docx')]:
        target=retained/name
        if target.exists():assert target.read_bytes()==src.read_bytes()
        else:shutil.copy2(src,target)
    d=Document(REFERENCE)
    original_paras=list(d.paragraphs)
    revision=d.tables[0]
    cover_values={3:'YouTube Video Intelligence\nMCP Server',4:'Version 1.0',5:'Prepared by Random Stuff',6:'Aadyant Neog  BT2024186\nJeswin Jose  BT2024142\nPaul T Mathew  BT2024135',7:'9 November 2026'}
    for index,value in cover_values.items():
        para=original_paras[index]
        prototype=deepcopy(para.runs[0]._r.rPr) if para.runs and para.runs[0]._r.rPr is not None else None
        para.clear();r=para.add_run(value)
        if prototype is not None:r._r.insert(0,prototype)
    # Retain the original cover/contents section boundaries and live header fields.
    for para in original_paras[10:46]:para._p.getparent().remove(para._p)
    toc=original_paras[9].insert_paragraph_before('')
    original_paras[9]._p.addnext(toc._p)
    run=toc.add_run()
    begin=OxmlElement('w:fldChar');begin.set(qn('w:fldCharType'),'begin');run._r.append(begin)
    instr=OxmlElement('w:instrText');instr.set(qn('xml:space'),'preserve');instr.text=' TOC \\o "1-2" \\h \\z \\t "TOCEntry,1" ';toc.add_run()._r.append(instr)
    sep=OxmlElement('w:fldChar');sep.set(qn('w:fldCharType'),'separate');toc.add_run()._r.append(sep)
    toc.add_run('Contents will be updated by Word before delivery.')
    end=OxmlElement('w:fldChar');end.set(qn('w:fldCharType'),'end');toc.add_run()._r.append(end)
    history=[['Random Stuff','7 November 2026','Initial YouTube SRS and team roster.','1.0'],['Random Stuff','9 November 2026','Reorganised into the teaching assistants\' template; requirement statements retained.','1.0 IEEE']]
    for row,values in zip(revision.rows[1:],history):
        for cell,value in zip(row.cells,values):cell.text=value
    original_paras[46].paragraph_format.page_break_before=True
    revision.autofit=False
    for column,width in zip(revision.columns,[1.15,1.2,3.15,1.0]):column.width=Inches(width)
    for row in revision.rows:
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for cell,width in zip(row.cells,[1.15,1.2,3.15,1.0]):
            cell.width=Inches(width)
    # The remainder is the template's editable body slot, not its section properties.
    body=d.element.body
    first=original_paras[50]._p
    for child in list(body)[list(body).index(first):]:
        if child.tag!=qn('w:sectPr'):body.remove(child)
    for section in d.sections:
        for para in section.header.paragraphs:
            if '<Project>' in para.text:
                para.clear()
                para.paragraph_format.tab_stops.clear_all()
                tabs=para._p.get_or_add_pPr().get_or_add_tabs()
                for pos in ['4680','9360']:
                    clear=OxmlElement('w:tab');clear.set(qn('w:val'),'clear');clear.set(qn('w:pos'),pos);tabs.append(clear)
                usable=section.page_width-section.left_margin-section.right_margin
                para.paragraph_format.tab_stops.add_tab_stop(usable,WD_TAB_ALIGNMENT.RIGHT)
                para.add_run('SRS for YouTube Video Intelligence MCP Server\tPage ')
                field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE')
                r=OxmlElement('w:r');t=OxmlElement('w:t');t.text='1';r.append(t);field.append(r);para._p.append(field)
    current=''
    def heading(label,level=1,appendix=False):
        nonlocal current
        current=label
        para=d.add_paragraph(label,style='TOCEntry' if appendix else f'Heading {level}')
        para.paragraph_format.keep_with_next=True
        if appendix and label.startswith(('Appendix B:','Appendix C:')):
            para.paragraph_format.page_break_before=True
        MD.append('\n'+('#'*(level+1))+' '+label+'\n')
        return para
    def para(text,boldlead=None):
        p=d.add_paragraph(style='Normal');p.paragraph_format.space_after=Pt(6)
        p.paragraph_format.keep_together=True
        if boldlead:
            p.add_run(boldlead).bold=True;p.add_run(text)
        else:p.add_run(text)
        MD.append(text if not boldlead else '**'+boldlead+'**'+text)
        return p
    def record(rid,location):
        r=BY_ID[rid]
        p=para(r['statement'],rid+' '+r['title']+'. ')
        p.paragraph_format.keep_with_next=True
        p.paragraph_format.keep_together=True
        v=para('Verification: '+r['verification'])
        for run in v.runs:run.italic=True
        MAPPING.append({'requirement_id':rid,'ieee_section':location,'title':r['title'],'verification':r['verification']})
    def tab(headers,rows,ratios):
        t=d.add_table(rows=1,cols=len(headers))
        t.alignment=WD_TABLE_ALIGNMENT.LEFT;t.autofit=False
        width=6.7
        for col,ratio in zip(t.columns,ratios):col.width=Inches(width*ratio/sum(ratios))
        for cell,txt in zip(t.rows[0].cells,headers):cell.text=txt
        for vals in rows:
            cells=t.add_row().cells
            for cell,txt in zip(cells,vals):cell.text=txt
        borders=OxmlElement('w:tblBorders')
        for edge in ('top','left','bottom','right','insideH','insideV'):
            e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'000000');borders.append(e)
        t._tbl.tblPr.append(borders)
        margins=OxmlElement('w:tblCellMar')
        for edge in ('top','left','bottom','right'):
            e=OxmlElement('w:'+edge);e.set(qn('w:w'),'80');e.set(qn('w:type'),'dxa');margins.append(e)
        t._tbl.tblPr.append(margins)
        for ri,row in enumerate(t.rows):
            trPr=row._tr.get_or_add_trPr();trPr.append(OxmlElement('w:cantSplit'))
            if ri==0:trPr.append(OxmlElement('w:tblHeader'))
            for ci,cell in enumerate(row.cells):
                cell.width=Inches(width*ratios[ci]/sum(ratios));cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                for p in cell.paragraphs:
                    p.style=d.styles['Normal'];p.paragraph_format.space_after=Pt(2)
                    p.paragraph_format.line_spacing=1
                    for r in p.runs:r.bold=(ri==0)
        d.add_paragraph().paragraph_format.space_after=Pt(0)
        MD.append('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |')
        MD.extend('| '+' | '.join(row)+' |' for row in rows)
        return t
    def source_table(index,n=0,ratios=None):
        b=table_block(index,n)
        return tab(b[1],b[2],ratios or b[3])

    heading('Introduction')
    heading('Purpose',2)
    para('This Software Requirements Specification defines version 1.0 of the YouTube Video Intelligence MCP Server for Team Random Stuff. It covers the complete project baseline: the five required product features, supporting interfaces, quality and security constraints, agent skills, engineering obligations, and acceptance evidence. The topic and submitted requirements remain fixed after submission. This document specifies required behaviour and does not certify completed implementation or human approval.')
    heading('Document Conventions',2)
    para('Shall denotes a mandatory, testable obligation. All numbered requirements are mandatory unless a stated condition applies. FR denotes functional requirements, NFR nonfunctional requirements, SK agent-skill requirements, GOV engineering obligations, and AT planned acceptance scenarios. The original requirement IDs and statements are retained. All system features have High priority because the supplied assignment requires them; priorities do not make detailed requirements optional. References [R1] to [R12] retain their original meanings.')
    heading('Intended Audience and Reading Suggestions',2)
    para('The instructor and reviewers should read Sections 1 and 2 for scope, Section 4 for behaviour, Section 5 for quality, and Appendix C for unresolved dependencies. Developers should additionally study Section 3, the skill and engineering requirements in Section 6, and Appendix B. Testers should use each requirement\'s verification link and the acceptance catalogue in Section 6. Team members are responsible for understanding the complete submitted baseline.')
    heading('Product Scope',2)
    para(text_block(0,'Learners use'))
    para(text_block(0,'The product is'))
    para(text_block(1,'The baseline excludes'))
    heading('References',2)
    para('The supplied project statement and common SDLC document govern scope. The following technical references were consulted for the baseline on 7 November 2026; this template adaptation does not assert a new external-source review. The structural template was supplied by the teaching assistants as srs_template-ieee.doc, based on the Karl E. Wiegers template, copyright 1999, whose permission notice is retained.')
    for rid,title,desc,url in SOURCE['REFERENCES']:
        para(desc+((' '+url) if url else ''),'['+rid+'] '+title+'. ')

    heading('Overall Description')
    heading('Product Perspective',2)
    para('This is a new local integration component used by an existing conversational AI client. It is not a replacement for YouTube or the AI model. The server owns validation, quota tracking, metadata processing, proposal state and account-write safeguards; external services own video hosting, account identity and consent. Appendix B shows the system context and playlist lifecycle.')
    para(text_block(2,'The learner interacts'))
    heading('Product Functions',2);source_table(1,ratios=[28,72])
    heading('User Classes and Characteristics',2)
    tab(['User class','Characteristics and permitted work'],[
        ['Learner','Primary user. Supplies a seed/topic and constraints, grants Google consent, reads results and approves or rejects a proposed playlist. Technical API knowledge is not required.'],
        ['Team developer','Configures local credentials and dependencies, maintains provider integrations, skills, tests and brain notes. Must understand code and documentation submitted under the team workflow.'],
        ['Instructor or reviewer','Examines requirements and evidence, observes demonstrations and checks traceability. Does not receive the learner\'s credentials or unrestricted account access.']
    ],[25,75])
    heading('Operating Environment',2);para(text_block(2,'The baseline shall run'))
    para('The performance reference is a machine with at least four CPU cores and 8 GB RAM, as defined in NFR-08. No GPU, embedded device or special peripheral is required. The supported client/runtime release and dependency versions are recorded during design and installation without changing the five feature commitments.')
    heading('Design and Implementation Constraints',2)
    para('Use only the official YouTube Data API v3, with access isolated behind a replaceable provider interface. Compute similarity from accessible metadata; do not assume watch history or related-video/channel endpoints. Keep tests independent of live API access and do not create extra Cloud projects to evade quota. Account mutations are restricted to creating approved new playlists and their items. The local stdio boundary, OAuth constraints, security controls and quota profile are specified in Sections 3 to 5.')
    heading('User Documentation',2)
    para('Deliver a setup guide, client-connection guide, consent/privacy explanation, feature examples, playlist approval and recovery instructions, and known limits. Developer documentation shall describe MCP tools/resources, schemas, provider interfaces and test execution. Keep these as versioned Markdown and client-readable help resources. If a REST interface is later introduced, its API documentation is governed by GOV-04; no REST interface is required by this baseline.')
    heading('Assumptions and Dependencies',2)
    b=table_block(15);tab(b[1],b[2],[25,75])
    para('Appendix C tracks the unresolved policy and design-selection items. They do not silently remove core features or establish that live acceptance has passed.')

    heading('External Interface Requirements')
    heading('User Interfaces',2)
    para('The existing AI client provides the conversational interface. Users enter video/channel identifiers or natural-language goals and receive readable results with source links, durations and explanations. The proposal view shows the account, privacy, exact ordered videos, constraints and warnings. A trusted client control or local human interaction supplies approval; a tool argument alone is insufficient. Detailed visual layout depends on the selected client and is documented during design.')
    heading('Hardware Interfaces',2)
    para('The product uses standard operating-system process, disk, credential-storage and network facilities on the development machine. It has no direct interface to sensors, actuators or specialist hardware. Browser-based consent and keyboard/mouse interaction are supplied by the host environment.')
    heading('Software Interfaces',2)
    record('NFR-01','3.3')
    source_table(2,ratios=[26,74])
    para('The YouTube provider exchanges validated identifiers and structured resource data. Account tokens remain in protected local storage. Proposal, quota and operation records are account-scoped. Appendix B defines the required data objects. Agent Skills remain versioned SKILL.md instruction packages; exposing instructions as resources does not turn skills into a new MCP protocol primitive.')
    heading('Communications Interfaces',2)
    para('The client launches the MCP server as a local process and exchanges structured protocol messages over stdio. Diagnostics use stderr. Calls to Google OAuth and the YouTube Data API use HTTPS. The OAuth callback binds to loopback only, and the product does not require a public listener, email, FTP or a custom browser service. Schema validation, safe error responses, per-attempt timeouts and account isolation apply at these boundaries. See NFR-02, NFR-07, NFR-09 and FR-8.')

    heading('System Features')
    para('Each feature below is required. Descriptions and response sequences explain the observable workflow; the numbered requirements are the binding details. Error cases and shared controls apply across features. Acceptance tests are planned scenarios, not claimed results.')
    def feature(number,title,description,sequence,ids):
        heading(title,2)
        heading('Description and Priority',3);para('Priority: High. '+description)
        heading('Stimulus/Response Sequences',3)
        for i,(stim,response) in enumerate(sequence,1):para(f'{i}. User or client: {stim} System: {response}')
        heading('Functional Requirements',3)
        for rid in ids:record(rid,f'4.{number}.3')
    feature(1,'Similar Videos','Given a seed video, identify distinct videos with explainable metadata overlap.',[
        ('Provide a supported video URL or ID and a result limit.','Validate and normalise it, preflight the request and retrieve available seed/candidate metadata.'),
        ('Request the ranked results.','Compute similarity, exclude the seed, remove duplicates and return stable ordering with evidence; report an unavailable seed or insufficient candidates explicitly.')
    ],['FR-1.1','FR-1.2','FR-1.3'])
    feature(2,'Similar Channels','Resolve a channel and compare its metadata and bounded video sample with other channels.',[
        ('Provide a channel URL, handle or ID.','Resolve the seed and discover comparable channels within budget.'),
        ('Inspect the comparison.','Return distinct channel rankings, selection reasons and sample limitations, or a corrective error.')
    ],['FR-2.1','FR-2.2'])
    feature(3,'Personalised Recommendations','Use accessible, authorised likes, subscriptions and playlists as preference evidence.',[
        ('Authorise read access and request recommendations, optionally with filters.','Retrieve the available collections, report coverage and build the profile.'),
        ('Inspect recommended content.','Show evidence-linked rankings. If all usable signals are absent, request a seed or topic instead of inventing preferences.')
    ],['FR-3.1','FR-3.2','FR-3.3'])
    feature(4,'Engagement Analysis','Summarise accessible collection activity and compare supported time periods without claiming watch history.',[
        ('Select collections and optional non-overlapping periods.','Retrieve supported records and distinguish playlist-addition, subscription-creation and unavailable event times.'),
        ('Request the report.','Return channel/category counts, duration statistics and valid period comparisons with denominators, missing data and date bases.')
    ],['FR-4.1','FR-4.2','FR-4.3'])
    feature(5,'Constrained Playlist Creation','Interpret a playlist request, show a feasible proposal, obtain exact human approval and create the playlist safely.',[
        ('Specify topic, total duration, maximum item length and language.','Clarify ambiguity and produce a bounded, compliant proposal or an infeasibility explanation.'),
        ('Inspect, revise, reject or approve the proposal.','Make no writes on rejection; invalidate earlier approval after a change. Accept approval only through the trusted human path.'),
        ('Approve the current account-bound version.','Recheck scope, channel, constraints and quota, then create exactly the approved playlist and items.'),
        ('Inspect success or failure.','Return the actual URL and completion state. Reconcile uncertain writes and disclose partial results without duplicate creation.')
    ],[f'FR-5.{i}' for i in range(1,8)])
    para('Worked constraint example: a request for up to two hours with no item longer than 20 minutes means a total of at most 7,200 seconds and an item maximum of 1,200 seconds. A 1,201-second item fails even if rounded display suggests 20 minutes. A feasible 6,420-second proposal shows 107 minutes used and 13 unused. Unknown language/duration does not count as proof of compliance.')
    feature(6,'Authorisation and Account Management','Establish delegated account access and recover from consent expiry, missing scope or missing YouTube channel.',[
        ('Start a workflow requiring private data or a write.','Obtain the minimum sufficient Google consent through the browser and keep tokens outside chat.'),
        ('Disconnect or encounter revoked/expired access.','Clear local account data on disconnect, attempt revocation and provide specific recovery guidance when access fails.')
    ],['FR-6'])
    feature(7,'Quota Budgeting','Reject unaffordable workflows before provider traffic and account for bounded calls safely.',[
        ('Request any API-backed workflow.','Estimate and reserve the cost of the complete bounded operation across applicable buckets.'),
        ('Continue execution or exhaust the available balance.','Track attempts and release unused reservations; reject insufficient budgets before any provider call.')
    ],['FR-7'])
    feature(8,'Input Validation Coverage and Errors','Apply shared input and coverage rules and return safe, actionable error states.',[
        ('Supply an identifier, limit, date range or constraint.','Validate the schema and normalise supported forms before calls.'),
        ('Receive limited or failed results.','Identify pagination, truncation and inaccessible content; return stable error codes with a safe next action and no secrets.')
    ],['FR-0.1','FR-0.2','FR-8'])

    heading('Other Nonfunctional Requirements')
    heading('Performance Requirements',2)
    for rid in ['NFR-08','NFR-09','NFR-12']:record(rid,'5.1')
    para('Performance thresholds apply to the documented local fixture environment. Network availability, OAuth interaction and model generation are external latency factors and must be reported separately. The quota profile remains dated and configurable rather than treating the handout\'s simplified quota summary as immutable.')
    heading('Safety Requirements',2)
    para('The product does not control physical equipment. Its principal loss risks are unintended account changes, exposed personal data and duplicate or partially completed writes. The safeguards are exact human confirmation (FR-5.5), revalidation and honest completion reporting (FR-5.6), operation reconciliation (FR-5.7), and fail-safe recovery (NFR-06). No safety certification is claimed. Metadata-based recommendations must not be represented as a guarantee of factual or educational quality.')
    heading('Security Requirements',2)
    for rid in ['NFR-02','NFR-03','NFR-04','NFR-05','NFR-07']:record(rid,'5.3')
    heading('Software Quality Attributes',2)
    para('Correctness of constraints, explicit approval and protection of user data take precedence over ranking breadth and latency. Reliability, explainability, maintainability and repeatable testing are required as specified below. Interoperability is defined by NFR-01 in Section 3.3.')
    for rid in ['NFR-06','NFR-10','NFR-11']:record(rid,'5.4')
    heading('Business Rules',2)
    tab(['Rule','Enforcing requirements'],[
        ['Only the authorised learner can approve a specific current playlist proposal; OAuth alone is not that approval.','FR-5.4 to FR-5.6; FR-6'],
        ['A total-duration request is an upper bound. Do not fill unused time by violating language, topic, duration or uniqueness constraints.','FR-5.1 to FR-5.3'],
        ['Writes create a new playlist and its approved items only; default privacy is private.','FR-5.4; FR-5.6; scope in Section 1.4'],
        ['Untrusted metadata cannot grant authority or alter budget rules.','FR-5.5; FR-7; NFR-03'],
        ['Retain the submitted topic and requirement baseline; changes need instructor direction.','GOV-05']
    ],[73,27])

    heading('Other Requirements')
    heading('Agent Skill Requirements',2)
    para('Each skill is a versioned directory with valid SKILL.md name/description frontmatter, invocation conditions, inputs, instructions, outputs and failure handling. Every skill cites a distilled brain note. Client setup must document how instructions are loaded; skills cannot override server validation or approval.')
    for i in range(1,7):record(f'SK-{i:02}','6.1')
    heading('Engineering and Knowledge Requirements',2)
    for i in range(1,6):record(f'GOV-{i:02}','6.2')
    source_table(11,ratios=[22,78])
    heading('Verification and Traceability',2)
    para('The following catalogue defines planned acceptance evidence. Each requirement above names the applicable scenarios. Product implementation, test execution, human review and submission are not established by this document.')
    source_table(13,ratios=[12,88]);source_table(14,0,ratios=[27,73]);source_table(14,1,ratios=[28,25,24,23])
    para(text_block(13,'Tests are planned'))
    para('Brain note numbers identify the numbered source notes in the repository index. Actual issue, PR and implementation-test links are added as work is created; missing links are pending rather than fabricated. The companion IEEE requirement-placement map records the new section for each unchanged baseline requirement.')

    heading('Appendix A: Glossary',appendix=True)
    tab(['Term','Definition'],[
        ['MCP','Model Context Protocol; the interface by which a client discovers and calls server tools and reads resources.'],
        ['SRS','Software Requirements Specification; the project\'s required behaviour and constraints.'],
        ['OAuth','Delegated authorisation to an account; separate from confirmation of a particular playlist.'],
        ['TF-IDF','Term-frequency inverse-document-frequency; a text feature representation for similarity.'],
        ['Cosine similarity','Comparison of the directions of two feature vectors.'],
        ['ADR','Architecture Decision Record, linked to supporting knowledge notes.'],
        ['CI','Continuous integration checks run on proposed repository changes.'],
        ['PARA','Projects, Areas, Resources and Archive; the organising system for the Second Brain.'],
        ['Fixture','Synthetic or fully sanitised test data used without live account access.'],
        ['Proposal','An account-bound read-only playlist plan that still requires human approval.'],
        ['Quota bucket','A provider-defined allowance against which particular API methods are accounted.'],
        ['TBD','A tracked item awaiting a decision; it does not make mandatory features optional.']
    ],[26,74])
    heading('Appendix B: Analysis Models',appendix=True)
    para('These conceptual models explain the system boundary and required behaviour. They do not prescribe an implementation language, database product or detailed class design.')
    for kind,caption in [('context','Figure B1 System context'),('state','Figure B2 Playlist approval and execution lifecycle')]:
        path=TMP/(kind+'-model.png');diagram(path,kind)
        p=d.add_paragraph();p.paragraph_format.keep_with_next=True;p.paragraph_format.line_spacing=1
        p.add_run().add_picture(str(path),width=Inches(6.6))
        p=para(caption)
        for run in p.runs:run.italic=True
    para('In Figure B2, a changed or expired proposal returns to the preview/approval workflow. Only successful revalidation permits writes. Partial or unknown outcomes require reconciliation; completed-operation replays return the recorded result. See FR-5.4 to FR-5.7.')
    para('Core information objects and their required fields follow. Unknown metadata remains explicitly unknown, and all account-specific objects require the account binding specified by the baseline.')
    source_table(3,ratios=[24,76])
    heading('Appendix C: To Be Determined List',appendix=True)
    para('The following items are tracked for closure. They preserve the existing policy dependency and leave implementation selections to design; they do not permit silent changes to the submitted topic or mandatory features.')
    tab(['ID','Item and closure evidence','Owner and timing'],[
        ['TBD-01','Resolve dependency D-02: applicability of YouTube derived-data/metric restrictions to the assigned similarity and analytics features. Record the instructor/provider interpretation and permitted live scope in an ADR. Until then, distinguish fixture evidence from blocked live acceptance.','Project team with instructor/provider; before affected live use.'],
        ['TBD-02','Select and document the client/version and trusted human confirmation route required by NFR-01 and FR-5.5. Verify connection, resources and exact-proposal approval.','Project team; design and client-integration stage.'],
        ['TBD-03','Record the implementation runtime, dependency versions and ranking configuration under NFR-11. These selections must meet the preserved requirements and the documented local environment.','Project team; design and reproducible-build setup.']
    ],[13,62,25])
    d.core_properties.title='YouTube Video Intelligence MCP Server Software Requirements Specification'
    d.core_properties.author='Random Stuff'
    d.core_properties.subject='Version 1.0 in the teaching assistants IEEE-style template'
    d.core_properties.comments=''
    setting=d.settings.element.find(qn('w:updateFields'))
    if setting is None:setting=OxmlElement('w:updateFields');d.settings.element.append(setting)
    setting.set(qn('w:val'),'true')
    authored=TMP/'authored.docx';d.save(authored)
    # Keep untouched source package parts byte-identical before Word field refresh.
    allow={'word/document.xml','docProps/core.xml','word/settings.xml','word/_rels/document.xml.rels','[Content_Types].xml'}
    with ZipFile(REFERENCE) as zref,ZipFile(authored) as znew,ZipFile(FINAL,'w',ZIP_DEFLATED) as zout:
        reference_names=set(zref.namelist())
        for name in znew.namelist():
            editable=name in allow or name.startswith('word/header') or name.startswith('word/media/')
            zout.writestr(name,znew.read(name) if editable or name not in reference_names else zref.read(name))
        for name in reference_names-set(znew.namelist()):zout.writestr(name,zref.read(name))
    assert {r['requirement_id'] for r in MAPPING}==set(BY_ID) and len(MAPPING)==46
    (ROOT/'docs/requirements/SRS_IEEE.md').write_text('# YouTube Video Intelligence MCP Server\n\nSoftware Requirements Specification\n\nTeam Random Stuff | Version 1.0 | 9 November 2026\n\nAadyant Neog BT2024186; Jeswin Jose BT2024142; Paul T Mathew BT2024135\n\n'+'\n\n'.join(MD)+'\n',encoding='utf-8')
    with (ROOT/'docs/requirements/ieee-requirements-map.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=MAPPING[0].keys());writer.writeheader();writer.writerows(MAPPING)
    print(f'Created {FINAL}; mapped all {len(MAPPING)} unchanged requirements')

if __name__=='__main__':main()
