# Competition Rules and Compliance Guide

**Competition:** CockroachDB x AWS Hackathon - Build with Agentic Memory
**Official title in the rules:** CockroachDB x AWS Hackathon - Build the Future
of Agentic Memory
**Last verified:** 2026-07-24
**Operational owner:** Project owner

## 1. Authority and source links

This document is a working summary. It does not reproduce or replace the legal
Official Rules. The live Official Rules prevail if this file is incomplete,
outdated, or inconsistent.

- [Official Rules](https://cockroachdb-ai.devpost.com/rules)
- [Hackathon overview](https://cockroachdb-ai.devpost.com/)
- [Official resources](https://cockroachdb-ai.devpost.com/resources)
- [Devpost Terms of Service](https://info.devpost.com/terms)
- [AWS event terms](https://aws.amazon.com/events/terms/)

The Official Rules may change. Re-verify them before architecture approval,
public launch, and final submission.

The 2026-07-24 verification confirmed the published submission deadline,
meaningful CockroachDB and AWS integration requirements, the minimum of two
eligible CockroachDB tools, public-source and demonstration requirements, and
the entrant's responsibility for usage above applicable free tiers. No
material conflict with the current DocWeave baseline was identified.

## 2. Dates

| Event | Official Eastern Time | Europe/Rome operational reference |
| --- | --- | --- |
| Submission opens | June 30, 2026, 10:00 EDT | June 30, 2026, 16:00 CEST |
| Submission deadline | August 18, 2026, 17:00 EDT | August 18, 2026, 23:00 CEST |
| Judging starts | August 19, 2026, 10:00 EDT | August 19, 2026, 16:00 CEST |
| Judging ends | September 15, 2026, 17:00 EDT | September 15, 2026, 23:00 CEST |
| Winners announced | Around September 21, 2026, 15:00 EDT | Around September 21, 2026, 21:00 CEST |

Eastern Time controls. The Rome conversion is a convenience and must be
rechecked if an official date changes.

## 3. Eligibility summary

- Individuals must be at least 18 or the age of majority in their jurisdiction.
- Teams may contain up to five people.
- A team or organization must appoint an authorized representative.
- Geographic, employment, judging, affiliation, and conflict-of-interest
  exclusions in the Official Rules apply.
- Participation also requires acceptance of Devpost and AWS terms.

The project owner is responsible for confirming personal eligibility. This
repository does not make a legal eligibility determination.

## 4. Mandatory project requirements

The submission must be a newly created agentic application that:

1. uses CockroachDB as its persistent memory layer;
2. is deployed on AWS;
3. integrates required CockroachDB and AWS components meaningfully rather than
   merely initializing them;
4. installs and runs consistently on its stated platform;
5. behaves as shown and described in the submission;
6. discloses any incorporated pre-existing work;
7. uses third-party software, services, data, and media only with authorization
   and license compliance.

## 5. CockroachDB requirement

At least two of these tools must be used:

1. CockroachDB Cloud Managed Model Context Protocol Server;
2. CockroachDB Distributed Vector Indexing;
3. `ccloud` Command-Line Interface with agent-ready access patterns;
4. CockroachDB Agent Skills repository.

### Proposed DocWeave evidence strategy

This is a plan, not an implementation claim:

| Tool | Intended meaningful role | Required evidence |
| --- | --- | --- |
| Managed Model Context Protocol Server | Audited agent-assisted schema inspection, database diagnostics, and memory operations | Configuration, audit record, reproducible workflow, and demo trace |
| Distributed Vector Indexing | Store document embeddings alongside transactional memory and retrieve related documents | Schema and index migration, query plan, retrieval evaluation, and visible demo |
| Agent Skills repository | Optional third tool for reviewed CockroachDB operational workflows | Pinned skill source, invoked workflow, and resulting evidence |

No tool may be claimed until the runtime or operational workflow is implemented
and demonstrated.

## 6. AWS requirement

At least one AWS service must power the agent environment. Eligible examples in
the rules include Amazon Bedrock, AWS Lambda, Amazon Elastic Container Service,
Amazon Elastic Kubernetes Service, Amazon Simple Storage Service, Amazon
SageMaker, and Amazon Bedrock Agents.

### Proposed DocWeave evidence strategy

This is a plan, not an implementation claim:

| Service | Intended role | Required evidence |
| --- | --- | --- |
| Amazon Bedrock | Model inference for document analysis and agent reasoning | Invocation trace, model configuration, evaluation, latency, and cost evidence |
| Amazon Simple Storage Service | Immutable original document storage | Versioning or immutability design, encryption, access policy, and demo evidence |
| AWS compute service | Host the application and background processing | Infrastructure as Code, deployment output, health check, and public demo URL |

The final compute choice requires architecture and budget approval.

## 7. Submission package

The final Devpost submission must include:

- a project satisfying all technology requirements;
- a public code repository for judging and testing;
- complete source code and dependencies;
- a clear English README with setup and run instructions;
- example configurations or datasets where applicable;
- a visible open-source license, with MIT or Apache 2.0 recommended by the
  rules;
- a URL to a functional demo application;
- an English text description of features and functionality;
- a public YouTube or Vimeo demonstration video shorter than three minutes;
- footage of the working project on its intended platform;
- footage that visibly shows the CockroachDB memory layer operating;
- an exact description of which CockroachDB tools and AWS services are used and
  what the agent actually does with them.

An architecture diagram and feedback on CockroachDB AI tooling are optional,
but DocWeave treats both as planned quality deliverables.

## 8. Demo availability and truthfulness

- The demo must be free and available without restriction to the Sponsor,
  Administrator, and judges through the judging period.
- Private demos require testing credentials in the instructions.
- Judges may evaluate only the text, images, and video, so those artifacts must
  communicate value without relying on live exploration.
- The video and written claims must match the actual deployed behavior.
- No trademark, copyrighted music, or third-party media may appear without
  permission.

## 9. Language, ownership, and licensing

- Submission materials must be in English or include an English translation.
- The submission must be original, owned by the entrant, and respect copyright,
  trademark, patent, contract, privacy, and publicity rights.
- Open-source components are permitted when their licenses are followed and the
  project adds original functionality.
- Pre-existing code or work incorporated into the project must be disclosed.
- Projects developed with prohibited financial or preferential support from the
  Sponsor or Administrator may be disqualified.

## 10. Judging

Stage One is a pass/fail viability and theme check. The project must reasonably
fit the theme and use the required application programming interfaces or
software development kits.

Stage Two uses five equally weighted criteria:

| Criterion | DocWeave interpretation |
| --- | --- |
| Agentic Memory Design | CockroachDB must hold durable state, context, embeddings, relationships, decisions, and audit evidence at production-relevant depth |
| Technological Implementation | Integrations must be correct, safe, tested, observable, and reproducible |
| Real-World Impact | The workflow must materially reduce document-management effort while keeping humans in control |
| Product Readiness | Security, resilience, access control, scalability, failure recovery, observability, and cost controls must be credible |
| Creativity and Originality | Multi-agent memory and document relationships must provide value beyond a conventional file organizer or chatbot |

All five criteria receive equal weight. Product polish cannot compensate for a
toy memory layer, and technical complexity cannot compensate for weak impact.

## 11. Submission freeze

Drafts may be updated before the deadline. After the submission period ends,
the submission cannot normally be changed. Devpost or the Sponsor may permit
narrow modifications for intellectual-property, personally identifiable
information, or appropriateness issues, but the project must remain
substantively the same.

Create a tagged, reproducible release and preserve the deployed version before
the deadline.

## 12. Compliance review checkpoints

- Architecture approval
- First end-to-end vertical slice
- Public repository conversion
- Public demo launch
- Video script approval
- Release candidate
- Final submission on Devpost
- Weekly rule-change check until the submission deadline
