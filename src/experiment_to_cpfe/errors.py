"""Domain exceptions raised by the experiment-to-CPFE pipeline."""


class PipelineError(Exception):
    """Base class for pipeline failures."""


class ConfigurationError(PipelineError):
    """Raised when pipeline configuration is invalid or incomplete."""


class ValidationError(PipelineError):
    """Raised when normalized data violates the project contract."""


class ArtifactError(PipelineError):
    """Raised when a required artifact is missing or inconsistent."""


class SolverError(PipelineError):
    """Raised when solver preparation or execution fails."""
