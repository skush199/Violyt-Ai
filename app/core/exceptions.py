class DomainError(Exception):
    """Base domain error."""


class AuthorizationError(DomainError):
    """Raised when a user cannot perform an action."""


class LifecycleError(DomainError):
    """Raised when a lifecycle transition is invalid."""


class UsageLimitExceededError(DomainError):
    """Raised when tenant quota is exceeded."""


class GuardrailViolationError(DomainError):
    """Raised when a prompt or response violates brand guardrails."""


class NotFoundError(DomainError):
    """Raised when a requested entity is missing."""


class DuplicateResourceError(DomainError):
    """Raised when a unique resource already exists."""


class UploadValidationError(DomainError):
    """Raised when an uploaded file fails preflight validation."""


class GenerationFailureError(DomainError):
    """Raised when the generation pipeline cannot produce a final user-safe output."""

    def __init__(
        self,
        reason_summary: str,
        *,
        failure_type: str,
        reason_code: str,
        user_safe_message: str,
        retryable: bool,
        rule_source: str | None = None,
        suggested_next_action: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(reason_summary)
        self.failure_type = failure_type
        self.reason_code = reason_code
        self.reason_summary = reason_summary
        self.user_safe_message = user_safe_message
        self.retryable = retryable
        self.rule_source = rule_source
        self.suggested_next_action = suggested_next_action
        self.details = details or {}

    def to_payload(self) -> dict:
        return {
            "failure_type": self.failure_type,
            "reason_code": self.reason_code,
            "reason_summary": self.reason_summary,
            "user_safe_message": self.user_safe_message,
            "retryable": self.retryable,
            "rule_source": self.rule_source,
            "suggested_next_action": self.suggested_next_action,
            "details": self.details,
        }
