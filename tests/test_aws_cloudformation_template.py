from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "aws"
    / "docweave-cloud-foundation.template.json"
)
ARTIFACT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "aws"
    / "docweave-artifact-bucket.template.json"
)


def _template() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")))


def _artifact_template() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(ARTIFACT_TEMPLATE_PATH.read_text(encoding="utf-8")),
    )


def test_template_declares_required_aws_services() -> None:
    resources = _template()["Resources"]

    assert resources["DocumentArtifactBucket"]["Type"] == "AWS::S3::Bucket"
    assert resources["AnalysisQueue"]["Type"] == "AWS::SQS::Queue"
    assert resources["CloudApiFunction"]["Type"] == "AWS::Lambda::Function"
    assert resources["AnalysisWorkerFunction"]["Type"] == "AWS::Lambda::Function"
    assert resources["HttpApi"]["Type"] == "AWS::ApiGatewayV2::Api"
    assert resources["CloudApiLogGroup"]["Type"] == "AWS::Logs::LogGroup"
    assert resources["AnalysisWorkerLogGroup"]["Type"] == "AWS::Logs::LogGroup"


def test_document_bucket_is_private_encrypted_versioned_and_retained() -> None:
    bucket = _template()["Resources"]["DocumentArtifactBucket"]
    properties = bucket["Properties"]

    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"
    assert properties["VersioningConfiguration"]["Status"] == "Enabled"
    assert properties["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert properties["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }


def test_lambda_role_limits_service_permissions_to_docweave_resources() -> None:
    role = _template()["Resources"]["CloudApiRole"]
    statements = role["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]

    actions = {
        action
        for statement in statements
        for action in (
            statement["Action"]
            if isinstance(statement["Action"], list)
            else [statement["Action"]]
        )
    }
    assert "s3:PutObject" in actions
    assert "sqs:SendMessage" in actions
    assert "bedrock:InvokeModel" in actions
    assert "iam:*" not in actions
    assert "s3:*" not in actions
    assert "sqs:*" not in actions


def test_api_routes_expose_health_upload_and_analysis_job_boundaries() -> None:
    resources = _template()["Resources"]

    assert resources["HealthRoute"]["Properties"]["RouteKey"] == "GET /health"
    assert (
        resources["PresignRoute"]["Properties"]["RouteKey"] == "POST /uploads/presign"
    )
    assert (
        resources["AnalysisJobRoute"]["Properties"]["RouteKey"] == "POST /analysis-jobs"
    )


def test_artifact_bucket_template_is_private_encrypted_versioned_and_retained() -> None:
    bucket = _artifact_template()["Resources"]["DeploymentArtifactBucket"]
    properties = bucket["Properties"]

    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"
    assert properties["VersioningConfiguration"]["Status"] == "Enabled"
    assert properties["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert properties["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
