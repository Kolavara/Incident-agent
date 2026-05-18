"""Main inference engine - the core agent loop for incident diagnosis."""

import time
import uuid
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from src.processing.preprocessor import LogPreprocessor
from src.processing.tokenizer import Tokenizer
from src.rag.retriever import IncidentRetriever
from src.rag.indexer import IncidentIndexer
from src.core.model_factory import ModelRouter
from src.prompts.chain import ReasoningChain
from src.inference.response_parser import ResponseParser
from audit_log import AuditLogger

logger = logging.getLogger('incident_agent.inference_engine')


class InferenceEngine:
    """Main agent loop for incident diagnosis.

    Flow:
    1. Clean the input log
    2. Search memory for similar past incidents
    3. Determine model via routing
    4. Build prompt with memory context
    5. Call the selected model
    6. Parse and return structured response
    7. Log the full audit entry
    """

    def __init__(self, model_router: ModelRouter, retriever: IncidentRetriever,
                 indexer: IncidentIndexer, audit_logger: AuditLogger):
        self.preprocessor = LogPreprocessor()
        self.tokenizer = Tokenizer()
        self.model_router = model_router
        self.retriever = retriever
        self.indexer = indexer
        self.audit_logger = audit_logger
        self.chain = ReasoningChain()
        self.parser = ResponseParser()
        self._last_incident_id: Optional[str] = None
        self._last_diagnosis: Optional[Dict] = None
        self._last_cleaned_log: Optional[str] = None

    def diagnose(self, raw_log: str) -> Dict[str, Any]:
        """Run the full diagnosis pipeline on an error log.

        Args:
            raw_log: The raw error log text

        Returns:
            Dict with diagnosis, metadata, and audit information
        """
        start_time = time.time()
        incident_id = str(uuid.uuid4())[:8]

        # Step 1: Validate and preprocess
        if not self.preprocessor.validate_input(raw_log):
            raise ValueError(
                "Input log is too short or empty. Please provide a detailed error log "
                "(at least 20 characters)."
            )

        logger.info(f"[{incident_id}] Starting diagnosis pipeline...")

        processed = self.preprocessor.preprocess(raw_log)
        cleaned_log = processed['cleaned_log']
        extracted_fields = {
            'service': processed.get('service'),
            'error_type': processed.get('error_type'),
            'error_code': processed.get('error_code'),
            'host': processed.get('host'),
        }

        input_tokens = self.tokenizer.count_tokens(raw_log)

        # Step 2: Search memory for similar incidents
        logger.info(f"[{incident_id}] Searching memory for similar incidents...")
        memory_result = self.retriever.retrieve(cleaned_log)

        top_score = memory_result['top_score']
        incident_type = memory_result['incident_type']
        memory_context = memory_result['memory_context']

        # Step 3: Route to the appropriate model
        logger.info(f"[{incident_id}] Incident classified as: {incident_type} (score={top_score:.4f})")
        client, model_tier, routing_reason = self.model_router.route(top_score)

        logger.info(
            f"[{incident_id}] Routing: {routing_reason} | "
            f"Model tier: {model_tier} | "
            f"Model: {client.get_model_name()}"
        )

        # Step 4-5: Run the reasoning chain
        if incident_type == 'NOVEL':
            logger.info(f"[{incident_id}] Using complex reasoning chain for novel incident...")
            response = self.chain.run_complex(
                client, cleaned_log, memory_context, extracted_fields
            )
        else:
            logger.info(f"[{incident_id}] Using simple reasoning chain...")
            response = self.chain.run_simple(
                client, cleaned_log, memory_context, extracted_fields
            )

        # Step 6: Parse the response
        diagnosis = self.parser.parse_diagnosis(response.content)

        # Step 7: Calculate final metrics
        total_latency = time.time() - start_time
        total_input_tokens = input_tokens + response.input_tokens
        total_output_tokens = response.output_tokens

        # Update cumulative cost
        self.model_router.update_cost(response.cost_usd)

        # Build audit entry
        audit_entry = {
            'incident_id': incident_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'similarity_score': round(top_score, 4),
            'incident_type': incident_type,
            'model_used': response.model_used,
            'model_tier': model_tier,
            'routing_reason': routing_reason,
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'cost_usd': response.cost_usd,
            'cumulative_cost_usd': round(self.model_router.get_cumulative_cost(), 6),
            'latency_seconds': round(total_latency, 2),
            'resolved': False,
            'root_cause': diagnosis.get('root_cause', ''),
            'confidence': diagnosis.get('confidence', 'Low'),
            'service': extracted_fields.get('service', 'unknown'),
            'error_type': extracted_fields.get('error_type', 'unknown'),
        }

        self.audit_logger.log(audit_entry)

        # Store for potential resolution
        self._last_incident_id = incident_id
        self._last_diagnosis = diagnosis
        self._last_cleaned_log = cleaned_log
        self._last_response = response
        self._last_extracted_fields = extracted_fields

        logger.info(
            f"[{incident_id}] Diagnosis complete. "
            f"Type={incident_type}, Model={response.model_used}, "
            f"Cost=${response.cost_usd:.6f}, Latency={total_latency:.2f}s"
        )

        return {
            'incident_id': incident_id,
            'diagnosis': diagnosis,
            'incident_type': incident_type,
            'similarity_score': round(top_score, 4),
            'model_used': response.model_used,
            'model_tier': model_tier,
            'routing_reason': routing_reason,
            'cost_usd': response.cost_usd,
            'cumulative_cost_usd': round(self.model_router.get_cumulative_cost(), 6),
            'latency_seconds': round(total_latency, 2),
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'memory_context': memory_result,
            'raw_response': response.content,
            'extracted_fields': extracted_fields,
        }

    def resolve_last(self, fix_applied: str,
                     resolution_time_minutes: int = 0) -> bool:
        """Store the last diagnosed incident as resolved in memory.

        Args:
            fix_applied: Description of the fix applied
            resolution_time_minutes: Time to resolve in minutes

        Returns:
            True if stored successfully
        """
        if not self._last_incident_id or not self._last_diagnosis:
            logger.warning("No previous incident to resolve.")
            return False

        success = self.indexer.store_resolved(
            cleaned_log=self._last_cleaned_log or '',
            diagnosis=self._last_diagnosis,
            fix_applied=fix_applied,
            service=self._last_extracted_fields.get('service') if self._last_extracted_fields else None,
            resolution_time_minutes=resolution_time_minutes,
            model_used=self._last_response.model_used if hasattr(self, '_last_response') else 'unknown',
            cost_usd=self._last_response.cost_usd if hasattr(self, '_last_response') else 0.0,
        )

        if success:
            # Update audit log
            self.audit_logger.mark_resolved(self._last_incident_id)
            logger.info(f"Incident {self._last_incident_id} marked as resolved.")

        return success
