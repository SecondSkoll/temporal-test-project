from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from models import (
    DOC_SECTIONS,
    DocGenRequest,
    DocGenResult,
    EmitSummaryInput,
    GenerateSectionRequest,
    GeneratedDoc,
    PersistArtifactsInput,
    PersistArtifactsResult,
    RepoInventory,
)


@workflow.defn
class DocumentationWorkflow:
    @workflow.run
    async def run(self, request: DocGenRequest) -> DocGenResult:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=5,
        )

        validated = await workflow.execute_activity(
            "validate_request_activity",
            request,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )
        if isinstance(validated, dict):
            validated_repo_url = validated["repo_url"]
            validated_max_files = int(validated.get("max_files", 300))
        else:
            validated_repo_url = validated.repo_url
            validated_max_files = int(validated.max_files)

        repo_path = await workflow.execute_activity(
            "fetch_repo_activity",
            validated,
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=retry_policy,
        )

        inventory: RepoInventory = await workflow.execute_activity(
            "inventory_repo_activity",
            args=[repo_path, validated_max_files],
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=retry_policy,
        )

        context: str = await workflow.execute_activity(
            "build_prompt_context_activity",
            inventory,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry_policy,
        )

        docs: list[GeneratedDoc] = []
        for file_name, instruction in DOC_SECTIONS.items():
            generated: GeneratedDoc = await workflow.execute_activity(
                "generate_doc_section_activity",
                GenerateSectionRequest(
                    file_name=file_name,
                    instruction=instruction,
                    context=context,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry_policy,
            )
            docs.append(generated)

        warnings = await workflow.execute_activity(
            "validate_docs_activity",
            docs,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        persisted: PersistArtifactsResult = await workflow.execute_activity(
            "persist_artifacts_activity",
            PersistArtifactsInput(
                repo_url=validated_repo_url,
                docs=docs,
                warnings=warnings,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry_policy,
        )

        final_warnings = await workflow.execute_activity(
            "emit_summary_activity",
            EmitSummaryInput(
                repo_url=validated_repo_url,
                generated_files=persisted.generated_files,
                warnings=warnings,
            ),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=retry_policy,
        )

        return DocGenResult(
            run_id=workflow.info().run_id,
            repo_url=validated_repo_url,
            artifact_path=persisted.artifact_path,
            generated_files=persisted.generated_files,
            warnings=final_warnings,
        )
