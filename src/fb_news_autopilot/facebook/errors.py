"""Sanitized Meta failure types."""


class MetaError(RuntimeError):
    def __init__(self, category, message, status_code=None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class MetaConfigurationError(MetaError):
    pass
