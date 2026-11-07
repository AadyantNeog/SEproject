"""Build the submission PDF and editable Markdown from one requirements source."""
from pathlib import Path
from html import escape
import json
import re
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/pdf'
DOCS = ROOT / 'docs/requirements'
OUT.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)
PAGES = []
REQS = []

def p(text): return ('p', text)
def h(text): return ('h', text)
def table(headers, rows, widths): return ('table', headers, rows, widths)
def req(rid, title, text, verification):
    REQS.append({'id': rid, 'title': title, 'statement': text, 'verification': verification})
    return ('req', rid, title, text, verification)
def page(title, *blocks): PAGES.append((title, list(blocks)))

page('YouTube Video Intelligence MCP Server',
    ('subtitle', 'Software Requirements Specification'),
    ('meta', 'Version 1.0  |  7 November 2026  |  Stage 1 Requirements'),
    h('Team Random Stuff'),
    table(['Team member', 'Roll number'], [
        ['Aadyant Neog', 'BT2024186'],
        ['Jeswin Jose', 'BT2024142'],
        ['Paul T Mathew', 'BT2024135']
    ], [300, 185]),
    h('Problem statement'),
    p('Learners use YouTube to study specific topics but must manually sift through distracting results, compare creators, check runtimes, and assemble playlists. The proposed system shall let a learner use a conversational AI client to discover relevant videos and channels, understand their accessible YouTube library, and create a focused playlist within explicit time and language constraints.'),
    h('Proposed solution'),
    p('The product is a Model Context Protocol server connected to the official YouTube Data API v3. It shall provide metadata-based similarity, personalised recommendations, engagement summaries, and a preview-and-confirm playlist workflow. The server shall validate constraints and enforce approval before writing to the user account. Reusable agent skills and a linked Second Brain shall support development and demonstration.'),
    h('Document purpose'),
    p('This SRS defines the project scope, externally observable behaviour, quality requirements, skill requirements, and evidence required for acceptance. It is intended for the project team, instructor, reviewers, and testers. The five functional feature identifiers in the assignment are preserved. All numbered requirements are mandatory for the project baseline unless a condition is explicitly stated.'),
    h('Document control'),
    table(['Field', 'Value'], [
        ['Document identifier', 'SRS-YT-MCP-001'],
        ['Selected topic', 'YouTube Video Intelligence MCP Server'],
        ['Submission unit', 'One SRS for the entire team'],
        ['Baseline rule', 'The topic and submitted SRS are fixed after submission.'],
        ['Primary authority', 'Project statement [R1] and common SDLC requirements [R2]']
    ], [112, 373]),
    p('This specification defines required behaviour; implementation and verification results are recorded separately. It does not assert that the product has already been built, approved, or submitted.')
)

page('1 Introduction and scope',
    h('1 1 Objectives'),
    p('The system shall reduce the effort needed to assemble a focused learning playlist, make selection reasons understandable, respect the learner\'s constraints, and preserve user control over account changes. Relevance is a metadata-based estimate, not a guarantee of factual correctness, teaching quality, or learning outcomes.'),
    h('1 2 Scope of delivery'),
    table(['Feature', 'Required outcome'], [
        ['FR-1 Similar videos', 'Rank videos related to a supplied video URL or ID.'],
        ['FR-2 Similar channels', 'Rank channels related to a channel URL, handle, or ID.'],
        ['FR-3 Recommendations', 'Use authorised likes, subscriptions, and playlists as preference signals.'],
        ['FR-4 Engagement analysis', 'Report top channels and categories, duration preferences, and supported time comparisons.'],
        ['FR-5 Playlist creation', 'Interpret a request, propose a compliant playlist, obtain approval, and create it.']
    ], [143, 342]),
    h('1 3 Users and responsibilities'),
    p('A learner supplies topics or seed content, authorises account access, examines results, and approves or rejects playlist creation. An AI client translates conversational intent into structured tool calls and presents results. The project team configures credentials, maintains the server, skills and knowledge base, and supplies test evidence. The instructor or reviewer evaluates the requirements and live demonstration.'),
    h('1 4 Scope exclusions'),
    p('The baseline excludes scraping, unofficial APIs, video or audio downloading, arbitrary third-party transcript retrieval, watch-history access, a replacement YouTube player, uploads, comments, likes or subscription changes, and editing or deleting existing playlists. A custom web application, public hosted service, model training, and support for every AI client are not required. The client may summarise API metadata but shall not claim to have watched a video or read unavailable captions.'),
    h('1 5 Requirement conventions'),
    p('"Shall" states a verifiable obligation. FR denotes functional behaviour; NFR denotes a quality or operational constraint; SK denotes an agent skill; GOV denotes engineering process obligations. AT identifies planned acceptance scenarios. Feature subrequirements refine the assignment IDs without replacing them. Sources appear as [R1] to [R12]; Section 16 lists full references.'),
    p('Core scope and learning workflow derive from [R1]. Knowledge management, review, CI and stage obligations derive from [R2]. Numerical operating limits and acceptance thresholds stated here are proposed project commitments, not measured results or external API guarantees.')
)

page('2 Product context and interfaces',
    h('2 1 System boundary'),
    p('The learner interacts with an existing AI client. The client calls the local MCP server, which validates requests, queries a YouTube provider, computes results, manages proposals and approvals, and returns structured responses. The provider alone calls the official YouTube Data API over HTTPS. Google handles user sign-in and consent. The AI model and YouTube are external dependencies.'),
    ('flow', ['Learner', 'AI client', 'MCP server', 'YouTube provider', 'YouTube API']),
    h('2 2 Operating environment'),
    p('The baseline shall run locally for one authorised account per server instance on a documented Windows development environment. The implementation shall include a reproducible install or build command and dependency versions. A supported desktop MCP client and a browser for Google consent are prerequisites. Internet connectivity, an enabled Google Cloud project, credentials, and a YouTube channel are required for live account operations. Fixture mode shall work without live credentials.'),
    req('NFR-01', 'MCP interoperability', 'The server shall support the standard local stdio transport, negotiated protocol initialisation, tool discovery and invocation, and resource discovery and reading. Tool inputs shall have machine-readable schemas; outputs shall include machine-readable fields and a readable explanation. Diagnostic logging shall use stderr and shall not corrupt stdout protocol messages. At least one documented MCP client shall be demonstrated.', 'AT-01 and AT-19; [R10].'),
    h('2 3 User and external interfaces'),
    table(['Interface', 'Contract'], [
        ['Conversational client', 'Accept natural-language requests; display ranked results, warnings, proposals and approval controls.'],
        ['Google OAuth', 'Browser-based installed-app authorisation with a loopback callback, state validation and PKCE. Tokens do not pass through chat.'],
        ['YouTube Data API v3', 'Retrieve video, channel, subscription and playlist metadata; create only an approved new playlist and its items.'],
        ['MCP resources', 'Expose non-secret capability/help text, current quota status and account-scoped proposal/report resources.'],
        ['Agent skills', 'Ship versioned SKILL.md workflows. Make instructions discoverable as resources and loadable by the selected skill-capable client.']
    ], [122, 363]),
    p('Skills are reusable instructions that orchestrate tools, not a separate standard MCP primitive. Client adapters shall document how those instructions are loaded. Exact tool names, storage schema and ranking weights may be refined during design without changing the behaviour defined here. [R3, R7, R10, R11]')
)

