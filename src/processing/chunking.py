"""Log chunking module for splitting large log inputs."""

from typing import List, Dict, Optional


class LogChunker:
    """Splits large logs into manageable chunks for processing."""

    DEFAULT_CHUNK_SIZE = 2000  # characters
    DEFAULT_OVERLAP = 200  # characters

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_log(self, log_text: str) -> List[str]:
        """Split a log into chunks if it's too large."""
        if len(log_text) <= self.chunk_size:
            return [log_text]

        chunks = []
        start = 0
        while start < len(log_text):
            end = start + self.chunk_size
            if end >= len(log_text):
                chunks.append(log_text[start:])
                break

            # Try to break at a newline
            newline_pos = log_text.rfind('\n', start, end)
            if newline_pos > start + self.chunk_size // 2:
                end = newline_pos + 1
            else:
                # Try to break at a space
                space_pos = log_text.rfind(' ', start, end)
                if space_pos > start + self.chunk_size // 2:
                    end = space_pos + 1

            chunks.append(log_text[start:end])
            start = end - self.overlap

        return chunks

    def chunk_structured(self, log_data: Dict[str, any]) -> List[Dict[str, any]]:
        """Split structured log data into chunked versions."""
        chunks = self.chunk_log(log_data.get('cleaned_log', ''))
        result = []
        for i, chunk in enumerate(chunks):
            chunked = dict(log_data)
            chunked['cleaned_log'] = chunk
            chunked['chunk_index'] = i
            chunked['total_chunks'] = len(chunks)
            result.append(chunked)
        return result
