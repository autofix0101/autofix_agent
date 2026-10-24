"""
Shared Test Fixtures and Sample Data for AutoFix Agent Tests.
"""
from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent
SAMPLE_REPO_DIR = FIXTURES_DIR / "sample_repo"

PYTHON_TRACEBACK_SAMPLE = """
Traceback (most recent call last):
  File "/workspace/src/app.py", line 12, in <module>
    run_server()
  File "/workspace/src/payment/processor.py", line 45, in calculate_fee
    fee = amount * rate
TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'
"""

JS_STACK_TRACE_SAMPLE = """
TypeError: Cannot read properties of undefined (reading 'rate')
    at calculateTax (services/taxCalculator.ts:24:18)
    at processPayment (controllers/paymentController.ts:60:12)
    at Layer.handle [as handle_request] (/node_modules/express/lib/router/layer.js:95:5)
"""

GENERIC_COMPILER_ERROR_SAMPLE = """
src/models/user.py:58:12: error: Name 'hashed_pw' is used before definition
FAILED tests/test_auth.py::test_login - AssertionError: assert False
"""

GITHUB_ISSUE_SAMPLE = """
Bug Report: Payment calculation failed with TypeError in checkout

When a user attempts checkout with a discount voucher, the application crashes:

```
TypeError: Cannot read properties of undefined (reading 'rate')
    at calculateTax (services/taxCalculator.ts:24:18)
    at processPayment (controllers/paymentController.ts:60:12)
```

The `taxCalculator` is throwing an error when tax exemption is enabled.
Please check `services/taxCalculator.ts` and function `calculateTax`.
"""

NATURAL_LANGUAGE_ISSUE_SAMPLE = """
Feature Broken: Checkout button does not respond on mobile devices.
When the user clicks the 'Confirm Purchase' button on iOS Safari, nothing happens.
There are no console errors shown. Check `CheckoutButton.tsx` and `handleCheckout`.
"""

PYTHON_SOURCE_SAMPLE = """# Payment Processor Module

class PaymentProcessor:
    def __init__(self, currency: str = "USD"):
        self.currency = currency

    def calculate_fee(self, amount: float, rate: float | None) -> float:
        \"\"\"Calculate processing fee.\"\"\"
        if rate is None:
            raise ValueError("Rate must not be None")
        return amount * rate

def format_currency(amount: float, symbol: str = "$") -> str:
    return f"{symbol}{amount:.2f}"
"""

TYPESCRIPT_SOURCE_SAMPLE = """// Tax Calculator Service

export interface TaxConfig {
  defaultRate: number;
  exemptRegions: string[];
}

export function calculateTax(amount: number, config?: TaxConfig): number {
  if (!config) {
    throw new TypeError("Cannot read properties of undefined (reading 'rate')");
  }
  return amount * config.defaultRate;
}

export class TaxManager {
  private config: TaxConfig;

  constructor(config: TaxConfig) {
    this.config = config;
  }

  public getRate(): number {
    return this.config.defaultRate;
  }
}
"""