page('3 Data rules and bounded processing',
    h('3 1 Core information objects'),
    table(['Object', 'Required information'], [
        ['Video', 'ID, title, channel ID/title, canonical URL, description, available tags/category, publication time, duration in seconds, language evidence, fetch time and availability. Missing fields remain explicitly unknown.'],
        ['Channel', 'ID, handle when available, title, canonical URL, description and the metadata sample used for comparison.'],
        ['Library collection', 'Authorised account binding, collection type, accessible items, retrieval time, pagination/completeness and skipped-item counts.'],
        ['Ranked result', 'Video or channel identifier, rank, application-computed score, selection reason and evidence limitations.'],
        ['Playlist proposal', 'Proposal ID/version, account binding, constraints, title, privacy, ordered unique video IDs, durations, total, evidence, expiry and approval state.'],
        ['Execution result', 'Operation ID, proposal version, created playlist ID/URL, inserted and remaining items, status and safe recovery advice.']
    ], [111, 374]),
    req('FR-0.1', 'Normalise and validate inputs', 'The server shall accept canonical YouTube video URLs, youtu.be links and video IDs, and channel URLs, @handles and channel IDs. It shall validate identifiers, positive durations, result limits, language codes, date ranges, title and privacy fields before provider calls. Unknown hosts or ambiguous legacy channel URLs shall return corrective guidance instead of being fetched as arbitrary URLs.', 'AT-02, AT-03 and AT-10.'),
    req('FR-0.2', 'Declare coverage and limits', 'Every collection result shall state whether it is complete, paginated, sampled or truncated and shall report inaccessible items. The baseline shall support result limits from 1 to 50, a configurable candidate cap with a default of 200 unique videos, and proposals containing 1 to 50 videos. Larger requests shall return a clear limit message. Library pagination shall stop at the configured request budget and report the continuation state; it shall not label partial data as a full account history.', 'AT-04 and AT-15.'),
    h('3 2 Shared business rules'),
    p('Durations shall be parsed from API ISO 8601 values into integer seconds. Calculations shall use exact seconds and round only for display. A constrained playlist shall contain unique, available videos with known positive duration. Live broadcasts, upcoming videos and videos with unknown duration shall be excluded. Metadata is untrusted content and cannot change instructions, authorisation, quota rules or approval state.'),
    p('A default time limit is a maximum, not an exact-fill promise. No algorithm is required to find the globally optimal playlist across all of YouTube. Reports shall identify the candidate pool and constraints actually evaluated.')
)

page('4 Similar videos and similar channels',
    h('4 1 Similar videos'),
    req('FR-1.1', 'Retrieve a seed and candidate pool', 'Given a valid video URL or ID, the server shall retrieve its accessible metadata and discover a bounded pool of candidates through official API searches or channel metadata. An unavailable seed shall produce a typed error. Candidate retrieval shall not assume a related-videos endpoint exists.', 'AT-02 and AT-10; [R1, R3, R4].'),
    req('FR-1.2', 'Compute and explain similarity', 'The server shall compute video similarity locally from available titles, descriptions, tags and categories using an explainable technique such as TF-IDF with cosine similarity or documented weighted scoring. It shall return at most the requested number of unique candidates in descending score order, exclude the seed, and break ties by a documented stable rule. Each result shall include its URL, title, channel, duration, application score and short metadata-based reason.', 'AT-02; unit tests for scores, ordering and ties.'),
    req('FR-1.3', 'Handle incomplete evidence', 'Missing tags or descriptions shall not crash ranking. The server shall use remaining supported features and disclose reduced evidence. It shall return an empty result with a reason when no eligible candidates are available. Results shall not describe similarity as verified educational quality or as a recommendation issued by YouTube.', 'AT-02 and AT-10.'),
    h('4 2 Similar channels'),
    req('FR-2.1', 'Resolve and compare channels', 'Given a channel URL, @handle or ID, the server shall resolve the seed channel and rank distinct candidate channels by available channel descriptions and a bounded sample of their video metadata. The response shall disclose the sample size and selection rule. It shall exclude the seed channel and shall not rely on an assumed related-channels endpoint.', 'AT-03; [R1, R3].'),
    req('FR-2.2', 'Return explainable channel rankings', 'Each channel result shall include ID, title, URL, application score and a short explanation of the topic overlap. Identical inputs, fixtures and configuration shall produce identical ordering. Unresolvable handles, inaccessible channels or insufficient comparable metadata shall return an explicit error or insufficient-data result.', 'AT-03 and AT-10.'),
    h('4 3 Ranking constraints'),
    p('Popularity or engagement counts shall not override explicit topic, language or duration constraints. The ranking method, preprocessing, weights and tie handling shall be documented and versioned. Validation shall use curated fixtures with expected topical matches and clear mismatches; the project does not promise universal recommendation accuracy.'),
    p('The assignment explicitly requires computed similarity. Live use shall address the policy dependency in Section 15 rather than assume that score labelling alone establishes permission.')
)

