"""Booking pricing and payment validation utilities."""
from decimal import Decimal


# Pricing configuration (in currency units per minute)
BASE_RATE_PER_MINUTE = Decimal("0.50")  # Example: ₹0.50 per minute


def calculate_booking_cost(charging_duration_minutes: int) -> Decimal:
    """
    Calculate the cost of a booking based on duration.
    
    Args:
        charging_duration_minutes: Duration in minutes
    
    Returns:
        Cost as Decimal to 2 decimal places
    
    Example:
        >>> calculate_booking_cost(60)
        Decimal('30.00')  # ₹30 for 1 hour at ₹0.50/min
    """
    if charging_duration_minutes <= 0:
        return Decimal("0.00")
    
    cost = Decimal(charging_duration_minutes) * BASE_RATE_PER_MINUTE
    return round(cost, 2)


def validate_wallet_balance(wallet_balance: Decimal, required_amount: Decimal) -> tuple[bool, str]:
    """
    Validate if wallet has sufficient balance for a transaction.
    
    Args:
        wallet_balance: Current wallet balance
        required_amount: Required amount for transaction
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Example:
        >>> validate_wallet_balance(Decimal("100.00"), Decimal("50.00"))
        (True, '')
        
        >>> validate_wallet_balance(Decimal("25.00"), Decimal("50.00"))
        (False, 'Insufficient wallet balance. Required: ₹50.00, Available: ₹25.00')
    """
    if wallet_balance < required_amount:
        return (
            False,
            f"Insufficient wallet balance. Required: ₹{required_amount:.2f}, Available: ₹{wallet_balance:.2f}",
        )
    return True, ""


def format_currency(amount: Decimal) -> str:
    """
    Format amount as currency string.
    
    Args:
        amount: Amount as Decimal
    
    Returns:
        Formatted currency string (e.g., "₹50.00")
    """
    return f"₹{amount:.2f}"
