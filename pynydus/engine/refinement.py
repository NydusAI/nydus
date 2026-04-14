"""LLM refinement for spawning and hatching pipelines.

Spawning (Step 7): ``refine_skills`` / ``refine_memory`` use the configured
LLM tier to deduplicate memory records and normalize skill formatting.
The LLM always operates on already-redacted content.

Hatching (Step 3): ``refine_hatch`` uses the same tier to adapt or polish
reconstructed files for the target platform's conventions.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from pynydus.api.schemas import (
    AgentSkill,
    Egg,
    EggPartial,
    MemoryModule,
    MemoryRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.llm import LLMTierConfig, create_completion

logger = logging.getLogger(__name__)

REFINEMENT_RETRY_LIMIT = 3

_PLACEHOLDER_RE = re.compile(r"\{\{(?:SECRET|PII)_\d+\}\}")


def _extract_placeholders(text: str) -> set[str]:
    """Return all ``{{SECRET_NNN}}`` / ``{{PII_NNN}}`` tokens in *text*."""
    return set(_PLACEHOLDER_RE.findall(text))


def _find_missing_placeholders(original: str, new: str) -> set[str]:
    """Tokens present in *original* but absent from *new*."""
    return _extract_placeholders(original) - _extract_placeholders(new)


# ---------------------------------------------------------------------------
# Response models: structured output schemas for Instructor
# ---------------------------------------------------------------------------


class RefinedMemoryRecord(BaseModel):
    """A single refined memory record returned by the LLM."""

    original_ids: list[str]
    """IDs of the original records this was derived from (multiple if merged)."""

    text: str
    """The cleaned/deduplicated/summarized text."""

    label: MemoryLabel | None = None
    """Preserved label from the original record."""


class RefinedMemoryOutput(BaseModel):
    """LLM response for memory deduplication and summarization."""

    records: list[RefinedMemoryRecord]
    """The refined set of memory records. Fewer or equal to the input count."""


class RefinedSkillRecord(BaseModel):
    """A single refined skill record returned by the LLM."""

    original_id: str
    """ID of the original skill this corresponds to."""

    name: str
    """Cleaned/normalized skill name."""

    content: str
    """Cleaned/reformatted skill content."""


class RefinedSkillsOutput(BaseModel):
    """LLM response for skill cleanup."""

    skills: list[RefinedSkillRecord]
    """The refined skills. Same count as input (1:1, no merging)."""


class AdaptedFile(BaseModel):
    """A single file whose content has been adapted for the target platform."""

    path: str
    """Relative path of the file (must match an entry in files_created)."""

    content: str
    """The adapted file content."""


class AdaptedFilesOutput(BaseModel):
    """LLM response for cross-platform file adaptation."""

    files: list[AdaptedFile]
    """Adapted file contents. Only includes files that needed changes."""

    warnings: list[str] = Field(default_factory=list)
    """Any warnings about adaptation issues."""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_MEMORY_SYSTEM_PROMPT = """\