page('5 Personalised recommendations and analysis',
    h('5 1 Personalised recommendations'),
    req('FR-3.1', 'Read authorised preference signals', 'With read consent, the server shall retrieve accessible liked videos, subscriptions, and playlists and their accessible items. It shall form a preference profile from the available sources, deduplicate video IDs across collections, and identify each source and its coverage. It shall not obtain or infer an actual watch-history feed.', 'AT-04; [R1, R4].'),
    req('FR-3.2', 'Recommend and explain', 'The server shall discover and rank a bounded set of videos using that profile and any explicit topic, duration or language filters. Each result shall identify the signals supporting the recommendation. Results shall exclude seed/profile videos by default and shall disclose this exclusion. The same fixtures and settings shall produce a stable ranking.', 'AT-04 and AT-15.'),
    req('FR-3.3', 'Support sparse and denied data', 'If a source is empty or inaccessible, the server shall report the limitation and use remaining consented sources. If no usable preference data exists, it shall request a seed video or topic rather than invent preferences. Permission errors shall never be bypassed by scraping or another account.', 'AT-04 and AT-11.'),
    h('5 2 Engagement analysis'),
    req('FR-4.1', 'Summarise accessible collections', 'The server shall report the top channels and video categories by item count, duration preferences through count, mean and median video length, and counts in documented duration bands. It shall distinguish liked videos, subscriptions and playlist items, identify the denominator of each count or percentage, and state duplicate handling, missing metadata and the retrieved population. Subscription summaries shall count channels rather than pretend subscriptions are video views.', 'AT-05 with hand-calculated fixtures.'),
    req('FR-4.2', 'Compare periods with valid timestamps', 'The server shall support two user-specified non-overlapping periods for trends and comparisons using available playlist-addition and subscription-creation timestamps. UTC intervals shall be start-inclusive and end-exclusive. Reports shall name the timestamp basis and include absolute differences; percentage change from a zero baseline shall be marked undefined. Video publication dates shall not be substituted for engagement dates. Unsupported like-event dates shall be reported as unavailable.', 'AT-05, including boundaries, zero baselines and missing dates; [R5].'),
    req('FR-4.3', 'Avoid unsupported conclusions', 'Reports shall label the data as accessible collection activity and shall not claim watch time, completion, full historical behaviour or learning progress. A video runtime describes the video, not time actually watched. Empty periods shall return zero supported counts and a clear insufficient-evidence explanation for other measures.', 'AT-05; [R1].')
)

page('6 Playlist interpretation and proposal',
    h('6 1 Request interpretation'),
    req('FR-5.1', 'Translate and validate a request', 'The AI client and server together shall accept a natural-language playlist request specifying topic, total duration, maximum video length and language. The client shall translate these into structured values; the server shall independently validate them. Missing or ambiguous hard constraints shall be clarified before proposing a playlist. A request for an exact total shall be clarified as an upper limit or rejected as unsupported, rather than silently reinterpreted.', 'AT-06 and AT-10.'),
    req('FR-5.2', 'Enforce hard constraints', 'The server shall build an ordered proposal whose total duration does not exceed the requested total and whose individual durations do not exceed the requested maximum. Every selected video shall satisfy the stated topic-selection rule and requested language according to available API language metadata. Unknown language shall not count as a strict match, and search relevanceLanguage alone shall not prove spoken language. Unverifiable candidates shall be excluded and the evidence limitation shall be shown.', 'AT-06, AT-07 and duration-boundary unit tests.'),
    req('FR-5.3', 'Handle insufficient candidates', 'The server shall report if no non-empty feasible proposal can be built. If only a shorter compliant playlist is available, it shall show the total and unused time and allow the user to accept it or revise the request. It shall never relax a hard constraint, add duplicate filler or claim exact duration without evidence.', 'AT-07.'),
    req('FR-5.4', 'Present the complete proposal', 'Before any playlist write, the client shall display the destination account/channel, title, privacy, topic and constraints, ordered video titles and links, channels, per-video duration, total duration, language evidence, warnings and proposal expiry. Default privacy shall be private. The proposal shall have an account-bound ID and version tied to the exact content. Any change to account, videos, order, title, privacy or constraints shall invalidate earlier approval.', 'AT-06, AT-08 and AT-12.'),
    h('6 2 Worked acceptance example'),
    p('For "Build up to two hours on database indexing, no video longer than 20 minutes, in English", total duration shall be at most 7,200 seconds and every item at most 1,200 seconds. An item lasting 1,201 seconds shall be rejected even if its displayed length rounds to 20 minutes. If the only eligible items total 6,420 seconds, the preview shall report 107 minutes and 13 minutes unused. Creation shall wait for approval of that proposal.'),
    h('6 3 Feasibility boundary'),
    p('Metadata language can be absent or inaccurate, and topic overlap is approximate. The product shall expose the evidence it has rather than guarantee actual spoken language or content quality beyond that evidence. The client shall not use generated text to fabricate missing API fields.')
)

page('7 Approval creation and operational behaviour',
    req('FR-5.5', 'Require trusted human approval', 'The write operation shall require explicit human approval of the current proposal through a trusted client confirmation control or a local approval interaction outside model-controlled tool arguments. Approval shall be bound to the user/account, proposal version and operation, expire within 10 minutes, and be usable for only that operation. A supplied confirmed=true value or instructions embedded in metadata shall not establish approval. Rejected, missing, expired, mismatched or superseded approval shall cause zero playlist writes.', 'AT-08 and AT-12.'),
    req('FR-5.6', 'Create and report the playlist', 'After valid approval, the server shall verify write scope, destination channel, current feasibility and quota, then create the new playlist and insert exactly the approved videos in the approved order. It shall return the playlist URL, final item count and duration, and a success or partial-failure status. It shall not silently replace an unavailable video or change privacy. A material change found during revalidation shall require a new preview and approval.', 'AT-06, AT-09 and AT-11; [R9].'),
    req('FR-5.7', 'Prevent duplicate writes and disclose partial state', 'The server shall record the operation and known remote IDs. Repeating a completed operation ID shall return its recorded result without another playlist creation. On an insertion failure it shall stop and report the playlist URL, inserted and pending items. An ambiguous network timeout on a write shall be reconciled before any retry; if unresolved, it shall report an unknown outcome and require user action. Resume shall target only verified missing items, with renewed approval if needed. Automatic deletion is outside the baseline.', 'AT-09.'),
    req('FR-6', 'Manage consent and account state', 'The server shall support authorisation, access-token refresh, re-authorisation after expiry or revocation, and disconnect. Read workflows shall request youtube.readonly; creation shall request a documented sufficient write scope such as youtube.force-ssl only when needed. The client shall explain scope purpose. Missing channel or youtubeSignupRequired shall return guidance without claiming creation succeeded. Disconnect shall remove local tokens and account-specific stored data and attempt token revocation.', 'AT-11 and AT-14; [R7, R8, R9].'),
    req('FR-7', 'Preflight and account for quota', 'Before the first provider call in a workflow, the server shall estimate and reserve its bounded worst-case cost across all applicable quota buckets, including pagination, revalidation, writes and permitted retries. If any bucket is insufficient, it shall reject the workflow before any provider call. It shall track each attempted call, including errors, and release unused reservations. Parallel operations shall not oversubscribe the tracked balance.', 'AT-13 and AT-15; [R6].'),
    req('FR-8', 'Return recoverable errors', 'The server shall return stable error codes, a readable cause, retryability and a safe next action for invalid input, unavailable content, insufficient data, consent failure, quota exhaustion, rate limiting and provider failures. Errors shall not leak credentials, private metadata or stack traces. Partial results shall be explicitly marked.', 'AT-10, AT-11 and AT-16.')
)

