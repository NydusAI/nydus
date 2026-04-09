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
from pathlib import Path

from pydantic import BaseModel, Field

from pynydus.api.schemas import (
    Egg,
    EggPartial,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.llm import LLMTierConfig, create_completion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response models — structured output schemas for Instructor
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
7. Preserve any placeholder tokens like {{SECRET_001}} or {{PII_001}} exactly as-is."""

_SKILL_SYSTEM_PROMPT = """\
You are a skill cleanup engine for an AI agent migration system.
You receive a list of skill records extracted from an AI agent. Your task:
1. Clean up the skill name: normalize casing, remove redundant prefixes/suffixes, \
make it a clear human-readable title.
2. Clean up the content: fix formatting inconsistencies, remove trailing whitespace, \
normalize markdown heading levels, ensure code blocks are properly fenced.
3. Do NOT remove skills. Return exactly one output per input skill.
4. Do NOT change the semantic meaning of any skill content.
5. Preserve any placeholder tokens like {{SECRET_001}} or {{PII_001}} exactly as-is."""

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
3. Do NOT modify secret placeholders like {{SECRET_001}} or {{PII_001}}.
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
5. Do NOT modify secret placeholders like {{SECRET_001}} or {{PII_001}}.
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
    """Standalone skill refinement — delegates to _refine_skills via EggPartial."""
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
    """Standalone memory refinement — delegates to _refine_memory via EggPartial."""
    partial = EggPartial(skills=SkillsModule(), memory=memory)
    partial = _refine_memory(partial, llm_config)
    if spawn_log is not None:
        spawn_log.extend(partial.spawn_log)
    return partial.memory


def _refine_memory(partial: EggPartial, llm_config: LLMTierConfig) -> EggPartial:
    """Deduplicate and summarize memory records via LLM."""
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

        new_record = source_record.model_copy(
            update={
                "id": record_id,
                "text": refined.text,
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
    """Clean up skill names and formatting via LLM."""
    skills = partial.skills.skills
    lookup: dict[str, SkillRecord] = {s.id: s for s in skills}

    serialized = json.dumps(
        [{"id": s.id, "name": s.name, "content": s.content} for s in skills],
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
    new_skills: list[SkillRecord] = []
    for refined in result.skills:
        original = lookup.get(refined.original_id)
        if original is None:
            logger.warning("Refined skill references unknown ID %s, skipping", refined.original_id)
            continue

        partial.spawn_log.append(
            {
                "type": "skill_refined",
                "skill_id": refined.original_id,
                "name_changed": refined.name != original.name,
                "old_name": original.name,
                "new_name": refined.name,
                "content_changed": refined.content != original.content,
            }
        )

        new_skill = original.model_copy(
            update={
                "name": refined.name,
                "content": refined.content,
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
# refine_hatch — hatching Step 3
# ---------------------------------------------------------------------------


def _serialize_spawn_log(spawn_log: list[dict]) -> str:
    """Serialize the full spawn log as JSON for inclusion in the hatch LLM prompt.

    Returns the complete, unfiltered log so the LLM can decide what is relevant.
    """
    if not spawn_log:
        return ""
    return json.dumps(spawn_log, indent=2, default=str)


def refine_hatch(
    file_dict: dict[str, str],
    egg: Egg,
    llm_config: LLMTierConfig,
    *,
    log: list[dict] | None = None,
    spawn_log: list[dict] | None = None,
    raw_artifacts: dict[str, str] | None = None,
) -> dict[str, str]:
    """Step 3: LLM refinement during hatching.

    Operates on a file dict (filename -> content) and returns the
    updated dict.  No disk I/O — the pipeline handles writing.

    Uses the configured LLM tier to adapt or polish reconstructed files for the
    target platform's conventions.

    If the LLM call fails, the original file dict is returned unchanged.
    """
    if not file_dict:
        return file_dict

    source_type = egg.manifest.agent_type
    target_type = _infer_target_type(file_dict)
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

    serialized_log = _serialize_spawn_log(spawn_log or [])
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
                + (f" — {s.description}" if s.description else "")
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

    llm_result = create_completion(
        llm_config,
        messages=messages,
        response_model=AdaptedFilesOutput,
        log=log,
    )
    if llm_result is None:
        return file_dict

    valid_files = set(file_dict)
    result = dict(file_dict)
    for adapted in llm_result.files:
        if adapted.path not in valid_files:
            logger.warning("LLM returned unknown file path %s, ignoring", adapted.path)
            continue
        result[adapted.path] = adapted.content

    if log is not None:
        for warning in llm_result.warnings:
            log.append({"type": "warning", "message": warning})

    return result


def _infer_target_type(file_dict: dict[str, str]) -> AgentType | None:
    """Best-effort infer the target platform from file names."""
    filenames = set(file_dict)
    if "agent.af" in filenames or "agent_state.json" in filenames:
        return AgentType.LETTA
    if any(f.endswith(".af") for f in filenames):
        return AgentType.LETTA
    if "soul.md" in filenames or "SOUL.md" in filenames:
        return AgentType.OPENCLAW
    if "persona.md" in filenames:
        return AgentType.ZEROCLAW
    if "agents.md" in filenames or "AGENTS.md" in filenames:
        return AgentType.OPENCLAW
    return None
