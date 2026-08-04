"""Domain-specific exceptions for configuration and Skill execution."""


class DataCleaningSkillsError(Exception):
    """Base error for the package."""


class SkillConfigurationError(DataCleaningSkillsError, ValueError):
    """Raised when rules cannot be mapped to a supported Skill configuration."""


class UnknownSkillError(DataCleaningSkillsError, KeyError):
    """Raised when a Skill name is not registered."""


class SkillExecutionError(DataCleaningSkillsError, RuntimeError):
    """Raised when a registered Skill violates the execution contract."""


class ContractValidationError(DataCleaningSkillsError, ValueError):
    """Raised when a generated artifact violates its published JSON Schema."""