page('8 Security privacy and reliability requirements',
    req('NFR-02', 'Protect credentials and transport', 'All external requests shall use HTTPS. OAuth access and refresh tokens shall be stored through OS-protected credential storage or an equivalently protected encrypted local store, with the key outside the repository. Secrets shall never appear in source, fixtures, brain notes, chat, logs, resources or tool results. Automated secret scanning shall run on pull requests.', 'AT-14; inspect repository, logs and token storage.'),
    req('NFR-03', 'Enforce authority boundaries', 'The server shall validate schemas and account bindings on every tool call and resource read. It shall treat titles, descriptions, tags and retrieved text as data, never instructions. Only the trusted human approval path shall authorise playlist writes; the model and external metadata shall not be able to mint approval. Cross-account or modified-proposal access shall fail.', 'AT-12 and AT-14 adversarial tests.'),
    req('NFR-04', 'Minimise personal data', 'Only data needed for the requested workflow shall be collected. Private account data shall remain isolated from other accounts and shall not be sent to the AI client except as needed for the requested result. Fixtures and CI logs shall contain synthetic or fully anonymised data. A user-facing privacy notice shall explain collection, AI-client disclosure, retention, disconnect and local deletion.', 'AT-14 and documentation inspection.'),
    req('NFR-05', 'Limit retention and support removal', 'API metadata caches shall expire within 24 hours by default and shall be refreshed or deleted no later than 30 days. Local proposal and operation records containing API data shall follow that limit. Disconnect or a user deletion request shall clear account-specific caches, proposals, operation data and tokens during successful completion. Failed removal shall be reported and shall not be marked complete. Data deletion in this application shall not claim to delete the user\'s YouTube content.', 'AT-14 with simulated time and deletion checks; [R12].'),
    req('NFR-06', 'Fail safely and recover', 'Read requests may use at most three attempts with bounded exponential backoff and jitter for retryable failures. Quota exhaustion and permanent permission errors shall not trigger repeated calls. Write timeouts shall follow FR-5.7. After interruption, stored operation state shall distinguish not-started, in-progress, completed, partial and unknown outcomes. A failed write shall never be reported as complete.', 'AT-09 and AT-16 fault-injection tests.'),
    req('NFR-07', 'Constrain network destinations', 'The server shall parse supported YouTube identifiers locally and shall not fetch arbitrary user-supplied URLs. Provider traffic shall be limited to official Google OAuth and YouTube API destinations required by the workflow. The OAuth callback shall bind only to the local loopback interface. The baseline shall not expose a public network listener.', 'AT-10 and AT-14; inspect outbound requests and callback binding.'),
    p('User approval is independent of OAuth: OAuth grants API capability, whereas proposal approval authorises one particular playlist operation. Both are required. Security requirements apply in fixture tests as well as live use.')
)

page('9 Quality and operational targets',
    req('NFR-08', 'Meet local performance targets', 'On a documented reference machine with at least four CPU cores and 8 GB RAM, fixed offline fixtures and no client-model generation time, input validation shall have a 95th-percentile latency of at most 100 ms; ranking up to 200 candidate videos or constructing a proposal shall take at most 2 seconds. Tests shall use at least 30 measured runs after one warm-up. Cached read responses shall have a 95th percentile of at most 2 seconds. Live network and OAuth latency shall be reported separately.', 'AT-17 benchmark report with hardware, inputs and timings.'),
    req('NFR-09', 'Bound runtime and resource use', 'A provider HTTP attempt shall have a configurable timeout with a default of 15 seconds. A foreground read or planning workflow shall stop after a configurable deadline with a default of 60 seconds, return a typed timeout or labelled partial result, and perform no writes. Creation shall report progress and honour the same per-attempt timeout; a stop shall preserve partial/unknown state. All searches and pagination shall respect the declared candidate and quota caps.', 'AT-15 and AT-16 with simulated delays and bounded-call assertions.'),
    req('NFR-10', 'Provide usable and explainable results', 'The client shall display human-readable durations, clickable source URLs, collection coverage, relevant constraints and actionable errors. Scores shall be labelled application estimates and shall identify the metadata used. Confirmation shall explicitly identify account and privacy. User and developer documentation shall include setup, consent, each feature, limits, recovery and one complete example.', 'AT-19 task walkthrough and documentation review.'),
    req('NFR-11', 'Support maintainable testing', 'YouTube access shall be isolated behind a provider interface replaceable by a fixture provider. Domain rules for similarity, duration parsing, constraints and approval shall be testable independently of a live API or AI model. Dependencies and the supported runtime shall be declared. CI shall build or validate the package, lint, test, scan secrets and validate skills and brain notes on every PR.', 'AT-18 and AT-20; [R2].'),
    req('NFR-12', 'Track changing API quotas', 'Quota method costs, bucket limits and daily reset rules shall be configurable and versioned with an authoritative reference date. The initial profile shall account for a 10,000-unit daily general bucket and the separately documented 100-call daily search allowance. The local ledger shall survive server restart and use the provider\'s reset boundary. It shall expose estimated remaining budget and warn that other applications sharing the Cloud project can consume unobserved quota.', 'AT-13 and AT-15; [R6].'),
    h('9 1 Acceptance boundaries'),
    p('These latency and resource targets apply to the specified local test conditions. They do not create a public-service uptime promise or guarantee YouTube availability. A workflow that meets local preflight may still receive a provider quota error if quota was consumed elsewhere; it shall handle that error safely. Testing-mode refresh-token expiry shall be handled through re-authorisation rather than an assumed permanent login. [R8]')
)