You are a memory deduplication and summarization engine for an AI agent migration system.
You receive a list of memory records extracted from an AI agent. Your task:
1. Identify duplicate or near-duplicate records and merge them into a single record.
2. Identify records that convey overlapping information and combine them.
3. Preserve the meaning and label of every record. Never change a record's label.
4. Keep records concise. If a record is excessively verbose, summarize it while \
preserving all factual content.
5. For merged records, list ALL original IDs in original_ids. \
For records kept as-is, list just the one ID.
6. Never invent new information. Only condense what exists.
7. CRITICAL: NEVER remove, rewrite, paraphrase, or substitute redaction placeholder \
tokens ({{SECRET_NNN}} or {{PII_NNN}}). Every such token that appears in the input \
MUST appear character-for-character in your output. If you are unsure whether to \
keep a token, keep it."""

_SKILL_SYSTEM_PROMPT = """\
You are a skill cleanup engine for an AI agent migration system.
You receive a list of skill records extracted from an AI agent. Your task:
1. Clean up the skill name: normalize casing, remove redundant prefixes/suffixes, \
make it a clear human-readable title.
2. Clean up the content: fix formatting inconsistencies, remove trailing whitespace, \
normalize markdown heading levels, ensure code blocks are properly fenced.
3. Do NOT remove skills. Return exactly one output per input skill.
4. Do NOT change the semantic meaning of any skill content.
5. CRITICAL: NEVER remove, rewrite, paraphrase, or substitute redaction placeholder \
tokens ({{SECRET_NNN}} or {{PII_NNN}}). Every such token that appears in the input \
MUST appear character-for-character in your output. If you are unsure whether to \
keep a token, keep it."""

_HATCH_SYSTEM_PROMPT = """\
You are a cross-platform adaptation engine for an AI agent migration system.
An agent was originally built for {source_type} and has been mechanically \
reconstructed for {target_type}.
Your task is to adapt the generated files so they follow the idiomatic conventions \
and best practices of the target platform.

Source platform specification:
{source_spec}

Target platform specification:
{target_spec}

Adaptation rules:
1. Adjust tone and structure to match target platform idioms.
2. Do NOT alter factual content or the agent's personality/knowledge.
3. CRITICAL: NEVER remove, rewrite, paraphrase, or substitute redaction placeholder \
tokens ({{SECRET_NNN}} or {{PII_NNN}}). Every such token that appears in an input \
file MUST appear character-for-character in your output for that file. If you are \
unsure whether to keep a token, keep it.
4. Only return files that you actually changed. If a file needs no adaptation, omit it."""

_HATCH_POLISH_PROMPT = """\
You are a polishing engine for an AI agent migration system.
An agent built for {target_type} has been reconstructed for the same platform.
Your task is to polish and improve the generated files so they follow the \
idiomatic conventions and best practices of {target_type}.

Platform specification:
{target_spec}

