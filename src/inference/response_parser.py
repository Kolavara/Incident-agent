"""Response parser for extracting structured data from LLM output.

Handles multiple model output formats including:
- Standard: ROOT CAUSE: ... / CONFIDENCE: ... / FIX STEPS: ... / NOTES: ...
- Markdown bold: **ROOT CAUSE:** ...
- Code blocks: ```text ... ```
- Compact: Root Cause: ... Confidence: ... Fix Steps: ... Notes: ...
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger('incident_agent.response_parser')


class ResponseParser:
    """Parses LLM responses into structured diagnosis data."""

    def _clean_response(self, text: str) -> str:
        """Normalize a model response by stripping markdown and extra formatting.

        Removes:
        - <think>...</think> reasoning blocks (used by Qwen, DeepSeek, etc.)
        - Markdown code fences (```text, ```, etc.)
        - Markdown bold markers (**bold**)
        """
        if not text:
            return text

        # Strip <think>...</think> reasoning blocks (Qwen/DeepSeek chain-of-thought)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

        # If there's an unclosed <think> block (response was truncated),
        # remove everything from the <think> tag onwards
        if '<think>' in text:
            text = text[:text.index('<think>')].strip()

        # Strip markdown code fences (```text, ```, etc.)
        text = re.sub(r'```(?:\w*)\n?', '', text)
        text = re.sub(r'\n?```', '', text)

        # Strip markdown bold markers (**bold**)
        text = text.replace('**', '')

        return text.strip()

    def parse_diagnosis(self, raw_response: str) -> Dict[str, any]:
        """Parse an LLM diagnosis response into structured fields.

        Handles multiple output formats:
            ROOT CAUSE: ...
            CONFIDENCE: High / Medium / Low
            FIX STEPS:
            1. ...
            2. ...
            3. ...
            NOTES: ...

        Also handles markdown variants (**bold**), code blocks, and
        common casing variations (Root Cause, Root cause, etc.).

        Args:
            raw_response: The raw LLM response text

        Returns:
            Dict with keys: root_cause, confidence, fix_steps, notes, raw
        """
        result = {
            'root_cause': '',
            'confidence': 'Low',
            'fix_steps': [],
            'notes': '',
            'raw': raw_response,
            'parse_success': True,
        }

        if not raw_response:
            result['parse_success'] = False
            return result

        try:
            text = self._clean_response(raw_response)

            # --- Extract root cause ---
            # Try standard format first: ROOT CAUSE: <text>
            rc_match = re.search(
                r'ROOT\s*CAUSE\s*:\s*(.+?)(?:\n|$)',
                text, re.IGNORECASE
            )
            if rc_match:
                result['root_cause'] = rc_match.group(1).strip()
            else:
                # Fallback: match after a label that ends with "cause"
                rc_match = re.search(
                    r'(?:Root|root)\s+(?:Cause|cause)\s*:\s*(.+?)(?:\n|$)',
                    text
                )
                if rc_match:
                    result['root_cause'] = rc_match.group(1).strip()

            # --- Extract confidence ---
            conf_match = re.search(
                r'CONFIDENCE\s*:\s*(High|Medium|Low)',
                text, re.IGNORECASE,
            )
            if conf_match:
                result['confidence'] = conf_match.group(1).capitalize()
            else:
                # Fallback: match after "confidence" label
                conf_match = re.search(
                    r'(?:Confidence|confidence)\s*:\s*(high|medium|low)',
                    text
                )
                if conf_match:
                    result['confidence'] = conf_match.group(1).capitalize()

            # --- Extract fix steps ---
            # Try standard format: FIX STEPS: <newline> 1. ... 2. ... 3. ...
            fix_section = re.search(
                r'FIX\s*STEPS\s*:\s*\n(.+?)(?:\nNOTES|\n*$)',
                text, re.IGNORECASE | re.DOTALL,
            )
            if not fix_section:
                # Fallback: look for "fix steps" or "Fix Steps" label
                fix_section = re.search(
                    r'(?:Fix\s+[Ss]teps|fix\s+steps)\s*:\s*\n(.+?)(?:\n(?:Notes|notes|NOTES)\s*:|\n*$)',
                    text, re.DOTALL,
                )
            if not fix_section:
                # Fallback: match any numbered list after "steps"
                fix_section = re.search(
                    r'(?:[Ff]ix\s+[Ss]teps|[Ss]teps?)\s*:?\s*\n((?:\d+\..+(?:\n|$))+)',
                    text
                )

            if fix_section:
                steps_text = fix_section.group(1)
                steps = re.findall(
                    r'(?:\d+\.|[-*])\s*(.+?)(?:\n|$)',
                    steps_text,
                )
                result['fix_steps'] = [s.strip() for s in steps if s.strip()]

            # --- Extract notes ---
            # Try standard format: NOTES: <text>
            notes_match = re.search(
                r'NOTES\s*:\s*(.+?)(?:\n*$|(?=\n[A-Za-z\s]+:))',
                text, re.IGNORECASE | re.DOTALL,
            )
            if not notes_match:
                # Fallback: match after "Notes" or "notes" label
                notes_match = re.search(
                    r'(?:Notes|notes)\s*:\s*(.+?)(?:\n*$|(?=\n[A-Za-z\s]+:))',
                    text, re.DOTALL,
                )
            if notes_match:
                notes_text = notes_match.group(1).strip()
                # If notes are very short and look like a section header, skip
                if len(notes_text) > 5:
                    result['notes'] = notes_text

            # Validate that we got at least a root cause
            if not result['root_cause']:
                logger.warning(
                    "Could not parse root cause from response. "
                    "Falling back to first sentence."
                )
                # Last resort: use first meaningful sentence as root cause
                # Match from start: grab everything up to first period/newline
                first_sentence = re.match(r'^([A-Z][^.]*\.)', text.strip())
                if first_sentence and len(first_sentence.group(1)) > 10:
                    result['root_cause'] = first_sentence.group(1).strip()
                    result['confidence'] = 'Medium'
                    result['parse_success'] = True
                else:
                    result['parse_success'] = False

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            result['parse_success'] = False

        return result

    def format_for_display(self, diagnosis: Dict[str, any]) -> str:
        """Format parsed diagnosis for terminal display."""
        lines = []

        if diagnosis.get('root_cause'):
            lines.append(f"ROOT CAUSE: {diagnosis['root_cause']}")

        if diagnosis.get('confidence'):
            lines.append(f"CONFIDENCE: {diagnosis['confidence']}")

        if diagnosis.get('fix_steps'):
            lines.append("\nFIX STEPS:")
            for i, step in enumerate(diagnosis['fix_steps'], 1):
                lines.append(f"  {i}. {step}")

        if diagnosis.get('notes'):
            lines.append(f"\nNOTES: {diagnosis['notes']}")

        return '\n'.join(lines)