page('10 Agent skill requirements',
    p('Each skill shall be a versioned folder containing SKILL.md with valid name and description frontmatter, invocation conditions, inputs, workflow, output and failure behaviour. Each shall cite a distilled brain note. The project shall make its instructions discoverable through the documented client setup and MCP resources. Skills orchestrate server tools and cannot override server validation or human approval. [R2, R11]'),
    req('SK-01', 'brain ingest', 'The brain-ingest skill shall capture supplied material or research as source-linked notes, record authorship and date, add requirement IDs and related wikilinks, update the index, and append the run to the log. Stage 1 shall contain at least 10 distinct research notes created through this workflow. Unverified material shall be identified as such.', 'AT-18: ingest sample material; inspect at least 10 source-linked research notes.'),
    req('SK-02', 'brain refine', 'The brain-refine skill shall organise notes into PARA, merge duplicates while preserving sources and authorship, and repair or report broken links. It shall report the changes made and leave an auditable history through the normal PR workflow.', 'AT-18: duplicate-note and broken-link fixtures.'),
    req('SK-03', 'brain query', 'The brain-query skill shall answer project questions or draft a document from relevant notes, cite the notes supporting its claims, and disclose missing or conflicting evidence. It shall not invent decisions, approvals, test results or sources.', 'AT-18 and AT-19: answer a requirement-to-decision question and an unsupported question.'),
    req('SK-04', 'local check', 'The local-check skill shall build or validate the project, run the automated test suite, start the local server, invoke one read-only fetch tool through MCP, and report pass, fail or blocked separately for every step. It shall terminate resources it started. Fixture mode shall be the default; an explicitly configured live check shall report quota used.', 'AT-19: live demonstration of all five steps with individual statuses.'),
    req('SK-05', 'video to playlist', 'The video-to-playlist skill shall accept a seed video, summarise its available title/description metadata with a stated evidence basis, find similar videos through FR-1, collect playlist constraints, propose a playlist, obtain human confirmation, create it through FR-5, and present a short analysis of duration, channels and constraints. Rejection or an infeasible request shall end without writes. It shall not claim access to full video content or unavailable transcripts.', 'AT-06, AT-08 and AT-19; full accepted and rejected workflow evaluations.'),
    req('SK-06', 'Evaluate skills before submissions', 'Each applicable skill shall have repeatable evaluation cases covering a successful path, a negative path and evidence/authority handling. Evaluations shall run before each relevant stage submission and results shall be recorded with inputs, expected behaviour, observed behaviour and pass/fail/blocked status.', 'AT-18; stage-specific evaluation records, not generated claims of success.')
)

page('11 Engineering and Second Brain obligations',
    req('GOV-01', 'Maintain linked project knowledge', 'The repository shall contain an Obsidian-compatible brain vault with inbox, projects, areas, resources and archive directories, an index entry point and an append-only run log. Notes shall link to other notes, requirement IDs and real issues/PRs as available. Every team member shall author notes under their own identity.', 'AT-20; repository and commit-history review; [R2] SB-1, SB-6.'),
    req('GOV-02', 'Record decisions and AI work', 'The repository shall contain root AGENTS.md and significant design decisions in docs/adr/. Each ADR and skill shall cite at least one distilled note. Significant AI sessions shall record goal, outcome and what worked or failed. The team shall write a review note at each stage and shall be able to explain every merged artefact.', 'AT-20; [R2] SB-2 to SB-4 and AI policy.'),
    req('GOV-03', 'Use reviewed version control', 'All work and defects shall be tracked as GitHub Issues. Code, skills, brain and document changes shall use meaningful incremental commits and PRs with at least one human review. The team shall document its branching strategy and maintain release tags and a changelog. Contributions shall remain attributable to their actual authors.', 'AT-20; inspect issues, commit history, PR reviews and release records; [R2].'),
    req('GOV-04', 'Maintain engineering artefacts', 'The team shall maintain architecture and design documentation with suitable UML/ER diagrams, ADRs, a development plan and task breakdown, user documentation and developer documentation for MCP tools/resources and provider interfaces. An OpenAPI document is required only if a REST interface is introduced.', 'AT-20; [R2] SE-2 to SE-4 and SE-7.'),
    req('GOV-05', 'Preserve traceability and the submitted baseline', 'The team shall maintain requirement-to-issue-to-PR-to-test-to-skill-to-brain-note traceability. Before submission, requirement edits shall be reviewed. After submission, the selected topic and SRS shall remain the fixed baseline; implementation decisions shall refine it without silently changing scope. Instructor-directed clarifications shall be recorded separately.', 'AT-20; traceability completeness and baseline comparison.'),
    h('11 1 Stage evidence'),
    table(['Stage', 'Required evidence'], [
        ['1 Requirements', 'SRS with FR/NFR/SK; PARA vault, index/log, at least 10 ingested research notes; AGENTS.md; repository and CI skeleton.'],
        ['2 Design', 'Architecture, diagrams and ADRs; brain-refine and brain-query; initial local-check.'],
        ['3 Testing and CI', 'Continuous testing/CI plan and results; evaluated video-to-playlist; defect log and regression tests; stage reviews.'],
        ['4 Review', 'Live FR-1 to FR-5 demonstration; product skill, local-check and brain-query; traced requirement walkthrough; final release tag.']
    ], [101, 384]),
    p('This document is the Stage 1 SRS. Later artefacts and live evidence remain deliverables to be produced; their inclusion as requirements is not a claim of completion.')
)

