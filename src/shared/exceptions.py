"""
Excepciones de Dominio para Quartermaster.
"""

class DomainError(Exception):
    """Error base de dominio."""
    pass


class InvalidMarketDataError(DomainError):
    pass


class CalculationError(DomainError):
    pass
