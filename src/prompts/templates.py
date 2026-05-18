"""Prompt templates for incident diagnosis."""

from typing import Dict, Optional


SYSTEM_PROMPT = """You are an expert Site Reliability Engineer with 10 years of experience at a high-growth fintech company. You specialize in diagnosing production incidents quickly and accurately.

Your task is to analyze error logs and provide clear, actionable diagnoses. If past similar incidents are provided, use patterns from them to inform your diagnosis. Learn from past fixes and apply that knowledge.

Always respond in this exact format:

ROOT CAUSE: [one sentence describing the root cause]
CONFIDENCE: [High / Medium / Low]
FIX STEPS:
1. [actionable step]
2. [actionable step]
3. [actionable step]
NOTES: [any caveats, warnings, or additional context]

Be specific and precise. Include actual commands, config changes, or code fixes when relevant."""


def build_user_prompt(cleaned_log: str, memory_context: str,
                      extracted_fields: Optional[Dict] = None) -> str:
    """Build the user prompt for diagnosis.

    Args:
        cleaned_log: The preprocessed error log
        memory_context: Formatted string of past similar incidents
        extracted_fields: Optional structured fields from preprocessing

    Returns:
        Formatted user prompt string
    """
    prompt_parts = ["ERROR LOG:\n"]

    if extracted_fields:
        prompt_parts.append("--- Extracted Context ---\n")
        if extracted_fields.get('service'):
            prompt_parts.append(f"Service: {extracted_fields['service']}\n")
        if extracted_fields.get('error_type'):
            prompt_parts.append(f"Error Type: {extracted_fields['error_type']}\n")
        if extracted_fields.get('error_code'):
            prompt_parts.append(f"Error Code: {extracted_fields['error_code']}\n")
        if extracted_fields.get('host'):
            prompt_parts.append(f"Host: {extracted_fields['host']}\n")
        prompt_parts.append("\n")

    prompt_parts.append(f"```\n{cleaned_log}\n```\n\n")

    prompt_parts.append("PAST SIMILAR INCIDENTS:\n")
    prompt_parts.append(memory_context)
    prompt_parts.append("\n\nDiagnose this incident. Follow the required output format exactly.")

    return ''.join(prompt_parts)


def build_resolution_prompt(diagnosis: str) -> str:
    """Build a prompt for resolution confirmation.

    Args:
        diagnosis: The original diagnosis text

    Returns:
        A prompt asking the user to confirm the fix
    """
    return (
        f"Based on this diagnosis:\n\n{diagnosis}\n\n"
        f"Please describe what fix was actually applied (or type SKIP to skip storage)."
    )


RESOLUTION_SYSTEM_PROMPT = """You are assisting an SRE team. They have fixed an incident based on your diagnosis. Store the fix details so the system learns from this incident for future reference."""