page('12 User workflows and acceptance scenarios',
    h('12 1 Principal use cases'),
    table(['Use case', 'Main flow and expected end state'], [
        ['UC-01 Discover related content', 'Learner supplies a video or channel. Client calls the matching discovery tool. Server validates, preflights, retrieves and ranks. Client shows distinct results and reasons. No account writes occur.'],
        ['UC-02 Get personal recommendations', 'Learner grants read consent. Server retrieves accessible library signals and reports coverage. Client shows explained recommendations or requests a seed when data is insufficient.'],
        ['UC-03 Analyse activity', 'Learner selects collections and optional comparison periods. Server reports supported counts, durations and date-based comparisons, with denominators and unknowns.'],
        ['UC-04 Create a constrained playlist', 'Learner supplies constraints. Client shows a compliant proposal. Learner approves the exact account-bound version. Server validates authority, rechecks and creates. Client shows a URL and actual completion state.'],
        ['UC-05 Reject or revise', 'Learner declines or changes a proposal. No writes occur. A revision receives a new version and requires fresh approval.'],
        ['UC-06 Recover access or failure', 'An expired token, missing channel, quota error or partial write produces specific guidance. The user can re-authorise or resolve the issue without an automatic duplicate playlist.']
    ], [135, 350]),
    h('12 2 Playlist state transitions'),
    p('A valid request produces a proposed state. A trusted approval of the current version moves it to approved. Successful preflight and revalidation allow creating, followed by completed or partial/unknown. Rejection, expiry or modification prevents creation. A changed proposal returns to proposed and requires another approval. A failed preflight makes no provider calls; an API failure after execution starts may consume quota and leave a disclosed partial state.'),
    h('12 3 End to end acceptance example'),
    p('With synthetic fixtures containing eligible and ineligible videos, UC-04 shall produce a feasible ordered proposal for the two-hour example in Section 6. Rejection shall leave the provider write-call count at zero. Approval shall create one private playlist with exactly the approved items and order. A repeated operation ID shall return the existing result. A later insertion failure shall return the actual partial playlist and pending items. Tests shall run through MCP rather than invoke domain functions alone.'),
    p('The final demonstration shall use at least one documented client and an authorised test account for permitted live operations. Fixture results shall always be labelled; they shall never be presented as proof of live API execution.')
)

page('13 Verification plan and completion criteria',
    h('13 1 Acceptance test catalogue'),
    table(['ID', 'Scenario and required evidence'], [
        ['AT-01', 'MCP initialisation, tool schemas, resources, stdio cleanliness and selected-client connection.'],
        ['AT-02', 'Video ranking: seed exclusion, duplicates, stable ties, missing tags and empty candidates.'],
        ['AT-03', 'Channel URL/handle/ID resolution and explainable, distinct channel rankings.'],
        ['AT-04', 'Personalisation using all three signal types, sparse sources and visible pagination.'],
        ['AT-05', 'Hand-calculated analysis, UTC boundaries, empty periods and unavailable event times.'],
        ['AT-06', 'Successful constrained proposal, approval, exact creation and video-to-playlist flow.'],
        ['AT-07', 'Duration/language/topic constraints, unknown metadata, underfill and infeasibility.'],
        ['AT-08', 'Reject, absent, expired, replayed, changed or wrong-account approval; zero new writes.'],
        ['AT-09', 'Partial creation, restart, ambiguous timeout, reconciliation and duplicate prevention.'],
        ['AT-10', 'Malformed IDs, unsupported hosts, invalid limits and private/deleted content.'],
        ['AT-11', 'Expired/revoked tokens, denied scope, failed refresh and youtubeSignupRequired.'],
        ['AT-12', 'Metadata prompt injection and model-forged approval cannot bypass confirmation.'],
        ['AT-13', 'Insufficient general or search bucket: reject before any provider call; concurrent reservation.'],
        ['AT-14', 'Secret storage/redaction, least privilege, isolation, local deletion and cache expiry.'],
        ['AT-15', 'Pagination/candidate caps, cost accounting, reset/restart and externally exhausted quota.'],
        ['AT-16', 'Rate limiting, timeouts and provider 5xx; bounded safe retries and typed failures.'],
        ['AT-17', 'Repeatable offline performance measurements against NFR-08.'],
        ['AT-18', 'Skill evaluations; notes, links and frontmatter validation; offline CI execution.'],
        ['AT-19', 'User-facing walkthroughs, documentation and live skill/client demonstration.'],
        ['AT-20', 'Design, ADR, plan, review, traceability and release-evidence inspection.']
    ], [54, 431]),
    h('13 2 Evidence and exit conditions'),
    p('Tests are planned, not executed results. Acceptance shall require every applicable mandatory requirement to have passing evidence, with unresolved failures and external blocks explicitly listed. Security-critical failures involving approval bypass, secret exposure, cross-account access or duplicate writes shall block release. Missing live credentials or a policy decision shall be reported as blocked, never passed. Regression cases shall be added for significant defects.')
)

page('14 Test quality and traceability',
    h('14 1 Required testing levels'),
    table(['Source requirement', 'Required verification'], [
        ['TQ-1 Unit', 'Test domain functions, services and tool handlers, especially similarity, ISO 8601 duration parsing and constraint boundaries.'],
        ['TQ-2 Integration', 'Test MCP handlers, services, state storage and interchangeable YouTube providers together.'],
        ['TQ-3 System', 'Run AT-02 to AT-06 through the MCP interface for all five core features.'],
        ['TQ-4 Negative', 'Cover invalid IDs, private/deleted videos, missing tags, quotaExceeded, youtubeSignupRequired, expired tokens and rate limits.'],
        ['TQ-5 CI and live separation', 'PR CI uses synthetic fixtures/mocks with no live credentials. A separate scheduled live workflow has a fixed, configurable quota budget and authorised test account.'],
        ['TQ-6 Quota', 'Test full-workflow budget preflight before any API call, accounting for both current bucket profiles and configured cost changes.'],
        ['TQ-7 Skills', 'Evaluate applicable skills before every stage submission and retain the results.'],
        ['TQ-8 Regression', 'Maintain tests as the product changes and give every significant defect a regression case.']
    ], [120, 365]),
    h('14 2 Baseline traceability matrix'),
    table(['Requirements', 'Acceptance', 'Skill', 'Brain note'], [
        ['FR-0.1 to FR-0.2', 'AT-02/03/10/15', 'local-check', '04, 10'],
        ['FR-1.1 to FR-1.3', 'AT-02/10', 'video-to-playlist', '02'],
        ['FR-2.1 to FR-2.2', 'AT-03/10', 'local-check', '02'],
        ['FR-3.1 to FR-3.3', 'AT-04/11/15', 'local-check', '03'],
        ['FR-4.1 to FR-4.3', 'AT-05', 'local-check', '05'],
        ['FR-5.1 to FR-5.7', 'AT-06 to AT-12', 'video-to-playlist', '04, 06, 07'],
        ['FR-6 to FR-8', 'AT-09 to AT-16', 'local-check', '07, 08, 09, 10'],
        ['NFR-01 to NFR-12', 'AT-01/09 to AT-20', 'local-check', '07 to 12'],
        ['SK-01 to SK-06', 'AT-06/08/18/19', 'Each named skill', '11, 12'],
        ['GOV-01 to GOV-05', 'AT-20', 'brain skills', '12']
    ], [132, 117, 111, 125]),
    p('Brain note numbers refer to the stable numbered note titles in the companion repository index. Detailed requirement-to-test links are defined in each requirement above. Actual GitHub Issue, PR and implemented test links shall be added as work is created; none are claimed here. The current traceability register is docs/requirements/traceability.csv. [R1, R2]')
)

