# Complete Installation Guide

This guide installs DocWeave from a clean Windows machine, creates its
CockroachDB persistent-memory database, configures Amazon Bedrock for local
analysis, and optionally deploys the complete AWS cloud slice.

The shortest path for judging is **Parts 1-5**. Part 6 is only required when
you want to reproduce the deployed AWS API, queue, worker, and artifact store.

## 1. Prerequisites

Install or create:

- Windows 10 or 11 with PowerShell;
- Git;
- Python 3.12, including `pip` and `venv`;
- an AWS account with access to `eu-central-1` (Europe, Frankfurt);
- AWS Command Line Interface (CLI) version 2;
- a CockroachDB Cloud account.

Optional, but required to reproduce the two CockroachDB tool integrations:

- the [`ccloud` CLI](https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started);
- the
  [CockroachDB Agent Skills repository](https://github.com/cockroachlabs/cockroachdb-skills)
  as a schema and transaction-design reference.

Check the local tools:

```powershell
git --version
python --version
aws --version
```

DocWeave invokes a paid Amazon Bedrock model and the cloud deployment creates
AWS resources. Charges depend on account, region, model usage, storage, and
request volume. CockroachDB Cloud plan charges are separate.

## 2. Clone And Install DocWeave

```powershell
git clone https://github.com/alessandrob1-star/cockroachdb-aws-agentic-memory-docweave.git
cd cockroachdb-aws-agentic-memory-docweave
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
```

Keep this PowerShell window open. Environment variables set later in this
guide apply only to the current window and are not committed to Git.

## 3. Create The CockroachDB Memory Database

### 3.1 Create a CockroachDB Cloud cluster

1. Sign in at [CockroachDB Cloud](https://cockroachlabs.cloud/).
2. Select **Create cluster**.
3. Choose an AWS-backed Basic or Standard cluster that fits your account.
4. Select an AWS region close to the application. DocWeave's submitted
   deployment uses `eu-central-1`.
5. Name the cluster, for example `docweave-memory`, and create it.
6. Create a SQL user and store its generated password in a password manager.

CockroachDB may require an Internet Protocol (IP) allowlist entry before a
local computer can connect. In the cluster's **Connect** dialog, authorize only
your current public IP address. Do not use an unrestricted `0.0.0.0/0` rule.

### 3.2 Create the `docweave` database

Open **SQL Shell** in the CockroachDB Cloud console and run:

```sql
CREATE DATABASE IF NOT EXISTS docweave;
```

Return to the cluster overview, select **Connect**, select the SQL user and the
`docweave` database, then copy the **General connection string**. It should
have this shape:

```text
cockroachdb+psycopg://USER:PASSWORD@HOST:26257/docweave?sslmode=verify-full
```

If the console supplies a Certificate Authority (CA) certificate parameter,
retain it. Password characters that are not valid in a Uniform Resource
Identifier (URI) must be percent-encoded.

CockroachDB Cloud normally supplies a `postgresql://` connection string. For
this Python environment, replace only that scheme with
`cockroachdb+psycopg://`; keep the host, user, password, database, Transport
Layer Security (TLS), and CA parameters unchanged. The explicit `+psycopg`
driver is required because DocWeave installs Psycopg 3, not `psycopg2`.

Never put the real connection string in `.env.example`, a committed file, a
screenshot, or a support message.

### 3.3 Set the local runtime variables

Replace only the placeholder connection string and AWS profile:

```powershell
$env:DOCWEAVE_DATABASE_URL = "YOUR_COCKROACHDB_CONNECTION_STRING"
$env:DOCWEAVE_WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
$env:DOCWEAVE_TAXONOMY_VERSION_ID = "22222222-2222-4222-8222-222222222222"
$env:DOCWEAVE_APPROVED_BY_ACTOR_ID = "33333333-3333-4333-8333-333333333333"
$env:DOCWEAVE_CLASSIFICATION_PROMPT_VERSION = "docweave.classification.v1"
$env:AWS_PROFILE = "YOUR_AWS_PROFILE"
$env:AWS_DEFAULT_REGION = "eu-central-1"
```

The three example Universally Unique Identifiers (UUIDs) are safe demo
identifiers. Use stable UUIDs of your own for a separate workspace.

### 3.4 Create the six-table memory schema

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-schema.exe --flat
```

Expected tables:

```text
docweave.documents
docweave.agent_runs
docweave.proposals
docweave.human_decisions
docweave.file_history
docweave.document_relationships
```

The migration is idempotent. Do not run `alembic downgrade` against a database
containing results you need: the downgrade removes the entire `docweave`
schema.

## 4. Configure AWS And Amazon Bedrock For Local Analysis

### 4.1 Authenticate without static keys

Use a short-lived AWS CLI profile. Depending on your AWS organization, use
AWS IAM Identity Center or the browser-based AWS CLI login configured for the
account. Then verify the active identity:

```powershell
aws sts get-caller-identity --profile $env:AWS_PROFILE
```

Do not place AWS access keys in `.env.example`, source code, launcher files, or
GitHub secrets intended for public forks.

### 4.2 Verify Bedrock access

1. Open the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/).
2. Switch the region to **Europe (Frankfurt), `eu-central-1`**.
3. Open **Model catalog** and locate Amazon Nova 2 Lite.
4. Confirm that the authenticated identity can invoke the model. Some accounts
   enable model access automatically; account and Marketplace permissions can
   still block invocation.

The desktop application intentionally uses this fixed inference profile:

```text
eu.amazon.nova-2-lite-v1:0
```

The identity needs `bedrock:InvokeModel` for that model or inference profile.
The exact Identity and Access Management (IAM) policy depends on your account;
grant only the required action and resource where your Bedrock setup supports
resource-level scoping.

Run the local preflight:

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
```

`bedrock_client: ok` proves that the client can be constructed. The definitive
model test is analyzing one synthetic PDF in the dashboard and receiving a
proposal without an authentication, access, or transport error.

## 5. Run And Test The Desktop Application

Start DocWeave from the same PowerShell window that contains the variables:

```powershell
.\.venv\Scripts\docweave-desktop.exe
```

Recommended first test:

1. Click **Choose** and select `pdf_sintetici` or a small copy of it.
2. Click **Scan**.
3. Click **Analyze** and wait for the batch counter to finish.
4. Click **Approve** to inspect original names, proposed names, and suggested
   directories.
5. Approve selected rows or the complete batch.
6. Confirm that files moved under `DocWeave Organized`.
7. Click **Restore**, select individual rows or all rows, and restore them.
8. Run the memory evidence command:

```powershell
.\.venv\Scripts\docweave-memory-evidence.exe
```

The application never renames or moves a PDF before an explicit human
approval. Test with the synthetic corpus before using personal documents.

## 6. Deploy The Optional AWS Cloud Slice

This deployment creates:

- Amazon S3 buckets for deployment and document artifacts;
- Amazon Simple Queue Service (SQS) analysis and dead-letter queues;
- two AWS Lambda functions;
- an Amazon API Gateway HTTP API;
- Amazon CloudWatch log groups;
- IAM roles that permit S3, SQS, logging, and Bedrock invocation;
- a CloudFormation dynamic reference to a CockroachDB connection secret.

The cloud API analyzes uploaded artifacts asynchronously. File approval,
renaming, moving, and restore remain human-controlled desktop operations.

This is a hackathon demonstration stack, not a production perimeter. Its HTTP
API has throttling but no user authentication. Deploy it only in a controlled
test account with synthetic PDFs, and remove it when testing is complete.

The template also uses standard Lambda networking and does not create a Virtual
Private Cloud (VPC), Network Address Translation (NAT) gateway, fixed outbound
IP address, or CockroachDB private connection. It therefore assumes that the
CockroachDB public endpoint is reachable with TLS and database authentication.
If your CockroachDB plan requires a fixed allowlisted source, add controlled
VPC egress or private connectivity before expecting the cloud worker to persist
memory. The desktop can still use a narrow allowlist entry for your local IP.

### 6.1 Verify the deployment identity

```powershell
aws sts get-caller-identity --profile $env:AWS_PROFILE
```

The deployment identity must be able to create the listed services and pass
the CloudFormation-created Lambda role. Deploy into `eu-central-1` so the
configured Nova inference profile remains valid.

### 6.2 Store the CockroachDB URL in AWS Secrets Manager

Open [AWS Secrets Manager](https://console.aws.amazon.com/secretsmanager/) in
`eu-central-1`, choose **Store a new secret**, then:

1. Select **Other type of secret**.
2. Add one JSON key named `database_url`.
3. Paste the CockroachDB `docweave` connection string as its value.
4. Use an appropriate AWS Key Management Service (KMS) key, restrict secret
   access to deployment/runtime administrators, and name the secret, for
   example `docweave/dev/cockroachdb`.
5. Copy only the secret Amazon Resource Name (ARN), never its value.

Automatic rotation is not configured by this repository because CockroachDB
Cloud credential rotation requires a coordinated password update. Rotate the
SQL password and secret together according to your own lifecycle policy.

In PowerShell, store the non-secret ARN:

```powershell
$env:DOCWEAVE_COCKROACHDB_SECRET_ARN = "YOUR_SECRET_ARN"
```

The CloudFormation template resolves the `database_url` JSON key during stack
deployment. It does not print the connection string or commit it to source.

### 6.3 Build the Lambda package

The Lambda functions use Python 3.12 on the ARM64 architecture. The packaging
script downloads matching Linux binary wheels and creates one ZIP package:

```powershell
.\scripts\package-aws-lambda.ps1
Test-Path .\dist\docweave-cloud-api.zip
```

### 6.4 Create the private deployment-artifact bucket

```powershell
aws cloudformation deploy `
  --stack-name docweave-artifacts `
  --template-file .\infrastructure\aws\docweave-artifact-bucket.template.json `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE

$ArtifactBucket = aws cloudformation describe-stacks `
  --stack-name docweave-artifacts `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE `
  --query "Stacks[0].Outputs[?OutputKey=='DeploymentArtifactBucketName'].OutputValue" `
  --output text

aws s3 cp .\dist\docweave-cloud-api.zip `
  "s3://$ArtifactBucket/docweave-cloud-api.zip" `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE
```

### 6.5 Deploy the application stack

```powershell
aws cloudformation deploy `
  --stack-name docweave-cloud-dev `
  --template-file .\infrastructure\aws\docweave-cloud-foundation.template.json `
  --capabilities CAPABILITY_IAM `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE `
  --parameter-overrides `
    StageName=dev `
    LambdaCodeS3Bucket=$ArtifactBucket `
    LambdaCodeS3Key=docweave-cloud-api.zip `
    BedrockModelId=eu.amazon.nova-2-lite-v1:0 `
    CockroachDbSecretArn=$env:DOCWEAVE_COCKROACHDB_SECRET_ARN
```

Obtain the generated API URL:

```powershell
$CloudApiUrl = aws cloudformation describe-stacks `
  --stack-name docweave-cloud-dev `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE `
  --query "Stacks[0].Outputs[?OutputKey=='CloudApiUrl'].OutputValue" `
  --output text

$env:DOCWEAVE_CLOUD_API_URL = $CloudApiUrl
Invoke-RestMethod "$CloudApiUrl/health"
```

Expected health fields include:

```text
aws_lambda: running
amazon_bedrock: configured
amazon_s3: configured
amazon_sqs: configured
cockroachdb_secret: configured
```

These are configuration/readiness signals. A complete cloud proof requires an
uploaded PDF, a queued analysis job, a Bedrock result artifact in S3, and
persisted proposal records in CockroachDB.

### 6.6 Inspect logs and queue wiring

```powershell
aws lambda list-event-source-mappings `
  --function-name docweave-cloud-dev-analysis-worker `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE

aws logs tail /aws/lambda/docweave-cloud-dev-analysis-worker `
  --since 10m `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE
```

CloudWatch logs must not contain database URLs, passwords, or unnecessary PDF
content.

## 7. Optional CockroachDB Tool Evidence

Authenticate `ccloud` through its browser flow and run the repository evidence
script:

```powershell
ccloud auth login
.\scripts\cockroachdb-tool-evidence.ps1 -ClusterId "YOUR_CLUSTER_ID"
```

Copy the cluster ID from its CockroachDB Cloud overview or URL. The script
inspects that live cluster and records the pinned CockroachDB Agent Skills
revision used by the project. It is competition evidence, not a requirement
for the dashboard's normal runtime.

## 8. Troubleshooting

### `cockroachdb_connection: failed`

- Confirm the URL targets the `docweave` database.
- Re-open the CockroachDB **Connect** dialog and check the IP allowlist.
- Preserve `sslmode=verify-full` and any CA certificate parameter.
- Percent-encode special password characters in the URI.

### Bedrock login or transport failure

- Verify the AWS profile with `aws sts get-caller-identity`.
- Confirm the region is `eu-central-1`.
- Confirm the identity can invoke `eu.amazon.nova-2-lite-v1:0`.
- Re-authenticate when short-lived credentials expire, then press the Bedrock
  button again.

### `AccessDeniedException` during deployment

The deployment principal is missing permission for CloudFormation, IAM role
creation/pass-role, Lambda, S3, SQS, API Gateway, CloudWatch Logs, Bedrock, or
the selected KMS/Secrets Manager resources. Review the failed CloudFormation
event before changing permissions.

### Cloud worker runs but does not persist memory

- Confirm the secret is in `eu-central-1` and its JSON key is exactly
  `database_url`.
- Confirm the connection URL targets a migrated `docweave` database.
- Confirm CockroachDB network authorization permits the AWS Lambda connection
  path. A local-only IP allowlist can allow the desktop while blocking Lambda.
- Inspect the worker CloudWatch log without printing the secret.

## 9. Remove Test Resources

Deleting cloud resources is irreversible and can remove test artifacts. Export
anything you need first. The templates retain selected S3 buckets and log
groups intentionally, so deleting the stacks may not remove every billable
resource.

After confirming the target AWS account, region, and stack names, remove the
application stack first and then inspect retained resources manually:

```powershell
aws cloudformation delete-stack `
  --stack-name docweave-cloud-dev `
  --region eu-central-1 `
  --profile $env:AWS_PROFILE
```

Only delete the artifact stack after its retained bucket is empty and no longer
needed. Delete or schedule deletion of the Secrets Manager secret and any
customer-managed KMS key only under your own retention policy.

## 10. Final Verification Checklist

- `docweave-runtime-preflight --database` reports runtime, Bedrock client, and
  CockroachDB readiness.
- `docweave-memory-schema --flat` reports exactly six DocWeave tables.
- A real synthetic PDF produces a Bedrock proposal.
- No file changes before human approval.
- Approved files move into readable content-based folders.
- Restore returns selected files to their original names and directories.
- CockroachDB records documents, agent runs, proposals, human decisions, and
  file history.
- The optional cloud `/health` endpoint reports all configured services.
- CloudWatch and repository history contain no credentials.

For the shorter judge workflow, see
[`submission/testing-instructions.md`](submission/testing-instructions.md).
