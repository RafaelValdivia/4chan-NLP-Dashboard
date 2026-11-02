# Role: annotation layer (sampling, terminal annotation, agreement metrics).
# Connects to: formal/schema, ingest/kek_loader, common/cli.

from keklab.annotation.schema import AnnotationRecord, SamplePost

__all__ = ["AnnotationRecord", "SamplePost"]