page('15 Assumptions dependencies and risks',
    table(['ID', 'Condition and required response'], [
        ['A-01 Client boundary', 'At least one supported client can load skill instructions, display structured results and provide trusted confirmation. A documented local approval path shall be used if the client cannot provide trustworthy approval.'],
        ['A-02 API data limits', 'Only accessible, budget-bounded metadata is available. Unknown language/duration, missing tags, API result caps and absent historical events reduce coverage and shall be disclosed.'],
        ['A-03 Consent and channel', 'The user supplies consent, configured test-user access and a YouTube channel for creation. Denial, Testing-mode expiry or missing channel shall produce guided recovery.'],
        ['D-01 Quota changes', 'The handout describes the 10,000-unit default. Current official documentation additionally separates search into its own daily allowance. The implementation shall use a dated configurable quota profile rather than a permanently hard-coded assumption.'],
        ['D-02 API policy review', 'The assignment requires computed similarity and aggregated analysis. YouTube Developer Policies Section III E 4 restricts derived data and metrics. The team shall resolve the applicability of those restrictions with the instructor and, where needed, the API provider before enabling affected live processing or public deployment. Labelling an application score is not itself evidence of permission.'],
        ['R-01 Data and content quality', 'Metadata can be incomplete, misleading or changed after preview. Show its evidence and retrieval time; revalidate before creation. Do not claim verified educational quality.'],
        ['R-02 Partial remote writes', 'YouTube operations are separate API calls, so playlist creation and insertion are not one atomic transaction. Preserve operation state, disclose partial results and reconcile uncertain outcomes.'],
        ['R-03 Evaluation evidence', 'Use fixtures to verify required algorithms and error paths while external dependencies are unavailable. Keep fixture and live evidence distinct. An unresolved live dependency remains a block to the affected live acceptance scenario.']
    ], [112, 373]),
    h('15 1 Scope stability'),
    p('The chosen topic and five core features remain the baseline. An external policy issue shall not silently remove a required feature or be treated as solved through scraping, extra Cloud projects or unapproved data collection. Record the interpretation and resolution as an ADR linked to this SRS and its supporting brain notes. A required scope clarification after submission belongs to the instructor.'),
    h('15 2 Terminology'),
    p('MCP means Model Context Protocol. SRS means Software Requirements Specification. OAuth is delegated account authorisation. TF-IDF is term-frequency inverse-document-frequency, a text feature representation; cosine similarity compares feature-vector directions. ADR means Architecture Decision Record. CI means continuous integration. PARA means Projects, Areas, Resources and Archive. A fixture is synthetic or sanitised test data. A proposal is a read-only plan; approval authorises only its exact current version.')
)

REFERENCES = [
    ('R1', 'Project Statement YouTube Video Intelligence MCP Server', 'Supplied project brief, Project_1_YouTube_MCP.pdf, pages 1-2. Authority for FR-1 to FR-5, video-to-playlist, TQ-1 to TQ-6 and official-API constraints.', None),
    ('R2', 'The AI Assisted Software Development Life Cycle', 'Supplied common workflow, SDLC_and_Workflow.pdf, pages 1-3. Authority for Second Brain, engineering, skills, CI, human review and stage deliverables.', None),
    ('R3', 'YouTube Data API reference', 'Google for Developers. Official resource and method catalogue.', 'https://developers.google.com/youtube/data/reference/rest'),
    ('R4', 'Videos list', 'Google for Developers. Video metadata, authorised myRating retrieval and result limits.', 'https://developers.google.com/youtube/data/reference/rest/v3/videos/list'),
    ('R5', 'Playlist items and subscriptions', 'Google for Developers. Playlist-addition and subscription-creation timestamp semantics. See also the subscriptions resource in the same reference.', 'https://developers.google.com/youtube/data/reference/rest/v3/playlistItems'),
    ('R6', 'Quota calculator', 'Google for Developers. Current bucket allocations, endpoint costs and reset boundary; profile checked 7 November 2026.', 'https://developers.google.com/youtube/data/determine_quota_cost'),
    ('R7', 'OAuth 2 for desktop apps', 'Google for Developers. Installed-app consent, loopback callbacks and PKCE.', 'https://developers.google.com/identity/protocols/oauth2/native-app'),
    ('R8', 'Using OAuth 2 to access Google APIs', 'Google for Developers. Refresh-token expiry, revocation and external Testing-mode seven-day lifetime.', 'https://developers.google.com/identity/protocols/oauth2'),
    ('R9', 'Playlist creation and item insertion', 'Google for Developers. Authorised write methods and scopes; see also playlistItems.insert in the same reference.', 'https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert'),
    ('R10', 'Model Context Protocol tools specification', 'Official MCP specification, revision 2025-11-25. Tool schemas, discovery, invocation and human interaction guidance; accompanying resources and transports sections define their interfaces.', 'https://modelcontextprotocol.io/specification/2025-11-25/server/tools'),
    ('R11', 'Agent Skills specification', 'Official skill directory, SKILL.md frontmatter and instruction format.', 'https://agentskills.io/specification'),
    ('R12', 'YouTube API Services Developer Policies', 'Google for Developers. Storage and deletion requirements and derived-data restrictions; see Section III E 4 and dependency D-02.', 'https://developers.google.com/youtube/terms/developer-policies')
]
refblocks = [p('The supplied assignment documents govern project scope. Official technical references support API and interface feasibility. External references were accessed on 7 November 2026 and may change; the team shall preserve the configuration and reference date used for verification.')]
for rid, title, desc, url in REFERENCES:
    refblocks.append(('ref', rid, title, desc, url))