Polishing rules:
1. Fix formatting inconsistencies: normalize headings, whitespace, and structure.
2. Improve clarity and readability without changing meaning.
3. Ensure the output follows {target_type} conventions precisely.
4. Do NOT alter factual content or the agent's personality/knowledge.
5. CRITICAL: NEVER remove, rewrite, paraphrase, or substitute redaction placeholder \
tokens ({{SECRET_NNN}} or {{PII_NNN}}). Every such token that appears in an input \
file MUST appear character-for-character in your output for that file. If you are \
unsure whether to keep a token, keep it.
6. Only return files that you actually changed. If a file needs no polishing, omit it."""


# ---------------------------------------------------------------------------
# AGENT_SPEC.md loader
# ---------------------------------------------------------------------------

_AGENT_SPEC_DIR = Path(__file__).parent.parent / "agents"


def _load_agent_spec(agent_type: AgentType) -> str:
    """Load the AGENT_SPEC.md for a given agent type."""
    spec_path = _AGENT_SPEC_DIR / agent_type.value / "AGENT_SPEC.md"
    if spec_path.exists():
        return spec_path.read_text()
    return f"No specification available for {agent_type.value}."


# ---------------------------------------------------------------------------
# Standalone refinement helpers (used by pipeline Step 7)
# ---------------------------------------------------------------------------


def refine_skills(
    skills: SkillsModule,
    llm_config: LLMTierConfig,
    spawn_log: list[dict] | None = None,
) -> SkillsModule:
    """Clean up skill names and formatting via the configured LLM tier.

    Args:
        skills: Module containing skill records to refine.
        llm_config: LLM provider, model, and API key.
        spawn_log: If set, refinement log entries are appended here.

    Returns:
        Updated SkillsModule with cleaned names and formatting.
    """
    from pynydus.api.schemas import MemoryModule

    partial = EggPartial(skills=skills, memory=MemoryModule())
    partial = _refine_skills(partial, llm_config)
    if spawn_log is not None:
        spawn_log.extend(partial.spawn_log)
    return partial.skills


def refine_memory(
    memory: MemoryModule,
    llm_config: LLMTierConfig,
    spawn_log: list[dict] | None = None,
) -> MemoryModule:
    """Deduplicate and summarize memory records via the configured LLM tier.

    Args:
        memory: Module containing memory records to refine.
        llm_config: LLM provider, model, and API key.
        spawn_log: If set, refinement log entries are appended here.

    Returns:
        Updated MemoryModule with deduplicated/summarized records.
    """
    partial = EggPartial(skills=SkillsModule(), memory=memory)
    partial = _refine_memory(partial, llm_config)
    if spawn_log is not None:
        spawn_log.extend(partial.spawn_log)
    return partial.memory


def _refine_memory(partial: EggPartial, llm_config: LLMTierConfig) -> EggPartial:
    """Deduplicate and summarize memory records via LLM.

    Args:
        partial: EggPartial whose memory module will be refined in place.
        llm_config: LLM provider, model, and API key.

    Returns:
        The same EggPartial with its memory module updated.
    """
    records = partial.memory.memory
    lookup: dict[str, MemoryRecord] = {r.id: r for r in records}

    serialized = json.dumps(
        [{"id": r.id, "text": r.text, "label": r.label} for r in records],
        indent=2,
    )

    system_prompt = _MEMORY_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Here are the memory records to refine:\n\n"
                f"{serialized}\n\n"
                "Return the deduplicated and summarized records."
            ),
        },
    ]

    result = create_completion(
        llm_config,
        messages=messages,
        response_model=RefinedMemoryOutput,
        log=partial.spawn_log,
    )
    if result is None:
        return partial

    # Rebuild memory list from LLM output
    new_memory: list[MemoryRecord] = []
    merge_counter = 0

    for refined in result.records:
        # Find the first valid original to copy metadata from
        source_record = None
        for oid in refined.original_ids:
            if oid in lookup:
                source_record = lookup[oid]
                break

        if source_record is None:
            logger.warning(
                "Refined record references unknown IDs %s, skipping", refined.original_ids
            )
            continue

        # Determine ID
        if len(refined.original_ids) == 1 and refined.original_ids[0] in lookup:
            record_id = refined.original_ids[0]
            partial.spawn_log.append(
                {
                    "type": "memory_refined",
                    "record_id": record_id,
                    "text_changed": refined.text != lookup[record_id].text,
                    "original_length": len(lookup[record_id].text),
                    "refined_length": len(refined.text),
                }
            )
        else:
            merge_counter += 1
            record_id = f"mem_merged_{merge_counter:03d}"
            partial.spawn_log.append(
                {
                    "type": "memory_merge",
                    "merged_ids": refined.original_ids,
                    "result_id": record_id,
                    "original_texts_length": [
                        len(lookup[oid].text) for oid in refined.original_ids if oid in lookup
                    ],
                    "result_text_length": len(refined.text),
                }
            )

        original_texts = [lookup[oid].text for oid in refined.original_ids if oid in lookup]
        required_placeholders: set[str] = set()
        for ot in original_texts:
            required_placeholders |= _extract_placeholders(ot)
        missing = required_placeholders - _extract_placeholders(refined.text)

        safe_text = refined.text
        if missing:
            safe_text = source_record.text
            logger.warning(
                "Memory record %s dropped placeholders %s. Keeping original text",
                record_id,
                sorted(missing),
            )
            partial.spawn_log.append(
                {
                    "type": "memory_placeholder_revert",
                    "record_id": record_id,
                    "missing_placeholders": sorted(missing),
                }
            )

        new_record = source_record.model_copy(
            update={
                "id": record_id,
                "text": safe_text,
                "label": refined.label or source_record.label,
            }
        )
        new_memory.append(new_record)

    partial.spawn_log.append(
        {
            "type": "memory_refinement_done",
            "input_count": len(records),
            "output_count": len(new_memory),
            "merges": merge_counter,
        }
    )

    partial.memory.memory = new_memory
    return partial


def _refine_skills(partial: EggPartial, llm_config: LLMTierConfig) -> EggPartial:
    """Clean up skill names and formatting via LLM.

    Args:
        partial: EggPartial whose skills module will be refined in place.
        llm_config: LLM provider, model, and API key.

    Returns:
        The same EggPartial with its skills module updated.
    """
    skills = partial.skills.skills
    lookup: dict[str, AgentSkill] = {s.metadata.get("id", s.name): s for s in skills}

    serialized = json.dumps(
        [
            {"id": s.metadata.get("id", s.name), "name": s.name, "content": s.body}
            for s in skills
        ],
        indent=2,
    )

    system_prompt = _SKILL_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Here are the skill records to clean up:\n\n"
                f"{serialized}\n\n"
                "Return the cleaned skills, one per input."
            ),
        },
    ]

    result = create_completion(
        llm_config,
        messages=messages,
        response_model=RefinedSkillsOutput,
        log=partial.spawn_log,
    )
    if result is None:
        return partial

    # Update skills from LLM output
    new_skills: list[AgentSkill] = []
    for refined in result.skills:
        original = lookup.get(refined.original_id)
        if original is None:
            logger.warning("Refined skill references unknown ID %s, skipping", refined.original_id)
            continue

        missing = _find_missing_placeholders(original.body, refined.content)
        safe_content = refined.content
        if missing:
            safe_content = original.body
            logger.warning(
                "Skill %s dropped placeholders %s. Keeping original content",
                refined.original_id,
                sorted(missing),
            )
            partial.spawn_log.append(
                {
                    "type": "skill_placeholder_revert",
                    "skill_id": refined.original_id,
                    "missing_placeholders": sorted(missing),
                }
            )

        partial.spawn_log.append(
            {
                "type": "skill_refined",
                "skill_id": refined.original_id,
                "name_changed": refined.name != original.name,
                "old_name": original.name,
                "new_name": refined.name,
                "content_changed": safe_content != original.body,
            }
        )

        new_skill = original.model_copy(
            update={
                "name": refined.name,
                "body": safe_content,
            }
        )
        new_skills.append(new_skill)

    partial.spawn_log.append(
        {
            "type": "skill_refinement_done",
            "input_count": len(skills),
            "output_count": len(new_skills),
        }
    )

    partial.skills.skills = new_skills
    return partial


# ---------------------------------------------------------------------------
# refine_hatch: hatching Step 3
# ---------------------------------------------------------------------------


def refine_hatch(
    file_dict: dict[str, str],
    egg: Egg,
    llm_config: LLMTierConfig,
    *,
    target: str | None = None,
    log: list[dict] | None = None,
    spawn_log: list[dict] | None = None,
    raw_artifacts: dict[str, str] | None = None,
) -> dict[str, str]:
    """Adapt or polish reconstructed files during hatching (Step 3) via LLM.

    Operates on a filename-to-content mapping with placeholders only. no disk I/O.
    Retries when redaction placeholders are dropped. on persistent failure, leaves
    affected paths unchanged.

    Args:
        file_dict: Reconstructed files (paths relative to output root).
        egg: Egg being hatched (manifest, secrets metadata, agent type).
        llm_config: LLM provider, model, and API key.
        target: Explicit target platform type (e.g. "openclaw").
        log: If set, hatch log entries (warnings, reverts) are appended here.
        spawn_log: Optional spawn pipeline log forwarded into the LLM context.
        raw_artifacts: Optional redacted ``raw/`` snapshot for extra LLM context.

    Returns:
        Updated file dict (unchanged keys omitted from LLM output stay as in
        ``file_dict``).

    """
    if not file_dict:
        return file_dict

    source_type = egg.manifest.agent_type
    target_type = AgentType(target) if target else None
    same_platform = target_type is not None and source_type == target_type

    file_listing = ""
    for path, content in file_dict.items():
        file_listing += f"--- {path} ---\n{content}\n\n"

    target_spec = _load_agent_spec(target_type) if target_type else ""

    if same_platform:
        system_prompt = _HATCH_POLISH_PROMPT.format(
            target_type=target_type,
            target_spec=target_spec,
        )
    else:
        source_spec = _load_agent_spec(source_type)
        system_prompt = _HATCH_SYSTEM_PROMPT.format(
            source_type=source_type,
            target_type=target_type,
            source_spec=source_spec,
            target_spec=target_spec,
        )

    log_entries = spawn_log or []
    serialized_log = json.dumps(log_entries, indent=2, default=str) if log_entries else ""
    context_block = ""
    if serialized_log:
        context_block = f"\nSpawn log:\n{serialized_log}\n\n"

    raw_block = ""
    if raw_artifacts:
        raw_listing = ""
        for name, content in raw_artifacts.items():
            raw_listing += f"--- raw/{name} ---\n{content}\n\n"
        raw_block = f"Original source files (redacted):\n\n{raw_listing}"

    secrets_block = ""
    if egg.secrets.secrets:
        secret_lines = []
        for s in egg.secrets.secrets:
            secret_lines.append(
                f"  - {s.placeholder}: {s.kind.value}, {s.name}"
                + (f" ({s.description})" if s.description else "")
            )
        secrets_block = "Redaction placeholders in this egg:\n" + "\n".join(secret_lines) + "\n\n"

    action_verb = "Polish" if same_platform else "Adapt"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Source platform: {source_type}\n"
                f"Target platform: {target_type}\n"
                f"{context_block}"
                f"{secrets_block}"
                f"{raw_block}"
                f"Here are the reconstructed files:\n\n{file_listing}"
                f"{action_verb} these files for the {target_type} platform. "
                "Only return files you changed."
            ),
        },
    ]

    valid_files = set(file_dict)
    last_adapted: list[AdaptedFile] = []
    last_warnings: list[str] = []

    for attempt in range(REFINEMENT_RETRY_LIMIT):
        llm_result = create_completion(
            llm_config,
            messages=messages,
            response_model=AdaptedFilesOutput,
            log=log,
        )
        if llm_result is None:
            return file_dict

        last_adapted = [a for a in llm_result.files if a.path in valid_files]
        last_warnings = list(llm_result.warnings)

        violations: dict[str, set[str]] = {}
        for adapted in last_adapted:
            missing = _find_missing_placeholders(file_dict[adapted.path], adapted.content)
            if missing:
                violations[adapted.path] = missing

        if not violations:
            break

        if attempt < REFINEMENT_RETRY_LIMIT - 1:
            violation_lines = " | ".join(
                f"{path}: {sorted(tokens)}" for path, tokens in violations.items()
            )
            logger.warning(
                "Hatch refinement attempt %d/%d dropped placeholders: %s",
                attempt + 1,
                REFINEMENT_RETRY_LIMIT,
                violation_lines,
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous output dropped required redaction placeholders. "
                        f"Missing tokens: {violation_lines}. "
                        "Retry and preserve every {{SECRET_NNN}} / {{PII_NNN}} token "
                        "character-for-character."
                    ),
                }
            )

    result = dict(file_dict)
    for adapted in last_adapted:
        missing = _find_missing_placeholders(file_dict[adapted.path], adapted.content)
        if missing:
            logger.warning(
                "Reverting %s after %d attempts: missing %s",
                adapted.path,
                REFINEMENT_RETRY_LIMIT,
                sorted(missing),
            )
            if log is not None:
                log.append(
                    {
                        "type": "placeholder_revert",
                        "path": adapted.path,
                        "missing_placeholders": sorted(missing),
                        "attempts": REFINEMENT_RETRY_LIMIT,
                    }
                )
        else:
            result[adapted.path] = adapted.content

    if log is not None:
        for warning in last_warnings:
            log.append({"type": "warning", "message": warning})

    return result