page('16 References', *refblocks)

def build():
    fontdir = Path('C:/Windows/Fonts')
    for name, filename in [('SRS','calibri.ttf'),('SRS-Bold','calibrib.ttf'),('SRS-Italic','calibrii.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(fontdir / filename)))
    pdfmetrics.registerFontFamily('SRS', normal='SRS', bold='SRS-Bold', italic='SRS-Italic', boldItalic='SRS-Bold')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyS', fontName='SRS', fontSize=10.5, leading=13.5, spaceAfter=7, textColor=colors.black))
    styles.add(ParagraphStyle(name='HeadS', fontName='SRS-Bold', fontSize=17, leading=20.5, spaceAfter=14, textColor=colors.black))
    styles.add(ParagraphStyle(name='SubS', fontName='SRS-Bold', fontSize=11.5, leading=14, spaceBefore=8, spaceAfter=6, textColor=colors.black, keepWithNext=True))
    styles.add(ParagraphStyle(name='TitleS', fontName='SRS-Bold', fontSize=25, leading=29, spaceAfter=12, textColor=colors.black))
    styles.add(ParagraphStyle(name='SubtitleS', fontName='SRS', fontSize=17, leading=21, spaceAfter=14, textColor=colors.black))
    styles.add(ParagraphStyle(name='MetaS', fontName='SRS', fontSize=10, leading=13, spaceAfter=20, textColor=colors.black))
    styles.add(ParagraphStyle(name='SmallS', fontName='SRS', fontSize=9, leading=11.5, spaceAfter=5))
    styles.add(ParagraphStyle(name='CellS', fontName='SRS', fontSize=9.5, leading=12, spaceAfter=0))
    styles.add(ParagraphStyle(name='CellHeadS', fontName='SRS-Bold', fontSize=9.5, leading=12, textColor=colors.white))
    def para(text, sty='BodyS'): return Paragraph(escape(text), styles[sty])
    story=[]
    md=[]
    for pi,(title, blocks) in enumerate(PAGES):
        if pi: story.append(PageBreak())
        story.append(para(title,'TitleS' if pi==0 else 'HeadS'))
        md.append(('# ' if pi==0 else '## ')+title+'\n')
        for b in blocks:
            kind=b[0]
            if kind=='p': story.append(para(b[1])); md.append(b[1]+'\n')
            elif kind=='h': story.append(para(b[1],'SubS')); md.append('### '+b[1]+'\n')
            elif kind in ('subtitle','meta'):
                story.append(para(b[1], 'SubtitleS' if kind=='subtitle' else 'MetaS')); md.append(b[1]+'\n')
            elif kind=='req':
                _,rid,label,text,verify=b
                story.append(Paragraph(f'<b>{escape(rid)} {escape(label)}.</b> {escape(text)}', styles['BodyS']))
                story.append(Paragraph('<i>Verification: '+escape(verify)+'</i>',styles['SmallS']))
                story.append(Spacer(1,4))
                md.append(f'**{rid} {label}.** {text}\n\nVerification: {verify}\n')
            elif kind=='table':
                _,headers,rows,widths=b
                data=[[para(x,'CellHeadS') for x in headers]]+[[para(x,'CellS') for x in row] for row in rows]
                t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#333333')),
                    ('GRID',(0,0),(-1,-1),0.45,colors.HexColor('#D9D9D9')),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F5F6')]),
                    ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                    ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                    ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                ]))
                story.extend([t,Spacer(1,10)])
                md += ['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
                md += ['| '+' | '.join(row)+' |' for row in rows];md.append('')
            elif kind=='flow':
                story.append(para('  >  '.join(b[1]),'SmallS'));story.append(Spacer(1,5))
                md.append(' > '.join(b[1])+'\n')
            elif kind=='ref':
                _,rid,label,desc,url=b
                txt=f'<b>[{rid}] {escape(label)}.</b> {escape(desc)}'
                if url: txt+=f'<br/><link href="{escape(url)}" color="#222222">{escape(url)}</link>'
                story.append(Paragraph(txt,styles['SmallS'])); story.append(Spacer(1,6))
                md.append(f'[{rid}] **{label}.** {desc}'+ ('\n'+url if url else '')+'\n')
    def footer(c,doc):
        c.saveState();c.setFont('SRS',8.5);c.setFillColor(colors.HexColor('#444444'))
        if doc.page>1:c.drawString(55,A4[1]-31,'YouTube Video Intelligence MCP Server  |  SRS 1.0')
        c.drawString(55,27,'SRS-YT-MCP-001  |  7 November 2026')
        c.drawRightString(A4[0]-55,27,str(doc.page));c.restoreState()
    path=OUT/'YouTube_Video_Intelligence_SRS.pdf'
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=55,leftMargin=55,topMargin=54,bottomMargin=48,
        title='YouTube Video Intelligence MCP Server Software Requirements Specification',author='Random Stuff',subject='Stage 1 Software Requirements Specification',pageCompression=1)
    def outline(flowable):
        if isinstance(flowable,Paragraph) and flowable.style.name in ('TitleS','HeadS'):
            key=f'section-{doc.page}'
            doc.canv.bookmarkPage(key)
            doc.canv.addOutlineEntry(flowable.getPlainText(),key,level=0,closed=False)
    doc.afterFlowable=outline
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    (DOCS/'SRS.md').write_text('\n'.join(md),encoding='utf-8')
    (DOCS/'requirements.json').write_text(json.dumps(REQS,indent=2)+'\n',encoding='utf-8')
    print(f'Built {path}; {len(PAGES)} intended pages, {len(REQS)} requirements')

if __name__=='__main__': build()
